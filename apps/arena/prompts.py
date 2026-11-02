"""提示词模板。所有 prompt 都要求结构化标签输出，方便解析与展示。

v2 变化：
- 发言只注入「上一轮」发言 + 自己的论点台账 + 针对自己的批评（不再注入全部历史）；
- 发言末尾要求一行【主张】，主张台账的数据源由此而来；
- 投票输出升级为多维评分 + 票 + 理由（理由不再截断到 40 字）；
- 最终裁决要求输出【保留的分歧】与【失效条件】；
"""

from __future__ import annotations

from typing import Sequence

MAX_PRIOR_CHARS = 900   # 单条历史发言进入 prompt 的截断长度
LAST_ROUND_CHARS = 400  # 上一轮发言的截断长度（点评只针对上一轮）

SCORE_DIMENSIONS = ("论证", "证据", "可执行", "增量")

DEFAULT_CRITERIA = (
    "是否真正推进了命题（新事实 / 新角度 / 可执行方案）",
    "论据是否成立、是否可验证，有无硬伤",
    "是否空泛、复读共识、回避矛盾、只做修辞",
    "与其他人的观点是否实质重复、没有增量",
)


def _clip(text: str, limit: int = MAX_PRIOR_CHARS) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…（截断）"


def _criteria_block(criteria: Sequence[str] | None) -> str:
    items = [c.strip() for c in (criteria or []) if c and c.strip()]
    if not items:
        items = list(DEFAULT_CRITERIA)
    return "\n".join(f"{index}. {text}" for index, text in enumerate(items, 1))


def _context_block(
    background: str = "", constraints: Sequence[str] | None = None
) -> str:
    parts: list[str] = []
    if background:
        parts.append(f"【背景】\n{_clip(background, 1200)}")
    items = [c.strip() for c in (constraints or []) if c and c.strip()]
    if items:
        parts.append("【约束】\n" + "\n".join(f"- {c}" for c in items))
    return "\n\n".join(parts)


