"""方案评审赛制：独立作答 → 匿名裁判评分 → 推荐与整合。"""

from __future__ import annotations

import json
import math
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .agent import CallResult
from .events import EventSink, NullSink

PERSPECTIVES = ("成本优先", "增长优先", "风险控制", "体验优先", "技术可行")
DIMENSIONS = ("可行性", "正确性", "完备性", "差异度")
PLAN_MARKERS = {
    "name": "方案名",
    "claim": "核心主张",
    "steps": "做法步骤",
    "cost": "代价",
    "risk": "风险",
    "diff": "与主流做法的差异",
}


@dataclass
class ReviewConfig:
    proposition: str
    timeout: float = 240
    out_dir: Path = Path("runs")
    retries: int = 1
    parallel_workers: int = 4
    criteria: list[str] = field(default_factory=list)
    background: str = ""
    constraints: list[str] = field(default_factory=list)
    diversify: bool = True
    run_id: str = ""


@dataclass
class ReviewResult:
    proposition: str
    started_at: str
    duration: float
    participants: list[dict[str, Any]]
    judge: dict[str, Any]
    labels: list[dict[str, Any]]
    answers: list[dict[str, Any]]
    scores: dict[str, dict[str, float]]
    totals: dict[str, float]
    ranking: list[str]
    recommended: str | None
    recommended_agent: str | None
    reasons: dict[str, str]
    risks: dict[str, str]
    rejections: dict[str, str]
    synthesis: str
    synthesis_sections: dict[str, list[str]]
    anomalies: list[dict[str, str]]
    absent: list[dict[str, str]]
    setup: dict[str, Any]
    budget: dict[str, Any]
    stop_reason: str = ""
    mode: str = "review"
    schema_version: int = 4

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clip(text: str, limit: int) -> str:
    value = str(text or "").strip()
    return value if len(value) <= limit else value[:limit] + "…（截断）"


def _agent_dict(agent: Any) -> dict[str, Any]:
    return {
        "name": agent.name,
        "label": getattr(agent, "label", ""),
        "model": str(getattr(agent, "model", getattr(agent, "label", "")) or ""),
        "config_id": int(getattr(agent, "config_id", 0) or 0),
        "path": str(getattr(agent, "path", "")),
    }


def _context(background: str, constraints: Sequence[str], criteria: Sequence[str]) -> str:
    parts: list[str] = []
    if background.strip():
        parts.append(f"【背景】\n{_clip(background, 1600)}")
    constraints = [item.strip() for item in constraints if item and item.strip()]
    if constraints:
        parts.append("【约束】\n" + "\n".join(f"- {item}" for item in constraints))
    criteria = [item.strip() for item in criteria if item and item.strip()]
    if criteria:
        parts.append("【附加评判要求】\n" + "\n".join(f"- {item}" for item in criteria))
    return "\n\n".join(parts)


def build_answer_prompt(
    *,
    proposition: str,
    perspective: str | None,
    background: str = "",
    constraints: Sequence[str] = (),
    criteria: Sequence[str] = (),
) -> str:
    perspective_block = (
        f"\n【指定视角】{perspective}\n"
        "请从这个视角出发形成方案，并在「与主流做法的差异」中说明你的取舍。\n"
        if perspective
        else ""
    )
    return f"""你在参加一场多模型方案评审。请独立提交一份可执行方案，不要假设或引用其他模型的答案。

【命题】
{proposition}

{_context(background, constraints, criteria)}
{perspective_block}
【输出格式】严格使用以下六段，不要开场白或结尾总结：
【方案名】<一个简洁名称>
【核心主张】<一句话说清方案判断>
【做法步骤】<3-5 步，每步一行>
【代价】<主要成本、资源或取舍>
【风险】<最重要的失败风险>
【与主流做法的差异】<必须明确写出与常见做法的不同>

【约束】
- 中文回答，总长度控制在 500-800 字。
- 必须给可执行细节，不要只写口号。
- 不讨论比赛规则，不自称 AI。"""


