"""战报落地：完整 JSON（可程序化分析）+ Markdown（可读复盘）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:  # 避免与 moderator 循环导入
    from .moderator import ArenaResult

MODE_LABEL = {
    "eliminate": "淘汰制（投观点最站不住的，票多者出局）",
    "support": "评选制（投最该留下的，票少者出局）",
}


def _stage_note(stage: str) -> str:
    if stage == "main":
        return ""
    if stage.startswith("tiebreak-"):
        return f"（第 {stage.removeprefix('tiebreak-')} 次加赛）"
    return f"（{stage}）"


def _md(result: ArenaResult) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"# 多智能体辩论战报\n")
    add(f"- **命题**：{result.proposition}")
    add("- **模式**：自定义模式")
    add(f"- **规则**：{MODE_LABEL.get(result.vote_mode, result.vote_mode)}")
    add(f"- **胜出标准**：{result.win_condition}")
    add(f"- **开始时间**：{result.started_at}")
    add(f"- **耗时**：{result.duration}s")
    add(f"- **参赛者**：{', '.join(p['name'] for p in result.participants)}")
    add(f"- **最终存活**：{result.winner or '（无）'}")
    add(f"- **发言方式**：{result.speech_mode}")
    if result.converged:
        add("- **共识**：至少有两位存活者的立场趋于一致")
    if result.stop_reason:
        add(f"- **中止原因**：{result.stop_reason}")
    budget = result.budget or {}
    if budget:
        add(
            f"- **运行用量**：{budget.get('calls', 0)} 次调用 · 约 {budget.get('tokens_estimate', 0)} tokens"
        )
    add("")

    add("## 参赛阵容\n")
    add("| 名字 | 模型 | 接口 |")
    add("| --- | --- | --- |")
    for p in result.participants:
        add(f"| `{p['name']}` | {p['label']} | `{p['path']}` |")
    add("")

    for r in result.rounds:
        add(f"## Round {r.no}\n")
        add(f"发言顺序：{' → '.join(r.order)}\n")
        for s in r.speeches:
            add(f"### {s.agent}（{s.role}，{s.elapsed:.1f}s）\n")
            if s.error:
                add(f"> 调用失败：{s.error}\n")
            else:
                add(s.text.strip() + "\n")

        if r.votes:
            add("### 投票\n")
            add("| 投票者 | 投给 | 理由 |")
            add("| --- | --- | --- |")
            for v in r.votes:
                marks = ("（评审）" if v.is_judge else "") + _stage_note(v.stage)
                who = v.voter + marks
                add(f"| {who} | {v.target or '弃权'} | {(v.reason or v.error or '').replace('|', '/')} |")
            add("")
            if r.counts:
                summary = "，".join(f"{k} {n:g} 票" for k, n in sorted(r.counts.items(), key=lambda x: -x[1]))
                add(f"计票：{summary}\n")
            breakdown = r.weight_breakdown or {}
            if breakdown:
                add(
                    f"票权分布：存活者 {breakdown.get('alive_votes', 0)} 票（权重 1.0）"
                    f" · 评审 {breakdown.get('judge_votes', 0)} 票"
                    f"（权重 {breakdown.get('judge_weight', 0.5)}）\n"
                )
            if r.scores:
                add("### 评分矩阵\n")
                dims = sorted({d for dims in r.scores.values() for d in dims})
                add("| 模型 | " + " | ".join(dims) + " | 均分 |")
                add("| --- | " + " | ".join("---" for _ in dims) + " | --- |")
                for name, dims_map in sorted(
                    r.scores.items(),
                    key=lambda item: -(sum(item[1].values()) / max(1, len(item[1]))),
                ):
                    avg = sum(dims_map.values()) / max(1, len(dims_map))
                    cells = " | ".join(f"{dims_map.get(d, '—')}" for d in dims)
                    add(f"| {name} | {cells} | {avg:.1f} |")
                add("")
            if r.stance_spread is not None:
                add(f"立场离散度：{r.stance_spread}\n")

        if r.exits:
            for e in r.exits:
                add(f"> ⚠ 技术性退赛：{e['agent']}（{e['reason']}）\n")
        if r.eliminated:
            tb = f"（{r.tiebreak}）" if r.tiebreak else ""
            add(f"### 淘汰：{r.eliminated} {r.votes_received} 票{tb}\n")

    if result.claims:
        add("## 主张存活表\n")
        add("| # | 主张 | 提出者 | 提出轮 | 被谁挑战 | 结局 |")
        add("| --- | --- | --- | --- | --- | --- |")
        for c in result.claims:
            challengers = "、".join(c.get("challengers") or []) or "—"
            add(
                f"| {c.get('claim_id')} | {c.get('text')} | {c.get('author')} | "
                f"{c.get('round')} | {challengers} | {c.get('final_status')} |"
            )
        add("")

    if result.final_answer:
        add("## 最终结论\n")
        add(f"**{result.winner}**\n")
        add(result.final_answer.strip() + "\n")

    return "\n".join(lines)


def write_all(result: ArenaResult, run_dir: Path) -> Sequence[Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "transcript.json"
    md_path = run_dir / "debate.md"

    json_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path.write_text(_md(result), encoding="utf-8")
    return [md_path, json_path]