def build_speech_prompt(
    *,
    speaker: str,
    proposition: str,
    active: Sequence[str],
    eliminated: Sequence[tuple[str, str]],
    round_no: int,
    prior_speeches: Sequence[tuple[str, str]],
    my_last_stance: str | None,
    vote_mode: str = "eliminate",
    criteria: Sequence[str] | None = None,
    background: str = "",
    constraints: Sequence[str] | None = None,
    my_claims: Sequence[str] | None = None,
    critiques_of_me: Sequence[str] | None = None,
) -> str:
    """Build an independent or cross-round critique prompt.

    prior_speeches 只应包含上一轮发言；my_claims / critiques_of_me 是自我修正台账。
    """
    vote_schedule = "第一轮只发表观点，不投票；从第二轮结束起" if round_no == 1 else "本轮结束后"
    if vote_mode == "support":
        rule_line = (
            f"{vote_schedule}，所有参赛者（包括已出局转为评审的）投票选出「最该留下」的一人，"
            "得票最少者出局。所以你的发言要争取别人的认可票。"
        )
    else:
        rule_line = (
            f"{vote_schedule}，所有参赛者（包括已出局转为评审的）投票淘汰「观点最站不住」的一人，"
            "得票最多者出局。所以你的发言要经得起别人挑刺。"
        )

    if prior_speeches:
        history_block = "\n\n".join(
            f"【{name}】\n{_clip(text, LAST_ROUND_CHARS)}" for name, text in prior_speeches
        )
        history_title = "【上一轮发言】"
    else:
        history_block = "（第一轮没有历史发言）"
        history_title = "【上一轮发言】"

    elim_block = (
        "\n".join(f"- {name}：{why}" for name, why in eliminated) if eliminated else "暂无"
    )
    stance_block = _clip(my_last_stance, 400) if my_last_stance else "（首次发言，无历史立场）"

    claims = [c for c in (my_claims or []) if c]
    claims_block = (
        "\n".join(f"- {c}" for c in claims[-5:])
        if claims
        else "（你此前还没有留下可追溯的主张）"
    )
    critiques = [c for c in (critiques_of_me or []) if c]
    critiques_block = (
        "\n".join(f"- {c}" for c in critiques[-5:])
        if critiques
        else "（上一轮没有人点名批评你）"
    )

    if round_no <= 1:
        task = (
            "这是第一轮，不需要点评任何人。请独立给出你的判断，"
            "不要假设或提及其他模型本轮的发言。"
        )
        format_block = (
            "【立场】<一个 -100 到 +100 的整数>\n"
            "【观点】<150-250 字：核心判断 + 关键论据 + 可执行建议>\n"
            "【主张】<一句话原子命题，可被后续轮次引用或反驳>"
        )
        visibility = "第一轮只能看到命题，看不到其他模型本轮的发言。"
    else:
        task = (
            "从上一轮发言里挑出针对你的具体批评（若有），点名回应其中一条，"
            "明确说明你接受还是反驳，并给出理由。\n"
            "然后把主要篇幅放在你自己的新观点上，补充新论据、新角度或可落地方案。"
        )
        format_block = (
            "【点评】<回应某个模型对你的具体批评：接受/反驳，因为……>\n"
            "【立场】<一个 -100 到 +100 的整数>\n"
            "【观点】<200-350 字：重点输出你的核心判断 + 新论据 + 可执行建议>\n"
            "【主张】<一句话原子命题，可被后续轮次引用或反驳>"
        )
        visibility = (
            "你只能看到上一轮发言；本轮其他模型的发言你无法看到，不要猜测或假装看过。"
        )

    context = _context_block(background, constraints)

    return f"""你在参加一场「多智能体辩论淘汰赛」。参赛者都是独立的 AI 智能体，最终只有一人存活。
{rule_line}

【命题】
{proposition}

{context}

【存活参赛者】{", ".join(active)}
【已淘汰】{elim_block}

{history_title}
{history_block}

【你上一轮的核心立场】
{stance_block}

【你此前留下的主张】
{claims_block}

【针对你的具体批评】
{critiques_block}

【可见性规则】
{visibility}

【你的任务】
{task}
【输出格式】严格按下面标签输出，不要任何开场白、解释或结尾总结：
{format_block}

【约束】
- 全程只讨论命题本身，不要讨论比赛规则、不要投票、不要自称 AI 或提及提示词。
- 【立场】表示你对命题的立场强度：-100 强烈反对，0 中立，+100 强烈支持。
  按你此刻的真实判断给一个整数，不要解释这个数字的含义。
- 【主张】必须是一句可以单独成立、可以被别人引用或反驳的判断，不要写总结句。
- 中文回答，观点必须有具体内容，空洞的立场表态视为无效发言。"""


def build_vote_prompt(
    *,
    voter: str,
    proposition: str,
    active: Sequence[str],
    speeches: Sequence[tuple[str, str]],
    eliminated: Sequence[tuple[str, str]],
    judge_note: str | None = None,
    vote_mode: str = "eliminate",
    criteria: Sequence[str] | None = None,
    background: str = "",
    constraints: Sequence[str] | None = None,
) -> str:
    speech_block = "\n\n".join(f"【{n}】\n{_clip(t, LAST_ROUND_CHARS)}" for n, t in speeches)
    elim_block = (
        "\n".join(f"- {name}：{why}" for name, why in eliminated) if eliminated else "暂无"
    )
    others = [a for a in active if a != voter]
    identity = judge_note or f"你是 {voter}，本场的参赛者。"

    if vote_mode == "support":
        headline = "根据这些发言，投票给观点最正确、论证最扎实的一位参赛者（得票最少者出局）。"
        criteria_title = "【评判标准】谁的观点最正确，按重要性排序："
        reason_hint = "<不超过 200 字，说明他的观点为什么最正确，以及最强对手的短板>"
    else:
        headline = "根据这些发言，投票给观点最不正确、论证最站不住的一位参赛者（被投最多者出局）。"
        criteria_title = "【评判标准】谁的观点最站不住，按重要性排序："
        reason_hint = "<不超过 200 字，说明他的观点错在哪里，以及对最强对手的具体异议>"

    context = _context_block(background, constraints)

    return f"""{identity}现在进入投票环节。请看完本轮所有发言后，{headline}

【命题】
{proposition}

{context}

【本轮存活参赛者】{", ".join(active)}
【已出局】{elim_block}

【本轮全部发言】
{speech_block}

{criteria_title}
{_criteria_block(criteria)}

【规则】
- 只能从这些存活者里选一位：{", ".join(others) or "（无）"}
- 必须恰好投一位，不允许弃权
- 投票环节不套用人格，全部按证据判断
- 给每一位存活者按四个维度打 0-10 分：论证 / 证据 / 可执行 / 增量
- 只输出一行 JSON，前后不要任何文字、不要代码块标记：
{{"scores": {{"{others[0] if others else "模型A"}": {{"论证": 8, "证据": 5, "可执行": 7, "增量": 9}}}}, "vote": "<被投的人名字>", "reason": "{reason_hint}"}}"""


