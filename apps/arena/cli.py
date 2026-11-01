"""命令行入口。"""

from __future__ import annotations

import argparse
import copy
import sys
import tempfile
from pathlib import Path

from .adapters import CliAgent, discover, make_custom_agent, probe_run, unavailable_agents
from .mock import MockAgent
from .moderator import Arena, ArenaConfig
from .ui import DIM, RESET, UI

MIN_PLAYERS = 4  # 低于这个人数，投票容易出现全员平票

EPILOG = """\
示例：
  python arena.py --serve                   # 打开图形界面（推荐）
  python arena.py "远程办公提升了工程团队的生产力吗"
  python arena.py "该不该上 K8s" --agents claude,codex --vote-mode support
  python arena.py --list                    # 探测本地装了哪些 agent CLI
  python arena.py --probe                   # 逐个真实调用，验证是否可用
  python arena.py "命题" --mock 4            # 离线跑通流程，不消耗额度
  python arena.py "命题" --custom "myai=mycli chat --prompt {prompt}"

出局规则（--vote-mode）：
  eliminate  投「最没用」，票最多者出局（默认）
  support    投「最该留下」，票最少者出局
出局者立即禁言，但会转为评审，继续参与后续每一轮投票。
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="arena.py",
        description="多智能体辩论淘汰赛：本地 agent CLI 轮流发言、互相点评、投票淘汰，直到剩最后一人。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    p.add_argument("proposition", nargs="*", help="待辩论的命题")
    p.add_argument("-a", "--agents", help="只用这些 CLI，逗号分隔（如 claude,codex）")
    p.add_argument("-n", "--mock", type=int, help="用 N 个本地 mock agent 跑（不调外部 CLI）")
    p.add_argument("--mock-fail-rate", type=float, default=0.0, help="Mock 模式下注入调用失败的概率")
    p.add_argument(
        "--vote-mode", choices=["eliminate", "support"], default="eliminate",
        help="出局规则：eliminate=投最没用票多出局（默认）；support=投最该留票少出局",
    )
    p.add_argument(
        "--repeat", type=int, default=0,
        help="每个 CLI 起几个实例；0=自动（凑够 4 人，保证投票有第三方）",
    )
    p.add_argument("--max-rounds", type=int, default=0, help="最多几轮（默认 人数-1）")
    p.add_argument("--timeout", type=float, default=240, help="单次调用超时秒数（默认 240）")
    p.add_argument("--out", default="runs", help="战报输出目录（默认 ./runs）")
    p.add_argument("--custom", action="append", default=[], metavar="NAME=CMD",
                   help="自定义 CLI，如 \"myai=mycli chat --prompt {prompt}\"，可重复")
    p.add_argument("--deep", action=argparse.BooleanOptionalAction, default=True,
                   help="深度扫描启发式发现注册表外的 CLI（默认开启）")
    p.add_argument("--list", action="store_true", help="只列出探测到的 CLI")
    p.add_argument("--probe", action="store_true", help="真实调用一次，验证 CLI 是否可用")
    p.add_argument("--serve", action="store_true", help="启动图形界面（本地网页）")
    p.add_argument("--port", type=int, default=7788, help="图形界面端口（默认 7788）")
    p.add_argument("--no-open", action="store_true", help="启动图形界面时不自动打开浏览器")
    p.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    return p


def _fmt_agents(agents: list[CliAgent], ui: UI) -> None:
    if not agents:
        ui.warn("没有探测到任何已安装的 agent CLI")
        return
    print(f"{'NAME':<20}{'VERSION':<28}PATH", flush=True)
    print("-" * 100, flush=True)
    for a in agents:
        tag = "  [启发式发现]" if a.spec.discovered else ""
        print(f"{a.spec.key:<20}{(a.version or '?')[:26]:<28}{a.path}{tag}", flush=True)
        if a.spec.note:
            print(f"{'':<20}{DIM}{a.spec.note}{RESET}", flush=True)
        if a.spec.requires:
            print(f"{'':<20}{DIM}前提：{a.spec.requires}{RESET}", flush=True)


def _build_customs(raw: list[str], ui: UI) -> list[CliAgent]:
    out: list[CliAgent] = []
    for item in raw:
        if "=" not in item:
            ui.warn(f"自定义命令格式应为 NAME=CMD：{item}")
            continue
        name, tpl = item.split("=", 1)
        try:
            out.append(make_custom_agent(name.strip(), tpl.strip()))
        except ValueError as exc:
            ui.warn(f"自定义命令无效：{exc}")
    return out


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ui = UI(color=False if args.no_color else None)

    if args.serve:
        from config.server import serve

        return serve(port=args.port, open_browser=not args.no_open)

    only = [x.strip() for x in args.agents.split(",") if x.strip()] if args.agents else None
    customs = _build_customs(args.custom, ui)

    # ---- 纯探测模式 ----
    if args.list or args.probe:
        found = discover(only, deep=args.deep, customs=customs)
        _fmt_agents(found, ui)
        if args.probe and found:
            print("", flush=True)
            with tempfile.TemporaryDirectory(prefix="arena-probe-") as tmp:
                for a in found:
                    ok, detail = probe_run(a, Path(tmp))
                    mark = "OK  " if ok else "FAIL"
                    print(f"[{mark}] {a.spec.key:<16} {detail[:70]}", flush=True)
        return 0

    proposition = " ".join(args.proposition).strip()
    if not proposition:
        print("缺少命题。用法：python arena.py \"你的命题\"（-h 查看帮助）", file=sys.stderr)
        return 2

    # ---- 组队 ----
    agents: list = []
    if args.mock:
        agents = [
            MockAgent(name=f"mock{i + 1}", fail_rate=args.mock_fail_rate)
            for i in range(max(args.mock, 2))
        ]
        ui.info(f"Mock 模式：{len(agents)} 个本地假 agent，不调用外部 CLI")
    else:
        found = discover(only, deep=args.deep, customs=customs, skip_unavailable=True)
        if not found:
            ui.error("没有探测到任何 agent CLI，先运行 `python arena.py --list` 看看")
            ui.info("想先跑通流程可以用：python arena.py \"命题\" --mock 4")
            return 1
        for key, why in unavailable_agents().items():
            if only is None or key not in only:
                ui.info(f"跳过 {key}：{why}（修好后用 --agents {key} 强制启用）")

        repeat = args.repeat or max(1, -(-MIN_PLAYERS // len(found)))
        for a in found:
            for _ in range(repeat):
                agents.append(copy.copy(a))
        if repeat > 1:
            ui.info(f"检测到 {len(found)} 个 CLI，每个起 {repeat} 个独立实例 → 共 {len(agents)} 位参赛")
        if len(agents) < 2:
            ui.error("只有 1 个 agent，无法淘汰赛")
            return 1

    cfg = ArenaConfig(
        proposition=proposition,
        max_rounds=args.max_rounds,
        timeout=args.timeout,
        out_dir=Path(args.out),
        vote_mode=args.vote_mode,
    )

    try:
        Arena(agents, cfg, sink=ui).run()
    except KeyboardInterrupt:
        ui.warn("已中断")
        return 130
    return 0
