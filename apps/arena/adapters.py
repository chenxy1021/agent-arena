"""本地 Agent CLI 的探测与统一调用层。

设计要点：
1. 探测走「注册表 + PATH 扫描 + 常见安装目录兜底」，只依赖标准库；
2. 每个 CLI 的差异被收敛到 BUILDERS 里的一张参数表，上层只调用 ask()；
3. 子进程默认在独立临时工作目录、只读沙箱中运行，避免 agent 读写宿主项目；
4. 输出统一清洗（去 ANSI、去元信息噪声），拿不到就抛错而不是返回脏文本。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# claude 在某些代理环境下会往 stdout 打模型元信息行，影响发言解析
META_NOISE_RE = re.compile(r"^\s*\[claude-code:[^\]]*\]\s*$", re.M)

# GUI 启动的进程 PATH 常常不全，这里兜底常见安装位置
EXTRA_BIN_DIRS = (
    "~/.local/bin",
    "~/bin",
    "~/go/bin",
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
    "/usr/local/bin",
    "~/.cargo/bin",
    "~/.bun/bin",
    "~/.deno/bin",
    "~/.npm-global/bin",
    "~/.volta/bin",
    "~/Library/pnpm",
    "~/.local/share/pnpm",
    "~/.local/share/mise/shims",
    "~/.asdf/shims",
)


@dataclass(frozen=True)
class AgentSpec:
    key: str
    label: str
    bins: tuple[str, ...] = ()
    version_args: tuple[str, ...] = ("--version",)
    note: str = ""
    argv_template: tuple[str, ...] | None = None  # 自定义命令，含 {prompt} 占位符
    discovered: bool = False  # True = 深度扫描发现，参数靠猜
    # 内嵌在 .app 里的 CLI 不在 PATH 上，用解析器在运行时算出可执行入口
    resolver: Callable[[], str | None] | None = None
    requires: str = ""  # 使用前提（登录、模型等），仅在列表里提示


# 注册表：新增 CLI 只要在这里加一行 + BUILDERS 里加一个构造器
SPECS: tuple[AgentSpec, ...] = (
    AgentSpec("claude", "Claude Code", ("claude",), note="Anthropic Claude Code"),
    AgentSpec("codex", "Codex CLI", ("codex",), note="OpenAI Codex"),
    AgentSpec(
        "codebuddy", "CodeBuddy Code", ("codebuddy", "cbc"),
        note="腾讯 CodeBuddy，接口与 claude 兼容",
        requires="需先在终端登录一次（/login）",
    ),
    AgentSpec(
        "deepseek-harness", "DeepSeek Harness", ("dsh",),
        note="DeepSeek Harness headless 模式",
        resolver=lambda: _resolve_dsh(),
        requires="DeepSeek Harness.app 需已安装",
    ),
    AgentSpec(
        "zcode", "ZCode", ("zcode",),
        note="ZCode（智谱 GLM），走本地 magpie 代理",
        resolver=lambda: _resolve_zcode(),
        requires="ZCode.app 需已登录且应用在运行",
    ),
    AgentSpec("gemini", "Gemini CLI", ("gemini",), note="Google Gemini"),
    AgentSpec("qwen", "Qwen Code", ("qwen",), note="通义千问 Code"),
    AgentSpec("ollama", "Ollama", ("ollama",), note="本地模型，用 ARENA_OLLAMA_MODEL 指定"),
    AgentSpec("aider", "Aider", ("aider",), note="需要 git 仓库"),
    AgentSpec("opencode", "OpenCode", ("opencode",)),
    AgentSpec("crush", "Crush", ("crush",)),
    AgentSpec("goose", "Goose", ("goose",)),
    AgentSpec("cursor-agent", "Cursor Agent", ("cursor-agent",)),
    AgentSpec("copilot", "Copilot CLI", ("copilot",)),
    AgentSpec("droid", "Droid", ("droid",)),
    AgentSpec("amp", "Amp", ("amp",)),
    AgentSpec("llm", "LLM", ("llm",), note="Simon Willison llm"),
    AgentSpec("aichat", "AIChat", ("aichat",)),
    AgentSpec("sgpt", "ShellGPT", ("sgpt",)),
    AgentSpec("mods", "Mods", ("mods",)),
    AgentSpec("opencoder", "OpenCoder", ("opencoder",)),
)

SPEC_BY_KEY = {s.key: s for s in SPECS}


@dataclass
class BuildResult:
    argv: list[str]
    out_file: Path | None = None  # 优先从文件读最终消息（如 codex -o）
    stdin_text: str | None = None


BuildFn = Callable[[str, Path, str], BuildResult]


def _simple(prefix: Sequence[str] = (), suffix: Sequence[str] = ()) -> BuildFn:
    """大多数 CLI 的形态：exe [prefix...] <prompt> [suffix...]。"""

    def build(prompt: str, workdir: Path, exe: str) -> BuildResult:
        return BuildResult([exe, *prefix, prompt, *suffix])

    return build


def _b_codex(prompt: str, workdir: Path, exe: str) -> BuildResult:
    out = workdir / ".codex-last.txt"
    argv = [
        exe, "exec",
        "--skip-git-repo-check",
        "-s", "read-only",     # 只读沙箱：不给它改文件的能力
        "--ephemeral",         # 不落 session 文件
        "--color", "never",
        "-C", str(workdir),
        "-o", str(out),
        prompt,
    ]
    return BuildResult(argv, out_file=out)


def _b_ollama(prompt: str, workdir: Path, exe: str) -> BuildResult:
    model = os.environ.get("ARENA_OLLAMA_MODEL") or _ollama_default_model()
    return BuildResult([exe, "run", model, prompt])


def _b_aider(prompt: str, workdir: Path, exe: str) -> BuildResult:
    return BuildResult([
        exe, "--yes", "--no-auto-commits", "--no-check-update",
        "--no-stream", "--message", prompt,
    ])


def _b_goose(prompt: str, workdir: Path, exe: str) -> BuildResult:
    return BuildResult([exe, "run", "--text", prompt])


def _b_codebuddy(prompt: str, workdir: Path, exe: str) -> BuildResult:
    """与 claude 同构；--port 0 避免并发调用抢占固定端口。"""
    return BuildResult([exe, "-p", "--output-format", "text", "--port", "0", prompt])


def _b_dsh(prompt: str, workdir: Path, exe: str) -> BuildResult:
    """DeepSeek Harness 的 headless 子命令：答完即退，结果只走 stdout。"""
    return BuildResult([exe, "headless", prompt])


def _b_zcode(prompt: str, workdir: Path, exe: str) -> BuildResult:
    """exe 是生成的启动脚本，内部已带好 provider 配置环境变量。"""
    return BuildResult([exe, "-p", prompt, "--no-color"])


_OLLAMA_MODEL_CACHE: str | None = None


def _ollama_default_model() -> str:
    global _OLLAMA_MODEL_CACHE
    if _OLLAMA_MODEL_CACHE:
        return _OLLAMA_MODEL_CACHE
    model = "llama3.2"
    try:
        out = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=10
        ).stdout
        rows = [ln.split()[0] for ln in out.splitlines()[1:] if ln.strip()]
        if rows:
            model = rows[0]
    except Exception:
        pass
    _OLLAMA_MODEL_CACHE = model
    return model


BUILDERS: dict[str, BuildFn] = {
    "claude": _simple(("-p", "--output-format", "text")),
    "codex": _b_codex,
    "codebuddy": _b_codebuddy,
    "deepseek-harness": _b_dsh,
    "zcode": _b_zcode,
    "gemini": _simple(("-p",)),
    "qwen": _simple(("-p",)),
    "ollama": _b_ollama,
    "aider": _b_aider,
    "opencode": _simple(("run",)),
    "crush": _simple(("run",)),
    "goose": _b_goose,
    "cursor-agent": _simple(("-p",)),
    "copilot": _simple(("-p",)),
    "droid": _simple(("exec",)),
    "amp": _simple(("-x",)),
    "llm": _simple(()),
    "aichat": _simple(()),
    "sgpt": _simple(()),
    "mods": _simple(("-p",)),
    "opencoder": _simple(("run",)),
}


# ----------------------------------------------------------------------
# 应用内嵌 CLI：它们不在 PATH 上，需要在运行时现场算出可执行入口
# ----------------------------------------------------------------------
ARENA_CACHE = Path(os.path.expanduser("~/.cache/agent-arena"))
DSH_CLI = Path("/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh")
ZCODE_RES = Path("/Applications/ZCode.app/Contents/Resources")
ZCODE_CJS = ZCODE_RES / "glm" / "zcode.cjs"
ZCODE_BUILTIN = ZCODE_RES / "config" / "provider" / "zcode-builtin.json"
ZCODE_USER_PERSONAL = Path.home() / ".zcode" / "v2" / "provider_config.json"


def _resolve_dsh() -> str | None:
    if DSH_CLI.is_file() and os.access(DSH_CLI, os.X_OK):
        return str(DSH_CLI)
    return shutil.which("dsh")


def _write_zcode_personal(dest: Path, model: str) -> None:
    """以用户现有配置为底稿，补出 magpie 代理模型和默认选择。

    ZCode CLI 的 -p 模式要求「已选模型」，但它没有暴露任何命令行/环境变量入口；
    唯一可靠的办法是把选择写进个人 provider 配置。这里复制一份到缓存目录，
    不去改用户 ~/.zcode 下的原始文件，避免和桌面端互相覆盖。
    """
    data: dict = {"schemaVersion": 1, "config": {}}
    if ZCODE_USER_PERSONAL.is_file():
        try:
            data = json.loads(ZCODE_USER_PERSONAL.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    cfg = data.setdefault("config", {})
    rules = cfg.setdefault("providerConfigRules", {}).setdefault("providerRules", [])
    magpie = next((r for r in rules if r.get("providerId") == "magpie"), None)
    if magpie is None:
        magpie = {
            "providerId": "magpie",
            "providerName": "magpie",
            "enabled": True,
            "config": {
                "group": "standard-personal",
                "access": {"type": "api-key", "apiKey": "magpie"},
                "api": {"type": "anthropic-messages", "baseUrl": "http://127.0.0.1:3425"},
            },
        }
        rules.append(magpie)

    inner = magpie.setdefault("config", {})
    ids = list(inner.get("personalModelIds") or [])
    if model not in ids:
        ids.insert(0, model)
    inner["personalModelIds"] = ids
    inner["modelOrder"] = ids
    cfg["defaultModelSelection"] = {"providerId": "magpie", "modelId": model}

    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_zcode() -> str | None:
    """生成自包含启动脚本（node + zcode.cjs + provider 配置），返回脚本路径。"""
    if not ZCODE_CJS.is_file():
        return shutil.which("zcode")
    node = shutil.which("node")
    if not node:
        return None

    model = os.environ.get("ARENA_ZCODE_MODEL", "glm-5.3-flash")
    cache = ARENA_CACHE / "zcode"
    launcher, personal, signature = cache / "zcode", cache / "personal.json", cache / "signature.txt"
    src_mtime = ZCODE_USER_PERSONAL.stat().st_mtime_ns if ZCODE_USER_PERSONAL.is_file() else 0
    sig = f"{model}|{ZCODE_CJS.stat().st_mtime_ns}|{src_mtime}"

    try:
        fresh = launcher.is_file() and signature.read_text(encoding="utf-8").strip() == sig
    except OSError:
        fresh = False
    if fresh:
        return str(launcher)

    cache.mkdir(parents=True, exist_ok=True)
    _write_zcode_personal(personal, model)
    launcher.write_text(
        "#!/bin/sh\n"
        "# 由 agent_arena 自动生成，请勿手改（改这里会被下次运行覆盖）\n"
        f'export ZCODE_BUILTIN_PROVIDER_CONFIG_FILE="{ZCODE_BUILTIN}"\n'
        f'export ZCODE_PERSONAL_PROVIDER_CONFIG_FILE="{personal}"\n'
        f'exec "{node}" "{ZCODE_CJS}" "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    signature.write_text(sig, encoding="utf-8")
    return str(launcher)


# ----------------------------------------------------------------------
# 不可用记忆：登录态/额度这类问题重试也没用，记下来免得白占一个参赛位
# ----------------------------------------------------------------------
AUTH_HINT_RE = re.compile(
    r"(authentication required|not logged in|please log ?in|please use /login|"
    r"unauthori[sz]ed|invalid api key|api key missing|quota|insufficient balance|\b401\b)",
    re.I,
)
UNAVAILABLE_FILE = ARENA_CACHE / "unavailable.json"


def _load_unavailable() -> dict[str, str]:
    try:
        data = json.loads(UNAVAILABLE_FILE.read_text(encoding="utf-8"))
        return {k: str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def unavailable_agents() -> dict[str, str]:
    """已知不可用的 CLI（key -> 原因），供界面提示。"""
    return _load_unavailable()


def _set_unavailable(key: str, reason: str | None) -> None:
    data = _load_unavailable()
    if reason is None:
        if key not in data:
            return
        data.pop(key, None)
    else:
        if data.get(key) == reason:
            return
        data[key] = reason
    try:
        UNAVAILABLE_FILE.parent.mkdir(parents=True, exist_ok=True)
        UNAVAILABLE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # 缓存写不进去不影响主流程


@dataclass
class CallResult:
    text: str = ""
    elapsed: float = 0.0
    error: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


def clean_output(text: str) -> str:
    text = ANSI_RE.sub("", text)
    text = META_NOISE_RE.sub("", text)
    # 去掉 hook/调试前缀行，保留正文
    lines = [ln for ln in text.splitlines() if not ln.startswith("hook:")]
    return "\n".join(lines).strip()


class CliAgent:
    """一个可调用的本地 agent。接口保持极简：ask(prompt) -> CallResult。"""

    def __init__(self, spec: AgentSpec, path: str, version: str = "?"):
        self.spec = spec
        self.path = path
        self.version = version
        self.name = spec.key  # 由赛制层分配唯一名（claude#1）

    # -- 身份 ----------------------------------------------------------
    @property
    def label(self) -> str:
        return f"{self.spec.label} {self.version}"

    def __repr__(self) -> str:
        return f"<CliAgent {self.name} {self.path}>"

    # -- 调用 ----------------------------------------------------------
    def ask(
        self,
        prompt: str,
        workdir: Path,
        timeout: float = 240,
        retries: int = 1,
        on_output: Callable[[str], None] | None = None,
    ) -> CallResult:
        # CLI mode returns its output at process exit; the web UI uses API streaming.
        build = BUILDERS.get(self.spec.key, _simple(()))
        last_err = ""
        for attempt in range(retries + 1):
            started = time.monotonic()
            try:
                res = self._invoke(build, prompt, workdir, timeout)
                _set_unavailable(self.spec.key, None)  # 能出词就说明可用，清掉旧记录
                return res
            except subprocess.TimeoutExpired:
                return CallResult(
                    elapsed=time.monotonic() - started,
                    error=f"超时（>{timeout:.0f}s）",
                )
            except FileNotFoundError:
                _set_unavailable(self.spec.key, f"找不到可执行文件：{self.path}")
                return CallResult(error=f"找不到可执行文件：{self.path}")
            except Exception as exc:  # 单次失败不炸整场
                last_err = str(exc)

        if AUTH_HINT_RE.search(last_err):
            _set_unavailable(self.spec.key, last_err.split("\n")[0][:120])
        return CallResult(error=last_err or "未知错误")

    def _invoke(
        self, build: BuildFn, prompt: str, workdir: Path, timeout: float
    ) -> CallResult:
        started = time.monotonic()
        workdir = workdir.resolve()  # 统一绝对路径，避免 CLI 内部二次拼接出错
        if self.spec.argv_template:
            argv = [
                self.path if i == 0 else tok.replace("{prompt}", prompt)
                for i, tok in enumerate(self.spec.argv_template)
            ]
            br = BuildResult(argv)
        else:
            br = build(prompt, workdir, self.path)
        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        env.pop("CLAUDECODE", None)  # 避免嵌套会话检测导致直接退出
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        proc = subprocess.run(
            br.argv,
            cwd=str(workdir),
            input=br.stdin_text,
            stdin=None if br.stdin_text else subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        elapsed = time.monotonic() - started

        if br.out_file is not None and br.out_file.exists():
            txt = clean_output(br.out_file.read_text(encoding="utf-8", errors="replace"))
            if txt:
                return CallResult(txt, elapsed)

        txt = clean_output(proc.stdout or "")
        if txt:
            return CallResult(txt, elapsed)

        err = clean_output(proc.stderr or "")[-400:]
        if proc.returncode != 0:
            raise RuntimeError(f"退出码 {proc.returncode}：{err}" if err else f"退出码 {proc.returncode}")
        raise RuntimeError(f"空输出：{err}" if err else "空输出")


# ----------------------------------------------------------------------
# 探测
# ----------------------------------------------------------------------
SYSTEM_DIRS = {"/bin", "/sbin", "/usr/bin", "/usr/sbin", "/usr/libexec", "/System"}

# 深度扫描时用来筛"可能和 AI 相关"的文件名
HEURISTIC_RE = re.compile(
    r"(claude|codex|gemini|qwen|ollama|llm|gpt|aider|agent|copilot|cursor|crush|"
    r"goose|opencode|droid|deepseek|kimi|glm|llama|mistral|openai|anthropic|assistant|chat)",
    re.I,
)
# --help 里出现这些词，才认为它真的是个 AI 对话工具，而不是叫 chat 的普通脚本
AI_SIGNALS = (
    "gpt", "claude", "llm", "model", "api key", "api_key", "prompt",
    "token", "agent", "anthropic", "openai", "completion", "assistant",
)


def candidate_dirs() -> list[Path]:
    """PATH 全量 + 常见安装目录 + 各包管理器的 bin 目录。"""
    dirs: list[Path] = []
    seen: set[str] = set()

    def add(raw: str | Path) -> None:
        p = Path(os.path.expanduser(str(raw)))
        try:
            if not p.is_dir():
                return
            key = str(p.resolve())
        except OSError:
            return
        if key not in seen:
            seen.add(key)
            dirs.append(p)

    for raw in os.environ.get("PATH", "").split(os.pathsep):
        if raw:
            add(raw)
    for d in EXTRA_BIN_DIRS:
        add(d)
    # uv tool / pipx 装出来的命令行工具都藏在各自 venv 的 bin 下
    for base in ("~/.local/share/uv/tools", "~/.local/pipx/venvs"):
        root = Path(os.path.expanduser(base))
        if root.is_dir():
            for tool in root.iterdir():
                add(tool / "bin")
    # nvm / fnm 多版本 node 的全局包 bin
    import glob

    for pat in (
        "~/.nvm/versions/node/*/bin",
        "~/.local/share/fnm/node-versions/*/installation/bin",
        "~/.nodenv/versions/*/bin",
    ):
        for p in glob.glob(os.path.expanduser(pat)):
            add(p)
    return dirs


def _resolve_bin(names: Sequence[str], dirs: Sequence[Path]) -> Path | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
    for d in dirs:
        for name in names:
            cand = d / name
            if cand.is_file() and os.access(cand, os.X_OK):
                return cand
    return None


def _probe_version(path: str, args: Sequence[str]) -> str:
    try:
        out = subprocess.run(
            [path, *args], capture_output=True, text=True, timeout=15
        )
        raw = (out.stdout or out.stderr or "").strip()
        first = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
        return first[:48] or "?"
    except Exception:
        return "?"


def _resolve_spec_path(spec: AgentSpec, dirs: Sequence[Path]) -> str | None:
    """先问解析器（应用内嵌 CLI），再退回 PATH / 常见目录查找。"""
    if spec.resolver is not None:
        try:
            got = spec.resolver()
        except Exception:
            got = None
        if got:
            return got
    if spec.bins:
        found = _resolve_bin(spec.bins, dirs)
        if found is not None:
            return str(found)
    return None


def _looks_like_agent(path: Path, timeout: float = 4.0) -> bool:
    """跑一次 --help，看输出里是否反复出现 AI 相关词汇。宁可漏报也不误报。"""
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    try:
        out = subprocess.run(
            [str(path), "--help"], capture_output=True, text=True,
            timeout=timeout, env=env, stdin=subprocess.DEVNULL,
        )
    except Exception:
        return False
    text = ((out.stdout or "") + (out.stderr or "")).lower()
    if len(text) < 80:
        return False
    return sum(1 for s in AI_SIGNALS if s in text) >= 3


def _scan_candidates(
    dirs: Sequence[Path], skip_names: set[str], limit: int = 40
) -> list[tuple[str, Path]]:
    """在候选目录里找名字像 AI 工具、但不在注册表里的可执行文件。"""
    found: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for d in dirs:
        if str(d).rstrip("/") in SYSTEM_DIRS:
            continue
        try:
            entries = list(os.scandir(d))[:800]
        except OSError:
            continue
        for entry in entries:
            name = entry.name
            if name in skip_names or name.startswith(".") or name in seen:
                continue
            if not HEURISTIC_RE.search(name):
                continue
            try:
                if not (entry.is_file() and os.access(entry.path, os.X_OK)):
                    continue
            except OSError:
                continue
            seen.add(name)
            found.append((name, Path(entry.path)))
            if len(found) >= limit:
                return found
    return found


def make_custom_agent(name: str, template: str) -> CliAgent:
    """用户自定义命令模板，如 `mycli chat --prompt {prompt}`。"""
    parts = tuple(template.split())
    if not parts:
        raise ValueError("自定义命令不能为空")
    exe = parts[0]
    resolved = shutil.which(exe)
    spec = AgentSpec(
        key=name,
        label=f"{name}（自定义）",
        bins=(exe,),
        note=template,
        argv_template=parts,
        discovered=True,
    )
    return CliAgent(spec, resolved or exe, "custom")


def discover(
    only: Sequence[str] | None = None,
    deep: bool = False,
    customs: Sequence[CliAgent] = (),
    skip_unavailable: bool = False,
) -> list[CliAgent]:
    """扫描本地已安装的 agent CLI。

    deep=True 时额外做启发式发现：把名字像 AI 工具、且 --help 里带 AI 特征的可执行文件
    也纳入候选（标记为自动发现），避免漏掉注册表里没收录的新 CLI。

    skip_unavailable=True 时跳过上次因登录/额度问题失败的 CLI，
    避免它们占用参赛位（显式用 --agents 点名时不会跳过）。
    """
    dirs = candidate_dirs()
    wanted = {k.lower() for k in only} if only else None
    agents: list[CliAgent] = []
    seen: set[str] = set()
    known_names: set[str] = set()
    blocked = _load_unavailable() if (skip_unavailable and wanted is None) else {}

    for spec in SPECS:
        if wanted is not None and spec.key not in wanted:
            continue
        known_names.update(spec.bins)
        if spec.key in blocked:
            continue
        path = _resolve_spec_path(spec, dirs)
        if path is None:
            continue
        real = str(Path(path).resolve())
        if real in seen:  # 同一二进制被多个别名指向时只注册一次
            continue
        seen.add(real)
        agents.append(CliAgent(spec, path, _probe_version(path, spec.version_args)))

    if deep and wanted is None:
        for name, path in _scan_candidates(dirs, known_names):
            real = str(path.resolve())
            if real in seen or not _looks_like_agent(path):
                continue
            seen.add(real)
            spec = AgentSpec(
                key=name,
                label=name,
                bins=(name,),
                note="启发式发现：参数未知，失败请用自定义命令覆盖",
                discovered=True,
            )
            agents.append(CliAgent(spec, str(path), _probe_version(str(path), ("--version",))))

    for agent in customs:
        if wanted is not None and agent.spec.key not in wanted:
            continue
        if str(agent.path) in seen:
            continue
        seen.add(str(agent.path))
        agents.append(agent)

    return agents


def probe_run(agent: CliAgent, workdir: Path, timeout: float = 90) -> tuple[bool, str]:
    """真实跑一句话，验证这个 CLI 是否真的能出结果（登录态/额度/模型）。"""
    res = agent.ask("请只回复两个字：可用", workdir, timeout=timeout, retries=0)
    if res.error:
        return False, res.error
    return True, res.text.replace("\n", " ")[:60]