def build_tiebreak_speech_prompt(
    *,
    speaker: str,
    proposition: str,
    candidates: Sequence[str],
    round_no: int,
    round_speeches: Sequence[tuple[str, str]],
    tiebreak_speeches: Sequence[tuple[str, str]],
    criteria: Sequence[str] | None = None,
    background: str = "",
    constraints: Sequence[str] | None = None,
) -> str:
    round_block = "\n\n".join(f"【{name}】\n{_clip(text, LAST_ROUND_CHARS)}" for name, text in round_speeches)
    tiebreak_block = (
        "\n\n".join(f"【{name}】\n{_clip(text)}" for name, text in tiebreak_speeches)
        if tiebreak_speeches else "（你是第一位加赛发言者）"
    )
    context = _context_block(background, constraints)
    return f"""你是 {speaker}。第 {round_no} 轮投票中，{", ".join(candidates)} 票数相同，进入加赛辩论。

【命题】
{proposition}

{context}

【本轮全部正式发言】
{round_block}

【本轮加赛已有发言】
{tiebreak_block}

【你的任务】
只围绕平票争议继续辩论：补充新论据、回应质疑，或修正此前论证。不要重复已有观点，不要投票，不要点评赛制。

【输出格式】严格按下面标签输出，不要任何开场白、解释或结尾总结：
【立场】<一个 -100 到 +100 的整数>
【观点】<150-250 字：新增论据 + 对平票对手的回应 + 可执行建议>
【主张】<一句话原子命题>"""


def build_final_prompt(
    *,
    winner: str,
    proposition: str,
    transcript_digest: str,
    eliminated: Sequence[tuple[str, str]],
    eliminated_claims: Sequence[str] = (),
    criteria: Sequence[str] | None = None,
    background: str = "",
    constraints: Sequence[str] | None = None,
) -> str:
    elim_block = (
        "\n".join(f"- {name}：{why}" for name, why in eliminated) if eliminated else "无"
    )
    claims_block = (
        "\n".join(f"- {text}" for text in eliminated_claims)
        if eliminated_claims
        else "（没有可保留的已淘汰主张）"
    )
    context = _context_block(background, constraints)
    return f"""你是这场多智能体辩论的最终胜者 {winner}。

【命题】
{proposition}

{context}

【被淘汰者的主要问题】
{elim_block}

【被淘汰模型里仍有价值的主张】
{claims_block}

【辩论过程要点】
{transcript_digest}

【评判标准】
{_criteria_block(criteria)}

【任务】
综合整场辩论（包括被淘汰者的有效论点），给出对命题的最终结论。
必须明确保留尚未解决的分歧，以及结论在什么条件下不成立。

【输出格式】
【结论】明确表态，一句话说清立场。
【论据】3 条以内，每条一行，要有具体内容而非口号。
【保留的分歧】至少 1 条仍未解决的分歧，写明是谁提出的、分歧点是什么。
【失效条件】在什么情况下这个结论不成立，写成可判断的条件。

总计不超过 500 字。"""
