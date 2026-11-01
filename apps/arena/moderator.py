"""赛制核心：独立首轮 → 跨轮点评 → 第二轮起投票 → 淘汰 → 直到剩一人。

规则要点（改动请保持语义一致）：
1. 第一轮所有模型独立发言；第二轮起只点评上一轮，且看不到本轮其他模型输出；
2. 第一轮不投票；从第二轮结束起，由「存活者 + 已出局的评审」一起投票；
3. 出局规则可切换：
   - eliminate（默认）：投观点最站不住的，票多者出局；
   - support：投最该留下的，票少者出局；
4. 平票时按累计分数裁决，再按本轮发言信息量，最后按名字，保证结果确定。
"""

from __future__ import annotations

import json
import random
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from . import prompts, report
from .adapters import CallResult
from .events import EventSink, NullSink

TAG_VIEW_RE = re.compile(r"【观点】\s*([\s\S]*)")
TAG_COMMENT_RE = re.compile(r"【点评】\s*([\s\S]*?)(?=【观点】|$)")
VOTE_JSON_RE = re.compile(r"\{[^{}]*[\"']?vote[\"']?\s*:\s*[^{}]*\}", re.S)
VOTE_LOOSE_RE = re.compile(r"vote[\"'\s]*[:：]\s*[\"“']([^\"”'\n,}]+)")

VOTE_MODES = ("eliminate", "support")


@dataclass
class Speech:
    round_no: int
    agent: str
    role: str
    text: str
    elapsed: float
    error: str | None = None


@dataclass
class Vote:
    round_no: int
    voter: str
    target: str | None
    reason: str = ""
    error: str | None = None
    is_judge: bool = False
    stage: str = "main"


@dataclass
class RoundRecord:
    no: int
    order: list[str]
    speeches: list[Speech] = field(default_factory=list)
    votes: list[Vote] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    eliminated: str | None = None
    votes_received: int = 0
    tiebreak: str | None = None
    tiebreak_steps: list[dict[str, Any]] = field(default_factory=list)
    exits: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ArenaConfig:
    proposition: str
    max_rounds: int = 0          # 0 = 自动（人数，首轮不投票）
    timeout: float = 240.0       # 单次调用超时（秒）
    out_dir: Path = Path("runs")
    retries: int = 1
    vote_mode: str = "eliminate"  # eliminate | support
    waiting_interval: float = 2.0  # 调用期间推送等待进度的间隔（秒）


@dataclass
class ArenaResult:
    proposition: str
    started_at: str
    duration: float
    vote_mode: str
    participants: list[dict[str, str]]
    rounds: list[RoundRecord]
    eliminated: list[dict[str, Any]]
    winner: str | None
    final_answer: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------
def _safe(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name)


def extract_view(text: str) -> str:
    m = TAG_VIEW_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


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


