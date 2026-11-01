"""终端渲染。订阅赛制事件，只负责展示，不参与任何决策。"""

from __future__ import annotations

import sys
from typing import Any, Sequence

from .events import EventSink

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"

VOTE_MODE_LABEL = {
    "eliminate": "淘汰制：投最没用的，票多者出局",
    "support": "评选制：投最该留下的，票少者出局",
}


class UI(EventSink):
    def __init__(self, color: bool | None = None):
        self.color = sys.stdout.isatty() if color is None else color

    # -- 基础 ----------------------------------------------------------
    def _c(self, text: str, code: str) -> str:
        return f"{code}{text}{RESET}" if self.color else text

    def raw(self, text: str = "") -> None:
        print(text, flush=True)

    def rule(self, char: str = "─", width: int = 72) -> None:
        print(self._c(char * width, DIM), flush=True)

    def info(self, text: str) -> None:
        print(self._c(f"· {text}", DIM), flush=True)

    def warn(self, text: str) -> None:
        print(self._c(f"! {text}", YELLOW), flush=True)

    def error(self, text: str) -> None:
        print(self._c(f"✖ {text}", RED), flush=True)

    # -- 事件分发 ------------------------------------------------------
    def emit(self, kind: str, **data: Any) -> None:
        handler = getattr(self, f"_on_{kind}", None)
        if handler is not None:
            handler(**data)

    def _on_run_start(self, proposition: str, agents: Sequence[dict], vote_mode: str, **_):
        self.rule("═")
        print(self._c("  AGENT ARENA  ·  多智能体辩论淘汰赛", BOLD + CYAN), flush=True)
        self.rule("═")
        print(f"{self._c('命题', BOLD)}：{proposition}", flush=True)
        print(
            f"{self._c('参赛', BOLD)}：{len(agents)} 位 → "
            + ", ".join(a["name"] for a in agents),
            flush=True,
        )
        print(f"{self._c('规则', BOLD)}：{VOTE_MODE_LABEL.get(vote_mode, vote_mode)}", flush=True)
        self.rule()

    def _on_agent_info(self, name: str, label: str, path: str, **_):
        self.info(f"{name:<14} {label}  ← {path}")

    def _on_round_start(self, no: int, alive: int, order: Sequence[str], **_):
        print("", flush=True)
        print(
            self._c(f"▎ROUND {no}", BOLD + YELLOW)
            + self._c(f"   存活 {alive} 人   发言顺序：", DIM)
            + ", ".join(order),
            flush=True,
        )
        self.rule()

    def _on_thinking(self, agent: str, role: str, **_):
        print(self._c(f"  ⋯ {agent} 正在组织{role}…", DIM), flush=True)

    def _on_speech(self, agent: str, role: str, text: str, elapsed: float, error: str | None = None, **_):
        if error:
            print(self._c(f"│ {agent} 发言失败：{error}", RED), flush=True)
            return
        head = f"┌─ {agent} " + self._c(f"[{role}]", MAGENTA) + self._c(f"  {elapsed:.1f}s", DIM)
        print(head, flush=True)
        for line in text.strip().splitlines():
            print(f"│ {line}", flush=True)
        print("└" + "─" * 3, flush=True)

    def _on_votes(self, rows: Sequence[dict], counts: dict[str, int], vote_mode: str = "eliminate", **_):
        print("", flush=True)
        print(self._c("  投票结果", BOLD + BLUE), flush=True)
        for r in rows:
            voter = r["voter"] + (self._c(" [评审]", DIM) if r.get("is_judge") else "")
            target = r.get("target") or "（弃权）"
            note = r.get("reason") or r.get("error") or ""
            print(f"   {voter:<16} → {self._c(target, GREEN):<16} {self._c(note, DIM)}", flush=True)
        if counts:
            summary = "  ".join(f"{k}:{v}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))
        else:
            summary = "无有效票"
        print(self._c(f"   计票：{summary}", BOLD), flush=True)

    def _on_elimination(self, agent: str, votes: int, tiebreak: str | None = None, **_):
        tail = f"（{tiebreak}）" if tiebreak else ""
        print("", flush=True)
        print(self._c(f"  ✖ 淘汰 {agent}  {votes} 票{tail}", BOLD + RED), flush=True)
        print(self._c(f"    → 转为评审：下一轮不再发言，但保留投票权", DIM), flush=True)

    def _on_technical_exit(self, agent: str, error: str, **_):
        print(self._c(f"  ⚠ {agent} 连续调用失败，技术性退赛：{error}", RED), flush=True)

    def _on_winner(self, agent: str, **_):
        print("", flush=True)
        self.rule("═")
        print(self._c(f"  ★ 最终存活：{agent}", BOLD + GREEN), flush=True)
        self.rule("═")

    def _on_final(self, agent: str, text: str, **_):
        if not text:
            return
        print("", flush=True)
        print(self._c(f"  最终结论（{agent}）", BOLD + CYAN), flush=True)
        for line in text.strip().splitlines():
            print(f"  {line}", flush=True)
        print("", flush=True)

    def _on_saved(self, paths: Sequence[str], **_):
        print(self._c("  战报已保存：", DIM), flush=True)
        for p in paths:
            print(self._c(f"    {p}", DIM), flush=True)

    def _on_done(self, duration: float, rounds: int, winner: str | None, **_):
        print(
            BOLD
            + f"用时 {duration}s，共 {rounds} 轮，胜者：{winner or '（无）'}"
            + RESET,
            flush=True,
        )