def build_judge_prompt(
    *,
    proposition: str,
    labels: Sequence[dict[str, Any]],
    background: str = "",
    constraints: Sequence[str] = (),
    criteria: Sequence[str] = (),
    retry: bool = False,
) -> str:
    blocks: list[str] = []
    for item in labels:
        plan = item["plan"]
        blocks.append(
            f"""【{item['label']}】视角：{item['perspective'] or '未分配'}
方案名：{plan.get('name') or '—'}
核心主张：{plan.get('claim') or '—'}
做法步骤：{plan.get('steps') or '—'}
代价：{plan.get('cost') or '—'}
风险：{plan.get('risk') or '—'}
与主流做法的差异：{plan.get('diff') or '—'}"""
        )
    retry_line = "\n上一次输出无法解析。这次只能输出一个合法 JSON 对象，不要代码块、不要解释。\n" if retry else ""
    return f"""你是独立方案评审裁判，不参与作答。请只按可验证性、完整性和差异度判断，不要偏爱长答案，也不要猜测方案作者。

【命题】
{proposition}

{_context(background, constraints, criteria)}
{retry_line}
【匿名方案】
{chr(10).join(blocks)}

【评分维度】固定为：可行性、正确性、完备性、差异度，每项 0-10 分，可含小数。

【任务】
1. 给每个方案四维评分。
2. 输出从高到低排名。
3. 选择一个推荐方案。
4. 给推荐方案写关键理由与主要风险。
5. 给每个非推荐方案写一句具体的「为什么不推荐」，不能只写“不如第一名”。
6. 推荐与排名第一不一致时，必须在 reasons 中说明原因。

只输出以下 JSON 结构，不要代码块：
{{"scores":{{"方案1":{{"可行性":8,"正确性":8,"完备性":7,"差异度":9}},"方案2":{{"可行性":7,"正确性":8,"完备性":6,"差异度":8}}}},"ranking":["方案1","方案2"],"recommended":"方案1","reasons":{{"方案1":"具体理由"}},"risks":{{"方案1":"主要风险"}},"rejections":{{"方案2":"具体的不推荐理由"}}}}"""


def build_synthesis_prompt(
    *,
    proposition: str,
    result: dict[str, Any],
    labels: Sequence[dict[str, Any]],
) -> str:
    label_blocks = "\n".join(
        f"- {item['label']}：{item['plan'].get('name') or '未命名'}；差异：{item['plan'].get('diff') or '—'}"
        for item in labels
    )
    return f"""你是独立方案评审裁判。请根据已完成的匿名评分，给出一份可直接执行的整合建议。

【命题】
{proposition}

【方案索引】
{label_blocks}

【评审结果 JSON】
{json.dumps(result, ensure_ascii=False)}

【输出格式】严格按以下五段输出，不要开场白：
【推荐结论】<明确推荐哪个方案，以及一句话原因>
【关键理由】<最多 3 条，每条一行，引用具体内容>
【必须吸收】<列出其他方案必须吸收的优点；没有就写“无跨方案补充”>
【整合方案】<最多 5 步，每步一行>
【前提与失效条件】<什么条件下建议成立，什么情况下失效>

总计不超过 700 字。"""


def parse_plan(text: str) -> tuple[dict[str, str], list[str]]:
    raw = str(text or "").strip()
    found: dict[str, str] = {}
    positions: list[tuple[int, int, str]] = []
    for key, label in PLAN_MARKERS.items():
        marker = f"【{label}】"
        at = raw.find(marker)
        if at >= 0:
            positions.append((at, at + len(marker), key))
    positions.sort()
    for index, (_, body_start, key) in enumerate(positions):
        body_end = positions[index + 1][0] if index + 1 < len(positions) else len(raw)
        found[key] = raw[body_start:body_end].strip()
    missing = [PLAN_MARKERS[key] for key in PLAN_MARKERS if not found.get(key)]
    return found, missing


def _iter_objects(text: str):
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
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    value = json.loads(text[start:index + 1])
                except json.JSONDecodeError:
                    value = None
                if isinstance(value, dict):
                    yield value


