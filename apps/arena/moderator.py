"""赛制核心：独立首轮 → 跨轮点评 → 第二轮起投票 → 淘汰 → 直到剩一人。

规则要点（改动请保持语义一致）：
1. 第一轮所有模型独立发言；第二轮起只点评上一轮，且看不到本轮其他模型输出；
2. 第一轮不投票；从第二轮结束起，由「存活者 + 已出局的评审」一起投票；
3. 评审票权重 0.5，存活者票权重 1.0；只剩 2 人时评审总权重不超过存活者；
4. 出局规则可切换：
   - eliminate（默认）：投观点最站不住的，票多者出局；
   - support：投最该留下的，票少者出局；
5. 平票时按多维评分 → 存活者票优先 → 本轮新增主张数裁决，全部确定性，无随机。
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from . import prompts, report
from .agent import CallResult
from .events import EventSink, NullSink

TAG_VIEW_RE = re.compile(r"【观点】\s*([\s\S]*)")
TAG_COMMENT_RE = re.compile(r"【点评】\s*([\s\S]*?)(?=【观点】|$)")
TAG_STANCE_RE = re.compile(r"【立场】\s*([+-]?\d{1,3})")
TAG_CLAIM_RE = re.compile(r"【主张】\s*([\s\S]*?)(?=\n【|$)")

VOTE_MODES = ("eliminate", "support")
SPEECH_MODES = ("parallel_buffered", "sequential_live")

CONVERGENCE_SPREAD = 25   # 立场极差 ≤ 25 记为收敛，但不替代完整赛程
DIVERGENCE_SPREAD = 150  # 立场极差 ≥ 150 视为分歧过大，动态 +1 轮
MIN_CONVERGENCE_ROUND = 2  # 首轮是独立开场，至少两轮后才判断收敛
JUDGE_WEIGHT = 0.5       # 评审票权重
MAX_REASON_CHARS = 200


@dataclass
class Speech:
    round_no: int
    agent: str
    role: str
    text: str
    elapsed: float
    error: str | None = None
    stance: int | None = None


@dataclass
class Vote:
    round_no: int
    voter: str
    target: str | None
    reason: str = ""
    error: str | None = None
    is_judge: bool = False
    stage: str = "main"
    weight: float = 1.0
    scores: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class RoundRecord:
    no: int
    order: list[str]
    speeches: list[Speech] = field(default_factory=list)
    votes: list[Vote] = field(default_factory=list)
    counts: dict[str, float] = field(default_factory=dict)
    eliminated: str | None = None
    votes_received: float = 0
    tiebreak: str | None = None
    tiebreak_steps: list[dict[str, Any]] = field(default_factory=list)
    exits: list[dict[str, str]] = field(default_factory=list)
    scores: dict[str, dict[str, float]] = field(default_factory=dict)
    weight_breakdown: dict[str, Any] = field(default_factory=dict)
    stance_spread: int | None = None
    round_claims: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ArenaConfig:
    proposition: str
    max_rounds: int = 0          # 0 = 自动（人数，首轮不投票）
    timeout: float = 240.0       # 单次调用超时（秒）
    out_dir: Path = Path("runs")
    retries: int = 1
    vote_mode: str = "eliminate"  # eliminate | support
    waiting_interval: float = 2.0  # 调用期间推送等待进度的间隔（秒）
    speech_mode: str = "parallel_buffered"  # parallel_buffered | sequential_live
    parallel_workers: int = 4
    judge_weight: float = JUDGE_WEIGHT
    criteria: list[str] = field(default_factory=list)
    background: str = ""
    constraints: list[str] = field(default_factory=list)


@dataclass
class ArenaResult:
    proposition: str
    started_at: str
    duration: float
    vote_mode: str
    participants: list[dict[str, Any]]
    rounds: list[RoundRecord]
    eliminated: list[dict[str, Any]]
    winner: str | None
    final_answer: str
    claims: list[dict[str, Any]] = field(default_factory=list)
    setup: dict[str, Any] = field(default_factory=dict)
    budget: dict[str, Any] = field(default_factory=dict)
    speech_mode: str = "parallel_buffered"
    converged: bool = False
    stop_reason: str = ""
    schema_version: int = 3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------
def extract_view(text: str) -> str:
    m = TAG_VIEW_RE.search(text)
    if m:
        body = m.group(1)
    else:
        body = text
    return TAG_STANCE_RE.sub("", body).strip()


def extract_stance(text: str) -> int | None:
    """Parse the 【立场 ±N】 marker into a -100..100 stance value."""
    m = TAG_STANCE_RE.search(text or "")
    if not m:
        return None
    try:
        value = int(m.group(1))
    except ValueError:
        return None
    return max(-100, min(100, value))


def parse_claims(text: str) -> list[str]:
    """解析发言里的【主张】行；缺失时用【观点】首句兜底。"""
    claims: list[str] = []
    for m in TAG_CLAIM_RE.finditer(text or ""):
        claim = re.sub(r"\s+", " ", m.group(1)).strip()
        if 4 < len(claim) <= 160:
            claims.append(claim)
    if claims:
        return claims[:3]
    view = extract_view(text)
    if not view:
        return []
    first = re.split(r"[。！？\n]", view.strip())[0].strip()
    return [first[:120]] if len(first) >= 6 else []


def _clean_candidate(raw: str) -> str:
    return raw.strip().strip("\"'“”`.,，。:：")


def _prior_speeches_for(
    active: Sequence[Any], rounds: Sequence[RoundRecord]
) -> list[tuple[str, str]]:
    alive = {agent.name for agent in active}
    return [
        (speech.agent, speech.text)
        for round_record in rounds
        for speech in round_record.speeches
        if speech.agent in alive
    ]


def _last_round_speeches_for(
    active: Sequence[Any], rounds: Sequence[RoundRecord]
) -> list[tuple[str, str]]:
    """上一轮发言（点评只针对上一轮）。"""
    alive = {agent.name for agent in active}
    if not rounds:
        return []
    last = rounds[-1]
    return [(s.agent, s.text) for s in last.speeches if s.agent in alive and not s.error]


def extract_critiques_for(
    name: str, round_speeches: Sequence[Speech], votes: Sequence[Vote]
) -> list[str]:
    """抓取点名提到 name 的批评：上一轮点评里提到它，或投票理由里提到它。"""
    out: list[str] = []
    for speech in round_speeches:
        if speech.agent == name or speech.error:
            continue
        critique = TAG_COMMENT_RE.search(speech.text or "")
        body = (critique.group(1) if critique else "").strip()
        if body and name in body:
            out.append(f"{speech.agent}：{body[:200]}")
    for vote in votes:
        if vote.voter == name or not vote.reason:
            continue
        if name in vote.reason:
            out.append(f"{vote.voter}（投票理由）：{vote.reason[:200]}")
    return out


def _iter_json_objects(text: str):
    """扫描文本里的 JSON 对象（按大括号配对，能吃下嵌套的 scores 结构）。"""
    depth = 0
    start = -1
    in_string = False
    escape = False
    for index, char in enumerate(text or ""):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start >= 0:
                blob = text[start:index + 1]
                try:
                    obj = json.loads(blob)
                except Exception:
                    obj = None
                if isinstance(obj, dict):
                    yield obj


def _ballot_target(text: str, valid: Sequence[str], voter: str) -> tuple[str | None, str]:
    """解析当前 JSON ballot 的投票目标与理由。"""
    pool = [v for v in valid if v != voter]
    if not pool:
        return None, ""

    raw_obj: dict[str, Any] | None = None
    for obj in _iter_json_objects(text or ""):
        if "vote" in obj or "target" in obj:
            raw_obj = obj
            break

    target: str | None = None
    reason = ""
    if raw_obj:
        target = _clean_candidate(str(raw_obj.get("vote") or raw_obj.get("target") or ""))
        reason = str(raw_obj.get("reason") or "").strip()[:MAX_REASON_CHARS]

    if not target:
        return None, ""

    # 名字容错：精确 → 忽略大小写 → 子串 / 去序号
    if target in pool:
        return target, reason
    low = target.lower()
    for name in pool:
        if name.lower() == low:
            return name, reason
    for name in pool:
        base = name.split("#")[0].lower()
        if base == low or low in name.lower() or name.lower() in low:
            return name, reason
    return None, ""


def parse_ballot(
    text: str, valid: Sequence[str], voter: str
) -> tuple[str | None, str, dict[str, dict[str, float]]]:
    """当前版 JSON ballot：多维评分 + 票 + 理由。

    返回 (target, reason, scores)。scores = {被投模型: {维度: 分数}}
    """
    target, reason = _ballot_target(text, valid, voter)
    scores: dict[str, dict[str, float]] = {}

    for obj in _iter_json_objects(text or ""):
        raw_scores = obj.get("scores")
        if not isinstance(raw_scores, dict):
            continue
        for name, dims in raw_scores.items():
            if not isinstance(dims, dict):
                continue
            clean: dict[str, float] = {}
            for dim, value in dims.items():
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    continue
                clean[str(dim)] = max(0.0, min(10.0, number))
            if clean:
                scores[str(name)] = clean
        break

    return target, reason, scores


def _digest(rounds: Sequence[RoundRecord], limit: int = 4000) -> str:
    chunks: list[str] = []
    for r in rounds:
        chunks.append(f"第 {r.no} 轮：")
        for s in r.speeches:
            if s.error:
                chunks.append(f"- {s.agent}（发言失败）：{s.error}")
            else:
                chunks.append(f"- {s.agent}：{extract_view(s.text)[:220]}")
        if r.eliminated:
            chunks.append(f"- 淘汰 {r.eliminated}（{r.votes_received} 票）")
    text = "\n".join(chunks)
    return text if len(text) <= limit else text[:limit] + "\n…（已截断）"


def assign_names(agents: Sequence[Any]) -> None:
    """Keep unique names unchanged; number only duplicate display names."""
    keys = [getattr(getattr(ag, "spec", None), "key", "agent") or "agent" for ag in agents]
    totals: Counter[str] = Counter(keys)
    counter: Counter[str] = Counter()
    for ag in agents:
        key = getattr(getattr(ag, "spec", None), "key", "agent") or "agent"
        counter[key] += 1
        ag.name = f"{key}#{counter[key]}" if totals[key] > 1 else key


# ----------------------------------------------------------------------
# 主赛制
# ----------------------------------------------------------------------
class Arena:
    def __init__(self, agents: Sequence[Any], cfg: ArenaConfig, sink: EventSink | None = None):
        if len(agents) < 2:
            raise ValueError("至少需要 2 个 agent 才能开赛")
        if cfg.vote_mode not in VOTE_MODES:
            raise ValueError(f"vote_mode 只能是 {VOTE_MODES}")
        if cfg.speech_mode not in SPEECH_MODES:
            raise ValueError(f"speech_mode 只能是 {SPEECH_MODES}")
        self.agents = list(agents)
        assign_names(self.agents)
        self.cfg = cfg
        self.sink: EventSink = sink or NullSink()

        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.run_dir = (Path(cfg.out_dir) / stamp).resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self._fail_streak: dict[str, int] = {a.name: 0 for a in self.agents}
        self._last_stance: dict[str, str] = {}
        self._judges: list[Any] = []          # 已出局但保留投票权
        self._elim_round: dict[str, int] = {}
        self._claims: list[dict[str, Any]] = []      # 主张台账
        self._claim_seq = 0
        self._usage: dict[str, int] = {"calls": 0, "tokens_estimate": 0}
        self._usage_per_model: dict[str, dict[str, int]] = {}
        self._stopped = False
        self._stop_reason = ""
        self._rounds_cache: list[RoundRecord] = []
        self._parallel_chars: dict[str, int] = {}
        # 外部取消信号（services.Manager 注入），在轮次边界检查。
        self.cancel_hook: Any = None

    def _agent_dict(self, agent: Any) -> dict[str, Any]:
        return {
            "name": agent.name,
            "label": getattr(agent, "label", ""),
            "model": str(getattr(agent, "model", getattr(agent, "label", "")) or ""),
            "config_id": int(getattr(agent, "config_id", 0) or 0),
            "path": str(getattr(agent, "path", "")),
            "persona": str(getattr(agent, "persona", "") or ""),
        }

    def _persona_of(self, agent: Any) -> str:
        return str(getattr(agent, "persona", "") or "")

    def _record_usage(self, agent: Any, res: CallResult) -> None:
        self._usage["calls"] = int(self._usage.get("calls", 0)) + 1
        tokens = int(res.usage.get("total_tokens") or 0)
        if not tokens:
            tokens = int(res.usage.get("prompt_tokens") or 0) + int(
                res.usage.get("completion_tokens") or 0
            )
        if tokens:
            self._usage["tokens_estimate"] = int(
                self._usage.get("tokens_estimate", 0)
            ) + tokens
        per = self._usage_per_model.setdefault(agent.name, {"calls": 0, "tokens_estimate": 0})
        per["calls"] += 1
        per["tokens_estimate"] += tokens

    # -- 主张台账 ------------------------------------------------------
    def _add_claims(self, agent: str, text: str, rnd: int, stance: int | None) -> list[dict[str, Any]]:
        added: list[dict[str, Any]] = []
        for claim_text in parse_claims(text):
            self._claim_seq += 1
            entry = {
                "claim_id": f"C{self._claim_seq:02d}",
                "text": claim_text,
                "author": agent,
                "round": rnd,
                "stance": stance,
                "challengers": [],
                "supporters": [],
                "final_status": "dormant",
            }
            self._claims.append(entry)
            added.append(entry)
            self.sink.emit("claims", claims=[entry])
        return added

    def _update_claim_relations(self, text: str, author: str) -> None:
        """文本包含匹配：提到某条主张即视为引用（支持），直接反驳则记为挑战。"""
        body = text or ""
        for entry in self._claims:
            if entry["author"] == author:
                continue
            core = entry["text"][:24]
            if len(core) < 6 or core not in body:
                continue
            lowered = body.lower()
            markers = ("反驳", "反对", "不成立", "质疑", "错误")
            if any(marker in lowered for marker in markers):
                if author not in entry["challengers"]:
                    entry["challengers"].append(author)
            elif author not in entry["supporters"]:
                entry["supporters"].append(author)

    # -- 主流程 --------------------------------------------------------
    def run(self) -> ArenaResult:
        cfg = self.cfg
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        t0 = time.monotonic()

        active = list(self.agents)
        eliminated: list[dict[str, Any]] = []
        rounds: list[RoundRecord] = []
        max_rounds = cfg.max_rounds or max(len(active), 1)
        converged = False

        self.sink.emit(
            "run_start",
            proposition=cfg.proposition,
            agents=[self._agent_dict(a) for a in active],
            vote_mode=cfg.vote_mode,
            max_rounds=max_rounds,
            speech_mode=cfg.speech_mode,
        )
        for a in active:
            info = self._agent_dict(a)
            self.sink.emit("agent_info", **info)

        rnd = 0
        while len(active) > 1 and rnd < max_rounds:
            if self._cancelled():
                self._stop_reason = "用户中止"
                self.sink.emit("stopped", reason="用户中止")
                break
            rnd += 1
            record = RoundRecord(no=rnd, order=[])
            order = self._rotate(active, rnd - 1)
            record.order = [a.name for a in order]
            self.sink.emit("round_start", no=rnd, alive=len(active), order=record.order)

            prior_speeches = _last_round_speeches_for(active, rounds)

            # ---- 1. 独立发言 / 综合此前讨论并提出新观点 ----
            if cfg.speech_mode == "parallel_buffered":
                self._speak_parallel(order, active, eliminated, record, rnd, prior_speeches)
            else:
                self._speak_sequential(order, active, eliminated, record, rnd, prior_speeches)

            if self._stopped:
                rounds.append(record)
                self._rounds_cache.append(record)
                break

            # ---- 2. 技术性退赛（连续说不出话，不占用投票名额）----
            exits = self._check_technicals(active)
            if exits:
                record.exits = exits
                for e in exits:
                    eliminated.append(
                        {"agent": e["agent"], "round": rnd, "votes": 0,
                         "reason": e["reason"], "technical": True}
                    )
                    self.sink.emit("technical_exit", agent=e["agent"], error=e["reason"])
                active = [a for a in active if a.name not in {e["agent"] for e in exits}]
                rounds.append(record)
                self._rounds_cache.append(record)
                if len(active) <= 1:
                    break
                continue

            # 立场离散度只作为赛况读数；首轮独立开场不能据此结束比赛。
            record.stance_spread = self._stance_spread(active, record)
            self.sink.emit("spread", round_no=rnd, spread=record.stance_spread)
            if (
                rnd >= MIN_CONVERGENCE_ROUND
                and record.stance_spread is not None
                and record.stance_spread <= CONVERGENCE_SPREAD
            ):
                converged = True
                self.sink.emit("converged", round_no=rnd, spread=record.stance_spread)
            if record.stance_spread is not None and record.stance_spread >= DIVERGENCE_SPREAD:
                max_rounds += 1

            # 首轮只发言、不投票；从第二轮结束起再进入裁决。
            if rnd == 1:
                rounds.append(record)
                self._rounds_cache.append(record)
                continue

            # ---- 3. 全员投票：存活者 + 评审团 ----
            voters = list(self._judges) + list(active)
            out, n_votes, tiebreak = self._resolve_vote(
                voters, active, record, eliminated, rnd
            )
            record.eliminated = out.name if out else None
            record.votes_received = n_votes
            record.tiebreak = tiebreak

            if out is None:
                rounds.append(record)
                self._rounds_cache.append(record)
                break

            reasons = [v.reason for v in record.votes if v.target == out.name and v.reason]
            label = "票" if cfg.vote_mode == "eliminate" else "支持票"
            reason_text = f"第 {rnd} 轮以 {n_votes:g} {label}出局" + (f"：{reasons[0]}" if reasons else "")
            eliminated.append(
                {"agent": out.name, "round": rnd, "votes": n_votes,
                 "reason": reason_text, "technical": False}
            )
            self.sink.emit(
                "elimination", agent=out.name, votes=n_votes,
                tiebreak=tiebreak, reason=reason_text,
            )
            active = [a for a in active if a.name != out.name]
            self._judges.append(out)          # 转任评审：不再发言，但继续投票
            self._elim_round[out.name] = rnd
            rounds.append(record)
            self._rounds_cache.append(record)

        winner = active[0].name if len(active) == 1 else None
        final_text = self._final_statement(active[0], eliminated, rounds) if winner else ""
        if winner:
            self.sink.emit("winner", agent=winner)
            if final_text:
                self.sink.emit("final", agent=winner, text=final_text)

        budget = {
            "calls": int(self._usage.get("calls", 0)),
            "tokens_estimate": int(self._usage.get("tokens_estimate", 0)),
            "wall_clock": round(time.monotonic() - t0, 1),
            "per_model": dict(self._usage_per_model),
        }
        self.sink.emit("budget", **budget)

        result = ArenaResult(
            proposition=cfg.proposition,
            started_at=started,
            duration=round(time.monotonic() - t0, 1),
            vote_mode=cfg.vote_mode,
            participants=[self._agent_dict(a) for a in self.agents],
            rounds=rounds,
            eliminated=eliminated,
            winner=winner,
            final_answer=final_text,
            claims=self._claims,
            setup={
                "model_ids": [
                    int(getattr(agent, "config_id", 0) or 0)
                    for agent in self.agents
                ],
                "vote_mode": cfg.vote_mode,
                "speech_mode": cfg.speech_mode,
                "timeout": cfg.timeout,
                "background": cfg.background,
                "constraints": list(cfg.constraints),
                "criteria": list(cfg.criteria),
            },
            budget=budget,
            speech_mode=cfg.speech_mode,
            converged=converged,
            stop_reason=self._stop_reason,
        )
        paths = report.write_all(result, self.run_dir)
        self.sink.emit("saved", paths=[str(p) for p in paths])
        self.sink.emit(
            "done",
            duration=result.duration,
            rounds=len(rounds),
            winner=winner,
            run_dir=str(self.run_dir),
        )
        return result

    def _cancelled(self) -> bool:
        hook = self.cancel_hook
        if hook is None:
            return False
        try:
            return bool(hook.is_set())
        except AttributeError:
            return bool(hook)

    # -- 发言 ----------------------------------------------------------
    def _speak_prompt(
        self,
        agent: Any,
        active: Sequence[Any],
        eliminated: Sequence[dict[str, Any]],
        rnd: int,
        prior_speeches: Sequence[tuple[str, str]],
    ) -> str:
        my_claims = [c["text"] for c in self._claims if c["author"] == agent.name]
        critiques = extract_critiques_for(
            agent.name,
            [s for r in self._rounds_cache for s in r.speeches],
            [v for r in self._rounds_cache for v in r.votes],
        )
        return prompts.build_speech_prompt(
            speaker=agent.name,
            proposition=self.cfg.proposition,
            active=[a.name for a in active],
            eliminated=[(e["agent"], e["reason"]) for e in eliminated],
            round_no=rnd,
            prior_speeches=prior_speeches,
            my_last_stance=self._last_stance.get(agent.name),
            vote_mode=self.cfg.vote_mode,
            criteria=self.cfg.criteria,
            background=self.cfg.background,
            constraints=self.cfg.constraints,
            persona=self._persona_of(agent),
            my_claims=my_claims,
            critiques_of_me=critiques,
        )

    def _speak_sequential(
        self,
        order: Sequence[Any],
        active: Sequence[Any],
        eliminated: Sequence[dict[str, Any]],
        record: RoundRecord,
        rnd: int,
        prior_speeches: Sequence[tuple[str, str]],
    ) -> None:
        for agent in order:
            role = "独立发言" if rnd == 1 else "综合发言"
            prompt = self._speak_prompt(agent, active, eliminated, rnd, prior_speeches)
            self.sink.emit("thinking", agent=agent.name, role=role)
            res = self._ask_with_progress(agent, prompt, role)
            self._record_usage(agent, res)
            speech = self._record_speech(rnd, agent, role, res)
            record.speeches.append(speech)
            self._after_speech(record, speech, rnd)

    def _speak_parallel(
        self,
        order: Sequence[Any],
        active: Sequence[Any],
        eliminated: Sequence[dict[str, Any]],
        record: RoundRecord,
        rnd: int,
        prior_speeches: Sequence[tuple[str, str]],
    ) -> None:
        """并行生成：本轮所有人同时生成，完成后按席位顺序回放。"""
        role = "独立发言" if rnd == 1 else "综合发言"
        self._parallel_chars = {}
        self.sink.emit(
            "parallel_start",
            round_no=rnd,
            agents=[a.name for a in order],
            order=record.order,
        )
        prompts_by_agent = {
            agent.name: self._speak_prompt(agent, active, eliminated, rnd, prior_speeches)
            for agent in order
        }
        results: dict[str, CallResult] = {}

        def task(agent: Any) -> tuple[str, CallResult]:
            self.sink.emit("thinking", agent=agent.name, role=role)
            # 同轮模型彼此看不到这些事件；界面可安全展示真实流式文本。
            def on_chunk(chunk: str) -> None:
                self._parallel_chars[agent.name] = self._parallel_chars.get(agent.name, 0) + len(chunk)
                self.sink.emit(
                    "parallel_progress",
                    round_no=rnd,
                    agent=agent.name,
                    chars=self._parallel_chars[agent.name],
                    text=chunk,
                )

            res = self._ask_with_progress(
                agent, prompts_by_agent[agent.name], role, on_output=on_chunk
            )
            self._record_usage(agent, res)
            return agent.name, res

        workers = max(1, min(self.cfg.parallel_workers, len(order)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(task, agent): agent for agent in order}
            for fut in as_completed(futures):
                agent = futures[fut]
                try:
                    name, res = fut.result()
                    results[name] = res
                except Exception as exc:
                    results[agent.name] = CallResult(error=str(exc))
                self.sink.emit(
                    "parallel_done",
                    round_no=rnd,
                    agent=agent.name,
                    error=results[agent.name].error,
                )

        # 按席位顺序回放：先到先播，保证前端看到的是有序结果。
        for agent in order:
            res = results.get(agent.name) or CallResult(error="未返回结果")
            speech = self._record_speech(rnd, agent, role, res)
            record.speeches.append(speech)
            self._after_speech(record, speech, rnd)
            self.sink.emit(
                "parallel_replay",
                round_no=rnd,
                agent=agent.name,
                index=record.order.index(agent.name) + 1,
                total=len(record.order),
            )

    def _after_speech(self, record: RoundRecord, speech: Speech, rnd: int) -> None:
        if speech.error:
            return
        added = self._add_claims(speech.agent, speech.text, rnd, speech.stance)
        if added:
            record.round_claims.extend(added)
        self._update_claim_relations(speech.text, speech.agent)

    # -- 步骤实现 ------------------------------------------------------
    @staticmethod
    def _rotate(items: Sequence[Any], shift: int) -> list[Any]:
        if not items:
            return []
        k = shift % len(items)
        return list(items[k:]) + list(items[:k])

    def _record_speech(self, rnd: int, agent: Any, role: str, res: CallResult) -> Speech:
        if res.error:
            self._fail_streak[agent.name] = self._fail_streak.get(agent.name, 0) + 1
            speech = Speech(rnd, agent.name, role, "", res.elapsed, res.error)
            self.sink.emit("speech", agent=agent.name, role=role,
                           text="", elapsed=res.elapsed, error=res.error)
            return speech
        self._fail_streak[agent.name] = 0
        self._last_stance[agent.name] = extract_view(res.text)
        stance = extract_stance(res.text)
        self.sink.emit("speech", agent=agent.name, role=role,
                       text=res.text, elapsed=res.elapsed, error=None, stance=stance)
        return Speech(rnd, agent.name, role, res.text, res.elapsed, None, stance)

    def _ask_with_progress(
        self,
        agent: Any,
        prompt: str,
        role: str,
        on_output: Any = None,
    ) -> CallResult:
        """Forward streamed model output and keep emitting waiting heartbeats."""
        interval = max(0.05, self.cfg.waiting_interval)

        def default_output(chunk: str) -> None:
            if chunk:
                self.sink.emit("model_output", agent=agent.name, role=role, text=chunk)

        sink = on_output or default_output

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                agent.ask,
                prompt,
                timeout=self.cfg.timeout,
                retries=self.cfg.retries,
                on_output=sink,
            )
            started = time.monotonic()
            while not future.done():
                try:
                    return future.result(timeout=interval)
                except FutureTimeout:
                    self.sink.emit(
                        "waiting",
                        agent=agent.name,
                        role=role,
                        elapsed=round(time.monotonic() - started, 1),
                    )
            return future.result()

    def _check_technicals(self, active: Sequence[Any]) -> list[dict[str, str]]:
        if len(active) <= 2:
            return []  # 只剩两人时不允许技术退赛，交给投票
        out = []
        for a in active:
            if self._fail_streak.get(a.name, 0) >= 2:
                out.append({"agent": a.name, "reason": "连续两轮调用失败"})
        return out

    def _stance_spread(
        self, active: Sequence[Any], record: RoundRecord
    ) -> int | None:
        values = [
            s.stance for s in record.speeches
            if s.agent in {a.name for a in active} and s.stance is not None
        ]
        if len(values) < 2:
            return None
        return max(values) - min(values)

    def _judge_weight_for(self, alive_count: int) -> float:
        """只剩 2 人时，评审票总权重不得超过存活者。"""
        if alive_count <= 2:
            return 0.0
        return self.cfg.judge_weight

    def _collect_votes(
        self,
        voters: Sequence[Any],
        candidates: Sequence[Any],
        speeches: Sequence[Speech],
        eliminated: Sequence[dict[str, Any]],
        rnd: int,
        stage: str = "main",
    ) -> list[Vote]:
        names = [a.name for a in candidates]
        judge_names = {a.name for a in self._judges}
        judge_weight = self._judge_weight_for(len(names))
        speech_pairs = [
            (s.agent, s.text if not s.error else f"（发言失败：{s.error}）") for s in speeches
        ]
        elim_pairs = [(e["agent"], e["reason"]) for e in eliminated]

        def task(agent: Any) -> Vote:
            is_judge = agent.name in judge_names
            weight = judge_weight if is_judge else 1.0
            self.sink.emit(
                "voting",
                round_no=rnd,
                stage=stage,
                voter=agent.name,
                is_judge=is_judge,
                weight=weight,
                status="thinking",
            )
            judge_note = None
            if is_judge:
                judge_note = (
                    f"你是 {agent.name}，已在第 {self._elim_round.get(agent.name, '?')} 轮出局，"
                    "现在是评审团成员：本轮不再发言，但保留投票权，请只按证据投票。"
                )
            prompt = prompts.build_vote_prompt(
                voter=agent.name,
                proposition=self.cfg.proposition,
                active=names,
                speeches=speech_pairs,
                eliminated=elim_pairs,
                judge_note=judge_note,
                vote_mode=self.cfg.vote_mode,
                criteria=self.cfg.criteria,
                background=self.cfg.background,
                constraints=self.cfg.constraints,
            )
            res = agent.ask(
                prompt,
                timeout=min(self.cfg.timeout, 90),
                retries=0,
            )
            if res.error:
                last_err = res.error
            else:
                target, reason, scores = parse_ballot(res.text, names, agent.name)
                if target:
                    vote = Vote(rnd, agent.name, target, reason, None, is_judge, stage, weight, scores)
                    self.sink.emit(
                        "voting",
                        round_no=rnd,
                        stage=stage,
                        voter=agent.name,
                        is_judge=is_judge,
                        weight=weight,
                        status="done",
                        target=target,
                        reason=reason,
                    )
                    return vote
                last_err = f"投票格式无法解析：{res.text[:60]}"
            vote = Vote(rnd, agent.name, None, "", last_err, is_judge, stage, weight)
            self.sink.emit(
                "voting",
                round_no=rnd,
                stage=stage,
                voter=agent.name,
                is_judge=is_judge,
                weight=weight,
                status="error",
                error=last_err,
            )
            return vote

        votes: list[Vote] = []
        # 所有投票者同时提交，慢模型不会阻塞其他人。
        with ThreadPoolExecutor(max_workers=max(1, len(voters))) as pool:
            futures = {pool.submit(task, a): a for a in voters}
            for fut in as_completed(futures):
                agent = futures[fut]
                try:
                    votes.append(fut.result())
                except Exception as exc:
                    self.sink.emit(
                        "voting",
                        round_no=rnd,
                        stage=stage,
                        voter=agent.name,
                        status="error",
                        error=str(exc),
                    )
                    votes.append(Vote(rnd, agent.name, None, "", str(exc), stage=stage))
        votes.sort(key=lambda v: (not v.is_judge, v.voter))
        return votes

    def _weighted_counts(self, votes: Sequence[Vote]) -> dict[str, float]:
        counts: dict[str, float] = {}
        for vote in votes:
            if not vote.target:
                continue
            counts[vote.target] = counts.get(vote.target, 0.0) + float(vote.weight)
        return {k: round(v, 3) for k, v in counts.items()}

    def _weight_breakdown(self, votes: Sequence[Vote]) -> dict[str, Any]:
        alive = [v for v in votes if not v.is_judge and v.target]
        judges = [v for v in votes if v.is_judge and v.target]
        return {
            "alive_votes": len(alive),
            "judge_votes": len(judges),
            "judge_weight": self.cfg.judge_weight,
            "alive_weight_total": round(sum(v.weight for v in alive), 3),
            "judge_weight_total": round(sum(v.weight for v in judges), 3),
        }

    def _aggregate_scores(self, votes: Sequence[Vote]) -> dict[str, dict[str, float]]:
        """按被投模型聚合四维评分（取所有投票人给出的均分）。"""
        buckets: dict[str, dict[str, list[float]]] = {}
        for vote in votes:
            for name, dims in (vote.scores or {}).items():
                bucket = buckets.setdefault(name, {})
                for dim, value in dims.items():
                    bucket.setdefault(dim, []).append(float(value))
        out: dict[str, dict[str, float]] = {}
        for name, bucket in buckets.items():
            out[name] = {
                dim: round(sum(values) / len(values), 2)
                for dim, values in bucket.items()
                if values
            }
        return out

    def _edge_names(
        self, counts: dict[str, float], candidates: Sequence[Any]
    ) -> tuple[list[str], float]:
        scores = {a.name: counts.get(a.name, 0.0) for a in candidates}
        edge = min(scores.values()) if self.cfg.vote_mode == "support" else max(scores.values())
        return [name for name, value in scores.items() if value == edge], edge

    def _emit_voting_start(
        self,
        voters: Sequence[Any],
        candidates: Sequence[Any],
        rnd: int,
        stage: str,
    ) -> None:
        self.sink.emit(
            "voting_start",
            round_no=rnd,
            stage=stage,
            voters=len(voters),
            candidates=[a.name for a in candidates],
        )

    def _emit_votes(
        self,
        votes: Sequence[Vote],
        counts: dict[str, float],
        rnd: int,
        stage: str,
    ) -> None:
        self.sink.emit(
            "votes",
            rows=[
                {"voter": v.voter, "target": v.target, "reason": v.reason,
                 "error": v.error, "is_judge": v.is_judge, "stage": v.stage,
                 "weight": v.weight}
                for v in votes
            ],
            counts=dict(counts),
            vote_mode=self.cfg.vote_mode,
            round_no=rnd,
            stage=stage,
        )

    def _resolve_vote(
        self,
        voters: Sequence[Any],
        active: Sequence[Any],
        record: RoundRecord,
        eliminated: Sequence[dict[str, Any]],
        rnd: int,
    ) -> tuple[Any | None, float, str | None]:
        """收集首轮票；平票时进入确定性加赛裁决（无随机）。"""
        self._emit_voting_start(voters, active, rnd, "main")
        votes = self._collect_votes(voters, active, record.speeches, eliminated, rnd)
        counts = self._weighted_counts(votes)
        record.votes = votes
        record.counts = dict(counts)
        record.weight_breakdown = self._weight_breakdown(votes)
        record.scores = self._aggregate_scores(votes)
        self._emit_votes(votes, counts, rnd, "main")
        self._emit_scores(record.scores, rnd)

        out, n_votes, tiebreak = self._decide(counts, active, record.speeches, record)
        if out is not None or not counts:
            return out, n_votes, tiebreak

        tied_names, _ = self._edge_names(counts, active)
        tied_agents = [a for a in active if a.name in set(tied_names)]
        by_name = {a.name: a for a in tied_agents}
        round_speeches = [
            (s.agent, s.text if not s.error else f"（发言失败：{s.error}）")
            for s in record.speeches
        ]
        remaining_voters = list(voters)
        attempt = 0

        while True:
            attempt += 1
            stage = f"tiebreak-{attempt}"
            step: dict[str, Any] = {
                "attempt": attempt,
                "stage": stage,
                "agents": list(tied_names),
                "voters": len(remaining_voters),
                "removed": [],
                "counts": {},
                "leader": 0,
                "status": "speaking" if attempt == 1 else "voting",
            }
            record.tiebreak_steps.append(step)
            self.sink.emit(
                "tiebreak",
                round_no=rnd,
                attempt=attempt,
                agents=list(tied_names),
                voters=len(remaining_voters),
                removed=[],
                stage=stage,
                status=step["status"],
            )

            if attempt == 1:
                tiebreak_speeches: list[tuple[str, str]] = []
                for agent in tied_agents:
                    prompt = prompts.build_tiebreak_speech_prompt(
                        speaker=agent.name,
                        proposition=self.cfg.proposition,
                        candidates=tied_names,
                        round_no=rnd,
                        round_speeches=round_speeches,
                        tiebreak_speeches=tiebreak_speeches,
                        criteria=self.cfg.criteria,
                        background=self.cfg.background,
                        constraints=self.cfg.constraints,
                    )
                    self.sink.emit("thinking", agent=agent.name, role="平票加赛")
                    res = self._ask_with_progress(agent, prompt, "平票加赛")
                    self._record_usage(agent, res)
                    speech = self._record_speech(rnd, agent, "平票加赛", res)
                    record.speeches.append(speech)
                    tiebreak_speeches.append(
                        (speech.agent, speech.text if not speech.error else f"（发言失败：{speech.error}）")
                    )

            self._emit_voting_start(remaining_voters, tied_agents, rnd, stage)
            ballots = self._collect_votes(
                remaining_voters,
                tied_agents,
                record.speeches,
                eliminated,
                rnd,
                stage=stage,
            )
            votes.extend(ballots)
            counts = self._weighted_counts(ballots)
            record.votes = votes
            record.counts = dict(counts)
            still_tied = list(tied_names)
            edge = 0.0
            if counts:
                still_tied, edge = self._edge_names(counts, tied_agents)
            step.update(
                counts=dict(counts),
                leader=max(counts.values(), default=0),
                status="decided" if len(still_tied) == 1 else "tied",
            )
            self.sink.emit(
                "tiebreak_result",
                round_no=rnd,
                attempt=attempt,
                stage=stage,
                counts=dict(counts),
                leader=step["leader"],
                status=step["status"],
            )
            self._emit_votes(votes, counts, rnd, stage)

            if counts:
                if len(still_tied) == 1:
                    reason = f"{len(tied_names)} 人平票，加赛发言后决出"
                    return by_name[still_tied[0]], edge, reason
                tied_names = still_tied
                tied_agents = [a for a in tied_agents if a.name in set(tied_names)]
                by_name = {a.name: a for a in tied_agents}

            # 加赛仍然平票：走确定性三级裁决，不再随机移出投票人。
            out, n_votes, reason = self._decide(
                counts, tied_agents, record.speeches, record, allow_tiebreak=False
            )
            if out is not None:
                return out, n_votes, reason
            return None, 0.0, f"{len(tied_names)} 人加赛后仍未分出胜负"

    def _emit_scores(self, scores: dict[str, dict[str, float]], rnd: int) -> None:
        if not scores:
            return
        ranked = sorted(
            scores.items(),
            key=lambda item: -(sum(item[1].values()) / max(1, len(item[1]))),
        )
        self.sink.emit(
            "scores",
            round_no=rnd,
            scores=scores,
            ranking=[name for name, _ in ranked],
        )

    def _claim_count_for(self, name: str, record: RoundRecord) -> int:
        return sum(1 for c in record.round_claims if c.get("author") == name)

    def _decide(
        self,
        counts: dict[str, float],
        active: Sequence[Any],
        speeches: Sequence[Speech],
        record: RoundRecord | None = None,
        allow_tiebreak: bool = True,
    ) -> tuple[Any | None, float, str | None]:
        """返回 (出局者, 其票数, 平票说明)。allow_tiebreak=False 时走三级确定性裁决。"""
        by_name = {a.name: a for a in active}
        lengths = {s.agent: len(extract_view(s.text)) for s in speeches}

        if not counts:
            target = min(active, key=lambda a: (lengths.get(a.name, 0), a.name))
            return target, 0.0, "无人有效投票，按信息量最少裁决"

        tied, edge = self._edge_names(counts, active)
        if self.cfg.vote_mode == "eliminate" and edge == 0:
            target = min(active, key=lambda a: (lengths.get(a.name, 0), a.name))
            return target, 0.0, "无人有效投票，按信息量最少裁决"

        if len(tied) == 1:
            return by_name.get(tied[0]), edge, None

        if allow_tiebreak:
            return None, edge, f"{len(tied)} 人平票，进入加赛"

        return self._decide_tiebreak(tied, edge, by_name, record, speeches)

    def _decide_tiebreak(
        self,
        tied: Sequence[str],
        edge: float,
        by_name: dict[str, Any],
        record: RoundRecord | None,
        speeches: Sequence[Speech],
    ) -> tuple[Any | None, float, str | None]:
        """三级确定性裁决：评分差 → 存活者票优先 → 本轮新增主张数。"""
        scores = (record.scores if record else {}) or {}

        def avg(name: str) -> float:
            dims = scores.get(name) or {}
            return sum(dims.values()) / len(dims) if dims else 0.0

        # 低分者出局（评分高者留）。
        ranked = sorted(tied, key=lambda name: (avg(name), name))
        if avg(ranked[0]) < avg(ranked[-1]):
            return by_name.get(ranked[0]), edge, f"{len(tied)} 人平票，按多维评分差裁决"

        # 存活者票优先：靠评审票撑起来的那一个先出局。
        alive_votes: dict[str, int] = {}
        if record:
            for vote in record.votes:
                if vote.target and not vote.is_judge:
                    alive_votes[vote.target] = alive_votes.get(vote.target, 0) + 1
        vote_ranked = sorted(tied, key=lambda name: (alive_votes.get(name, 0), name))
        if alive_votes.get(vote_ranked[0], 0) < alive_votes.get(vote_ranked[-1], 0):
            return by_name.get(vote_ranked[0]), edge, f"{len(tied)} 人平票，存活者票优先裁决"

        # 本轮新增主张少者出局。
        claim_counts = {
            name: (self._claim_count_for(name, record) if record else 0) for name in tied
        }
        claim_ranked = sorted(tied, key=lambda name: (claim_counts.get(name, 0), name))
        if claim_counts.get(claim_ranked[0], 0) < claim_counts.get(claim_ranked[-1], 0):
            return by_name.get(claim_ranked[0]), edge, f"{len(tied)} 人平票，按本轮新增主张数裁决"

        # 兜底：按姓名排序，保证结果可复现。
        lengths = {s.agent: len(extract_view(s.text)) for s in speeches}
        target = min(tied, key=lambda name: (lengths.get(name, 0), name))
        return by_name.get(target), edge, f"{len(tied)} 人平票，按确定性顺序裁决"

    def _final_statement(
        self,
        winner: Any,
        eliminated: Sequence[dict[str, Any]],
        rounds: Sequence[RoundRecord],
    ) -> str:
        self.sink.emit("thinking", agent=winner.name, role="最终总结")
        eliminated_claims = [
            c["text"] for c in self._claims
            if c["author"] != winner.name and c["final_status"] != "rejected"
        ][:12]
        prompt = prompts.build_final_prompt(
            winner=winner.name,
            proposition=self.cfg.proposition,
            transcript_digest=_digest(rounds),
            eliminated=[(e["agent"], e["reason"]) for e in eliminated],
            eliminated_claims=eliminated_claims,
            criteria=self.cfg.criteria,
            background=self.cfg.background,
            constraints=self.cfg.constraints,
        )
        res = self._ask_with_progress(winner, prompt, "最终总结")
        self._record_usage(winner, res)
        if res.error:
            self.sink.emit("error", message=f"最终总结失败：{res.error}")
            return ""
        text = res.text.strip()
        # 最终裁决里写下的主张记为采纳。
        for entry in self._claims:
            core = entry["text"][:16]
            if len(core) >= 6 and core in text:
                entry["final_status"] = "adopted"
        return text


def run_arena(
    agents: Sequence[Any], cfg: ArenaConfig, sink: EventSink | None = None
) -> ArenaResult:
    return Arena(agents, cfg, sink).run()