def parse_vote(text: str, valid: Sequence[str], voter: str) -> tuple[str | None, str]:
    """从模型输出里解析投票。返回 (target, reason)，target 为 None 表示解析失败。"""
    pool = [v for v in valid if v != voter]
    if not pool:
        return None, ""

    raw_obj: dict[str, Any] | None = None
    for m in VOTE_JSON_RE.finditer(text or ""):
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and ("vote" in obj or "target" in obj):
                raw_obj = obj
                break
        except Exception:
            continue

    target: str | None = None
    reason = ""
    if raw_obj:
        target = _clean_candidate(str(raw_obj.get("vote") or raw_obj.get("target") or ""))
        reason = str(raw_obj.get("reason") or "").strip()[:40]
    else:
        m = VOTE_LOOSE_RE.search(text or "")
        if m:
            target = _clean_candidate(m.group(1))

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

    # -- 路径 ----------------------------------------------------------
    def _workdir(self, agent: Any) -> Path:
        # 必须是绝对路径：CLI 内部再做相对路径拼接时会被二次解析
        d = self.run_dir / "ws" / _safe(agent.name)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _agent_dict(self, agent: Any) -> dict[str, str]:
        spec = getattr(agent, "spec", None)
        return {
            "name": agent.name,
            "label": getattr(agent, "label", ""),
            "path": str(getattr(agent, "path", "")),
            "discovered": bool(getattr(spec, "discovered", False)),
        }

    # -- 主流程 --------------------------------------------------------
    def run(self) -> ArenaResult:
        cfg = self.cfg
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        t0 = time.monotonic()

        active = list(self.agents)
        eliminated: list[dict[str, Any]] = []
        rounds: list[RoundRecord] = []
        max_rounds = cfg.max_rounds or max(len(active), 1)

        self.sink.emit(
            "run_start",
            proposition=cfg.proposition,
            agents=[self._agent_dict(a) for a in active],
            vote_mode=cfg.vote_mode,
            max_rounds=max_rounds,
        )
        for a in active:
            info = self._agent_dict(a)
            self.sink.emit("agent_info", **info)

        rnd = 0
        while len(active) > 1 and rnd < max_rounds:
            rnd += 1
            record = RoundRecord(no=rnd, order=[])
            order = self._rotate(active, rnd - 1)
            record.order = [a.name for a in order]
            self.sink.emit("round_start", no=rnd, alive=len(active), order=record.order)

            prior_speeches = _prior_speeches_for(active, rounds)

            # ---- 1. 独立发言 / 综合此前讨论并提出新观点 ----
            for agent in order:
                role = "独立发言" if rnd == 1 else "综合发言"
                prompt = prompts.build_speech_prompt(
                    speaker=agent.name,
                    proposition=cfg.proposition,
                    active=[a.name for a in active],
                    eliminated=[(e["agent"], e["reason"]) for e in eliminated],
                    round_no=rnd,
                    prior_speeches=prior_speeches,
                    my_last_stance=self._last_stance.get(agent.name),
                    vote_mode=cfg.vote_mode,
                )
                self.sink.emit("thinking", agent=agent.name, role=role)
                res = self._ask_with_progress(agent, prompt, role)
                record.speeches.append(self._record_speech(rnd, agent, role, res))

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
                if len(active) <= 1:
                    break
                continue

            # 首轮只发言、不投票；从第二轮结束起再进入裁决。
            if rnd == 1:
                rounds.append(record)
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
                break

            reasons = [v.reason for v in record.votes if v.target == out.name and v.reason]
            label = "票" if cfg.vote_mode == "eliminate" else "支持票"
            reason_text = f"第 {rnd} 轮以 {n_votes} {label}出局" + (f"：{reasons[0]}" if reasons else "")
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

        winner = active[0].name if len(active) == 1 else None
        final_text = self._final_statement(active[0], eliminated, rounds) if winner else ""
        if winner:
            self.sink.emit("winner", agent=winner)
            if final_text:
                self.sink.emit("final", agent=winner, text=final_text)

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
        self.sink.emit("speech", agent=agent.name, role=role,
                       text=res.text, elapsed=res.elapsed, error=None)
        return Speech(rnd, agent.name, role, res.text, res.elapsed)

    def _ask_with_progress(self, agent: Any, prompt: str, role: str) -> CallResult:
        """Forward streamed model output and keep emitting waiting heartbeats."""
        interval = max(0.05, self.cfg.waiting_interval)

        def on_output(chunk: str) -> None:
            if chunk:
                self.sink.emit("model_output", agent=agent.name, role=role, text=chunk)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                agent.ask,
                prompt,
                self._workdir(agent),
                self.cfg.timeout,
                self.cfg.retries,
                on_output,
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
        speech_pairs = [
            (s.agent, s.text if not s.error else f"（发言失败：{s.error}）") for s in speeches
        ]
        elim_pairs = [(e["agent"], e["reason"]) for e in eliminated]

        def task(agent: Any) -> Vote:
            is_judge = agent.name in judge_names
            self.sink.emit(
                "voting",
                round_no=rnd,
                stage=stage,
                voter=agent.name,
                is_judge=is_judge,
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
            )
            last_err = ""
            for attempt in range(2):
                res = agent.ask(
                    prompt, self._workdir(agent), min(self.cfg.timeout, 150),
                    self.cfg.retries if attempt == 0 else 0,
                )
                if res.error:
                    last_err = res.error
                    continue
                target, reason = parse_vote(res.text, names, agent.name)
                if target:
                    vote = Vote(rnd, agent.name, target, reason, None, is_judge, stage)
                    self.sink.emit(
                        "voting",
                        round_no=rnd,
                        stage=stage,
                        voter=agent.name,
                        is_judge=is_judge,
                        status="done",
                        target=target,
                        reason=reason,
                    )
                    return vote
                last_err = f"投票格式无法解析：{res.text[:60]}"
            vote = Vote(rnd, agent.name, None, "", last_err, is_judge, stage)
            self.sink.emit(
                "voting",
                round_no=rnd,
                stage=stage,
                voter=agent.name,
                is_judge=is_judge,
                status="error",
                error=last_err,
            )
            return vote

        votes: list[Vote] = []
        with ThreadPoolExecutor(max_workers=min(len(voters), 10)) as pool:
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

    def _edge_names(
        self, counts: dict[str, int], candidates: Sequence[Any]
    ) -> tuple[list[str], int]:
        scores = {a.name: counts.get(a.name, 0) for a in candidates}
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
        counts: dict[str, int],
        rnd: int,
        stage: str,
    ) -> None:
        self.sink.emit(
            "votes",
            rows=[
                {"voter": v.voter, "target": v.target, "reason": v.reason,
                 "error": v.error, "is_judge": v.is_judge, "stage": v.stage}
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
    ) -> tuple[Any | None, int, str | None]:
        """收集首轮票；平票时让同票者加赛，再逐次随机减少投票人。"""
        self._emit_voting_start(voters, active, rnd, "main")
        votes = self._collect_votes(voters, active, record.speeches, eliminated, rnd)
        counts = Counter(v.target for v in votes if v.target)
        record.votes = votes
        record.counts = dict(counts)
        self._emit_votes(votes, counts, rnd, "main")

        out, n_votes, tiebreak = self._decide(counts, active, record.speeches)
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
        removed_names: list[str] = []
        attempt = 0

        while True:
            attempt += 1
            stage = f"tiebreak-{attempt}"
            step: dict[str, Any] = {
                "attempt": attempt,
                "stage": stage,
                "agents": list(tied_names),
                "voters": len(remaining_voters),
                "removed": list(removed_names),
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
                removed=list(removed_names),
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
                    )
                    self.sink.emit("thinking", agent=agent.name, role="平票加赛")
                    res = self._ask_with_progress(agent, prompt, "平票加赛")
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
            counts = Counter(v.target for v in ballots if v.target)
            record.votes = votes
            record.counts = dict(counts)
            still_tied = list(tied_names)
            edge = 0
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
                    if removed_names:
                        reason = (
                            f"{len(tied_names)} 人平票；随机移出投票人 "
                            f"{'、'.join(removed_names)} 后决出"
                        )
                    return by_name[still_tied[0]], edge, reason
                tied_names = still_tied
                tied_agents = [a for a in tied_agents if a.name in set(tied_names)]
                by_name = {a.name: a for a in tied_agents}

            if len(remaining_voters) <= 1:
                lengths = {s.agent: len(extract_view(s.text)) for s in record.speeches}
                out = min(tied_agents, key=lambda a: (lengths.get(a.name, 0), a.name))
                removed = "、".join(removed_names) or "无"
                return (
                    out,
                    0,
                    f"{len(tied_names)} 人加赛后仍无有效票，随机移出投票人 {removed}，"
                    "最终按本轮发言信息量裁决",
                )

            removed = random.choice(remaining_voters)
            remaining_voters.remove(removed)
            removed_names.append(removed.name)

    def _decide(
        self,
        counts: dict[str, int],
        active: Sequence[Any],
        speeches: Sequence[Speech],
    ) -> tuple[Any | None, int, str | None]:
        """返回 (出局者, 其票数, 平票说明)。"""
        by_name = {a.name: a for a in active}
        lengths = {s.agent: len(extract_view(s.text)) for s in speeches}

        if not counts:
            target = min(active, key=lambda a: (lengths.get(a.name, 0), a.name))
            return target, 0, "无人有效投票，按信息量最少裁决"

        tied, edge = self._edge_names(counts, active)
        if self.cfg.vote_mode == "eliminate" and edge == 0:
            target = min(active, key=lambda a: (lengths.get(a.name, 0), a.name))
            return target, 0, "无人有效投票，按信息量最少裁决"

        if len(tied) == 1:
            return by_name.get(tied[0]), edge, None

        return None, edge, f"{len(tied)} 人平票，进入加赛"

    def _final_statement(
        self,
        winner: Any,
        eliminated: Sequence[dict[str, Any]],
        rounds: Sequence[RoundRecord],
    ) -> str:
        self.sink.emit("thinking", agent=winner.name, role="最终总结")
        prompt = prompts.build_final_prompt(
            winner=winner.name,
            proposition=self.cfg.proposition,
            transcript_digest=_digest(rounds),
            eliminated=[(e["agent"], e["reason"]) for e in eliminated],
        )
        res = self._ask_with_progress(winner, prompt, "最终总结")
        if res.error:
            self.sink.emit("error", message=f"最终总结失败：{res.error}")
            return ""
        return res.text.strip()


def run_arena(
    agents: Sequence[Any], cfg: ArenaConfig, sink: EventSink | None = None
) -> ArenaResult:
    return Arena(agents, cfg, sink).run()