def parse_judgement(
    text: str, valid_labels: Sequence[str]
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    anomalies: list[dict[str, str]] = []
    payload = next(iter(_iter_objects(text)), None)
    if not isinstance(payload, dict):
        return None, [{"code": "judge_json", "detail": "裁判未返回可解析 JSON"}]
    valid = set(valid_labels)
    raw_scores = payload.get("scores")
    if not isinstance(raw_scores, dict):
        return None, [{"code": "judge_scores", "detail": "裁判 JSON 缺少 scores"}]

    scores: dict[str, dict[str, float]] = {}
    for label, dims in raw_scores.items():
        if label not in valid or not isinstance(dims, dict):
            anomalies.append({"code": "unknown_label", "detail": f"忽略未知标签：{label}"})
            continue
        clean: dict[str, float] = {}
        for dim in DIMENSIONS:
            if dim not in dims:
                anomalies.append({"code": "missing_dimension", "detail": f"{label} 缺少 {dim}"})
                continue
            try:
                value = float(dims[dim])
            except (TypeError, ValueError):
                anomalies.append({"code": "invalid_dimension", "detail": f"{label} {dim} 非数字"})
                continue
            if value < 0 or value > 10:
                anomalies.append({"code": "clamped_dimension", "detail": f"{label} {dim} 已截断"})
            clean[dim] = round(max(0.0, min(10.0, value)), 2)
        if clean:
            scores[label] = clean

    totals = {
        label: round(sum(dims.values()) / len(dims), 1)
        for label, dims in scores.items()
        if dims
    }
    ranking = [
        label for label in payload.get("ranking", [])
        if isinstance(label, str) and label in valid and label in scores
    ]
    ranking = list(dict.fromkeys(ranking))
    for label in sorted(totals, key=lambda item: -totals[item]):
        if label not in ranking:
            ranking.append(label)
    recommended = payload.get("recommended")
    if recommended not in valid or recommended not in scores:
        anomalies.append({"code": "invalid_recommended", "detail": "推荐标签无效，改用总分第一"})
        recommended = ranking[0] if ranking else None
    if recommended and ranking and recommended != ranking[0]:
        anomalies.append(
            {"code": "recommend_mismatch", "detail": "推荐方案与评分第一不一致"}
        )
    reasons = payload.get("reasons") if isinstance(payload.get("reasons"), dict) else {}
    risks = payload.get("risks") if isinstance(payload.get("risks"), dict) else {}
    rejections = payload.get("rejections") if isinstance(payload.get("rejections"), dict) else {}
    if recommended and not str(reasons.get(recommended) or "").strip():
        anomalies.append({"code": "missing_reason", "detail": "推荐方案缺少关键理由"})
    for label in ranking:
        if label == recommended:
            continue
        reason = str(rejections.get(label) or "").strip()
        if len(reason) < 15:
            anomalies.append({"code": "weak_rejection", "detail": f"{label} 的否决理由不足"})

    return {
        "scores": scores,
        "totals": totals,
        "ranking": ranking,
        "recommended": recommended,
        "reasons": {str(key): str(value) for key, value in reasons.items()},
        "risks": {str(key): str(value) for key, value in risks.items()},
        "rejections": {str(key): str(value) for key, value in rejections.items()},
    }, anomalies


def parse_synthesis(text: str) -> dict[str, list[str]]:
    labels = {
        "recommendation": "推荐结论",
        "reasons": "关键理由",
        "absorb": "必须吸收",
        "plan": "整合方案",
        "conditions": "前提与失效条件",
    }
    raw = str(text or "")
    positions = []
    for key, label in labels.items():
        marker = f"【{label}】"
        at = raw.find(marker)
        if at >= 0:
            positions.append((at, at + len(marker), key))
    positions.sort()
    out: dict[str, list[str]] = {}
    for index, (_, start, key) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(raw)
        lines = [
            re.sub(r"^[-·•\d.、\s]+", "", line).strip()
            for line in raw[start:end].splitlines()
        ]
        out[key] = [line for line in lines if line]
    return out


class ReviewArena:
    def __init__(
        self,
        agents: Sequence[Any],
        judge: Any,
        cfg: ReviewConfig,
        sink: EventSink | None = None,
    ):
        if len(agents) < 2 or len(agents) > 8:
            raise ValueError("方案评审需要 2-8 个参赛模型")
        participant_ids = {int(getattr(agent, "config_id", 0) or 0) for agent in agents}
        judge_id = int(getattr(judge, "config_id", 0) or 0)
        if judge_id and judge_id in participant_ids:
            raise ValueError("裁判不能同时参赛")
        self.agents = list(agents)
        self.judge = judge
        self.cfg = cfg
        self.sink: EventSink = sink or NullSink()
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.run_dir = (Path(cfg.out_dir) / stamp).resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.cancel_hook: Any = None
        self._usage: dict[str, int] = {"calls": 0, "tokens_estimate": 0}
        self._usage_per_model: dict[str, dict[str, int]] = {}
        self._cancelled = False

    def _record_usage(self, agent: Any, result: CallResult) -> None:
        self._usage["calls"] += 1
        tokens = int(result.usage.get("total_tokens") or 0)
        if not tokens:
            tokens = int(result.usage.get("prompt_tokens") or 0) + int(
                result.usage.get("completion_tokens") or 0
            )
        self._usage["tokens_estimate"] += tokens
        per = self._usage_per_model.setdefault(agent.name, {"calls": 0, "tokens_estimate": 0})
        per["calls"] += 1
        per["tokens_estimate"] += tokens

    def _is_cancelled(self) -> bool:
        hook = self.cancel_hook
        if hook is None:
            return False
        try:
            return bool(hook.is_set())
        except AttributeError:
            return bool(hook)

    def run(self) -> ReviewResult:
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        t0 = time.monotonic()
        perspectives = [
            PERSPECTIVES[index % len(PERSPECTIVES)] if self.cfg.diversify else None
            for index in range(len(self.agents))
        ]
        self.sink.emit(
            "run_start",
            mode="review",
            proposition=self.cfg.proposition,
            agents=[{**_agent_dict(agent), "perspective": perspectives[index]}
                    for index, agent in enumerate(self.agents)],
            judge=_agent_dict(self.judge),
            diversify=self.cfg.diversify,
            stage="answers",
        )
        self.sink.emit("review_phase", phase="answers", label="独立作答")

        answers = self._collect_answers(perspectives)
        valid = [item for item in answers if not item.get("error")]
        absent = [
            {"agent": item["agent"], "reason": item.get("error") or "返回内容为空"}
            for item in answers if item.get("error")
        ]
        for item in absent:
            self.sink.emit("review_absent", **item)
        if not valid:
            raise ValueError("全部参赛模型作答失败，无法进入评审")
        if self._is_cancelled():
            return self._write(
                self._result(
                    started, t0, answers, [], [], [], None, {}, {}, {}, "", {}, absent, "用户中止"
                )
            )

        labels = self._make_labels(valid)
        self.sink.emit(
            "review_labels",
            labels=[
                {
                    "label": item["label"],
                    "agent": item["agent"],
                    "perspective": item["perspective"],
                }
                for item in labels
            ],
        )
        self.sink.emit("review_phase", phase="judging", label="匿名评审")
        judged, anomalies = self._judge(labels)
        if judged is None:
            empty = self._result(
                started, t0, answers, labels, [], [], None, {}, {}, {}, "", {}, absent,
                "评审未完成",
            )
            empty.anomalies = anomalies
            return self._write(empty)

        recommended = judged["recommended"]
        label_map = {item["label"]: item for item in labels}
        recommended_agent = (
            str(label_map.get(recommended, {}).get("agent") or "") or None
        )
        self.sink.emit(
            "review_judge_done",
            scores=judged["scores"],
            totals=judged["totals"],
            ranking=judged["ranking"],
            recommended=recommended,
            recommended_agent=recommended_agent,
            reasons=judged["reasons"],
            risks=judged["risks"],
            rejections=judged["rejections"],
            anomalies=anomalies,
        )

        if self._is_cancelled():
            return self._write(
                self._result(
                    started, t0, answers, labels, judged["scores"], judged["ranking"],
                    recommended, judged["reasons"], judged["risks"], judged["rejections"],
                    "", {}, absent, "用户中止",
                )
            )

        self.sink.emit("review_phase", phase="synthesis", label="整合建议")
        synthesis, synthesis_error = self._synthesize(labels, judged)
        if synthesis_error:
            anomalies.append({"code": "synthesis_failed", "detail": synthesis_error})
        sections = parse_synthesis(synthesis)
        self.sink.emit(
            "review_synthesis_done",
            text=synthesis,
            sections=sections,
            error=synthesis_error,
        )
        result = self._result(
            started,
            t0,
            answers,
            labels,
            judged["scores"],
            judged["ranking"],
            recommended,
            judged["reasons"],
            judged["risks"],
            judged["rejections"],
            synthesis,
            sections,
            absent,
            "",
            recommended_agent=recommended_agent,
            anomalies=anomalies,
        )
        return self._write(result)

    def _collect_answers(self, perspectives: Sequence[str | None]) -> list[dict[str, Any]]:
        rows = [
            {
                "agent": agent.name,
                "perspective": perspectives[index],
                "plan": {},
                "text": "",
                "elapsed": 0.0,
                "error": None,
                "struct_complete": False,
                "missing": [],
            }
            for index, agent in enumerate(self.agents)
        ]
        by_name = {row["agent"]: row for row in rows}

        def task(index: int, agent: Any) -> tuple[str, CallResult]:
            self.sink.emit(
                "review_answer_start",
                agent=agent.name,
                perspective=perspectives[index],
            )
            def on_output(chunk: str) -> None:
                self.sink.emit(
                    "review_answer_progress",
                    agent=agent.name,
                    text=chunk,
                )
            result = agent.ask(
                build_answer_prompt(
                    proposition=self.cfg.proposition,
                    perspective=perspectives[index],
                    background=self.cfg.background,
                    constraints=self.cfg.constraints,
                    criteria=self.cfg.criteria,
                ),
                timeout=self.cfg.timeout,
                retries=self.cfg.retries,
                on_output=on_output,
            )
            self._record_usage(agent, result)
            return agent.name, result

        workers = max(1, min(self.cfg.parallel_workers, len(self.agents)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(task, index, agent): agent
                for index, agent in enumerate(self.agents)
            }
            for future in as_completed(futures):
                agent = futures[future]
                try:
                    name, result = future.result()
                except Exception as exc:
                    name, result = agent.name, CallResult(error=str(exc))
                row = by_name[name]
                row["elapsed"] = round(result.elapsed, 1)
                if result.error or not result.text.strip():
                    row["error"] = result.error or "返回内容为空"
                else:
                    plan, missing = parse_plan(result.text)
                    row.update(
                        text=result.text.strip(),
                        plan=plan,
                        struct_complete=not missing,
                        missing=missing,
                    )
                self.sink.emit("review_answer_done", **row)
        return rows

    def _make_labels(self, answers: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        shuffled = list(answers)
        random.Random(self.cfg.run_id or self.cfg.proposition).shuffle(shuffled)
        labels = []
        for index, item in enumerate(shuffled, 1):
            plan = dict(item.get("plan") or {})
            text = item.get("text") or ""
            for agent in self.agents:
                if agent.name:
                    text = text.replace(agent.name, "该方案")
                    plan = {key: str(value).replace(agent.name, "该方案") for key, value in plan.items()}
            labels.append(
                {
                    "label": f"方案{index}",
                    "agent": item["agent"],
                    "perspective": item.get("perspective"),
                    "plan": plan,
                    "text": text,
                }
            )
        return labels

    def _judge(
        self, labels: Sequence[dict[str, Any]]
    ) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
        names = [item["label"] for item in labels]
        all_anomalies: list[dict[str, str]] = []
        self.sink.emit("review_judge_start", retried=False)
        for attempt in range(2):
            self.sink.emit("thinking", agent=self.judge.name, role="匿名评审")
            result = self.judge.ask(
                build_judge_prompt(
                    proposition=self.cfg.proposition,
                    labels=labels,
                    background=self.cfg.background,
                    constraints=self.cfg.constraints,
                    criteria=self.cfg.criteria,
                    retry=attempt > 0,
                ),
                timeout=min(self.cfg.timeout, 120),
                retries=0,
            )
            self._record_usage(self.judge, result)
            if not result.error:
                parsed, anomalies = parse_judgement(result.text, names)
                all_anomalies.extend(anomalies)
                if parsed:
                    return parsed, all_anomalies
            else:
                all_anomalies.append({"code": "judge_call", "detail": result.error})
            if attempt == 0:
                self.sink.emit("review_judge_retry")
        return None, all_anomalies

    def _synthesize(
        self, labels: Sequence[dict[str, Any]], judged: dict[str, Any]
    ) -> tuple[str, str]:
        self.sink.emit("thinking", agent=self.judge.name, role="整合建议")
        result = self.judge.ask(
            build_synthesis_prompt(
                proposition=self.cfg.proposition,
                result=judged,
                labels=labels,
            ),
            timeout=min(self.cfg.timeout, 120),
            retries=0,
        )
        self._record_usage(self.judge, result)
        if result.error:
            return "", f"整合建议未生成：{result.error}"
        return result.text.strip(), ""

    def _result(
        self,
        started: str,
        t0: float,
        answers: Sequence[dict[str, Any]],
        labels: Sequence[dict[str, Any]],
        scores: dict[str, dict[str, float]],
        ranking: Sequence[str],
        recommended: str | None,
        reasons: dict[str, str],
        risks: dict[str, str],
        rejections: dict[str, str],
        synthesis: str,
        sections: dict[str, list[str]],
        absent: Sequence[dict[str, str]],
        stop_reason: str,
        *,
        recommended_agent: str | None = None,
        anomalies: Sequence[dict[str, str]] = (),
    ) -> ReviewResult:
        totals = {
            label: round(sum(dims.values()) / len(dims), 1)
            for label, dims in scores.items()
            if dims
        }
        budget = {
            "calls": self._usage["calls"],
            "tokens_estimate": self._usage["tokens_estimate"],
            "wall_clock": round(time.monotonic() - t0, 1),
            "per_model": dict(self._usage_per_model),
        }
        public_labels = [
            {
                "label": item["label"],
                "agent": item["agent"],
                "perspective": item["perspective"],
            }
            for item in labels
        ]
        return ReviewResult(
            proposition=self.cfg.proposition,
            started_at=started,
            duration=round(time.monotonic() - t0, 1),
            participants=[_agent_dict(agent) for agent in self.agents],
            judge=_agent_dict(self.judge),
            labels=public_labels,
            answers=list(answers),
            scores=scores,
            totals=totals,
            ranking=list(ranking),
            recommended=recommended,
            recommended_agent=recommended_agent,
            reasons=reasons,
            risks=risks,
            rejections=rejections,
            synthesis=synthesis,
            synthesis_sections=sections,
            anomalies=list(anomalies),
            absent=list(absent),
            setup={
                "mode": "review",
                "model_ids": [
                    int(getattr(agent, "config_id", 0) or 0)
                    for agent in self.agents
                ],
                "judge_model_id": int(getattr(self.judge, "config_id", 0) or 0),
                "vote_mode": "eliminate",
                "speech_mode": "parallel_buffered",
                "timeout": self.cfg.timeout,
                "background": self.cfg.background,
                "constraints": list(self.cfg.constraints),
                "criteria": list(self.cfg.criteria),
                "diversify": self.cfg.diversify,
            },
            budget=budget,
            stop_reason=stop_reason,
        )

    def _write(self, result: ReviewResult) -> ReviewResult:
        json_path = self.run_dir / "transcript.json"
        md_path = self.run_dir / "review.md"
        json_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_path.write_text(self._markdown(result), encoding="utf-8")
        budget = result.budget
        self.sink.emit("budget", **budget)
        self.sink.emit("saved", paths=[str(md_path), str(json_path)])
        self.sink.emit(
            "done",
            duration=result.duration,
            rounds=0,
            winner=result.recommended_agent,
            run_dir=str(self.run_dir),
        )
        return result

    @staticmethod
    def _markdown(result: ReviewResult) -> str:
        lines = [
            "# 多模型方案评审\n",
            f"- **命题**：{result.proposition}",
            f"- **裁判**：{result.judge.get('name')} · {result.judge.get('label')}",
            f"- **推荐**：{result.recommended_agent or '—'}（{result.recommended or '—'}）",
            f"- **耗时**：{result.duration}s",
            f"- **用量**：{result.budget.get('calls', 0)} 次调用 · "
            f"约 {result.budget.get('tokens_estimate', 0)} tokens",
            "",
            "## 方案对比\n",
            "| 方案 | 模型 | 视角 | " + " | ".join(DIMENSIONS) + " | 总分 |",
            "| --- | --- | --- | " + " | ".join("---" for _ in DIMENSIONS) + " | --- |",
        ]
        label_map = {item["label"]: item for item in result.labels}
        for label in result.ranking or list(result.scores):
            mapping = label_map.get(label, {})
            dims = result.scores.get(label, {})
            cells = " | ".join(str(dims.get(dim, "—")) for dim in DIMENSIONS)
            lines.append(
                f"| {label} | {mapping.get('agent', '—')} | "
                f"{mapping.get('perspective') or '未分配'} | {cells} | "
                f"{result.totals.get(label, '—')} |"
            )
        if result.synthesis:
            lines.extend(["", "## 推荐与整合", "", result.synthesis])
        if result.absent:
            lines.extend(["", "## 缺席方案", ""])
            lines.extend(f"- {item['agent']}：{item['reason']}" for item in result.absent)
        lines.extend(
            [
                "",
                "## 判定口径",
                "",
                "- 裁判仅看到匿名标签与乱序方案。",
                "- 单裁判存在主观偏差，样本量为 1。",
                "- 本页评分仅在本模式内可比，不应与淘汰辩论混排。",
            ]
        )
        return "\n".join(lines)
