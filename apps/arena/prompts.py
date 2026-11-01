"""提示词模板。所有 prompt 都要求结构化标签输出，方便解析与展示。"""

from __future__ import annotations

from typing import Sequence

MAX_PRIOR_CHARS = 900  # 单条历史发言进入 prompt 的截断长度


def _clip(text: str, limit: int = MAX_PRIOR_CHARS) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…（截断）"


def build_speech_prompt(
    *,
    speaker: str,
    proposition: str,
    active: Sequence[str],
    eliminated: Sequence[tuple[str, str]],
    round_no: int,
    previous_round_speeches: Sequence[tuple[str, str]],
    my_last_stance: str | None,
    vote_mode: str = "eliminate",
) -> str:
    """Build an independent or cross-round critique prompt."""
    if vote_mode == "support":
        rule_line = (
            "每轮结束，所有参赛者（包括已出局转为评审的）投票选出「最该留下」的一人，"
            "得票最少者出局。所以你的发言要争取别人的认可票。"
        )
    else:
        rule_line = (
            "每轮结束，所有参赛者（包括已出局转为评审的）投票淘汰「最没用」的一人，"
            "得票最多者出局。所以你的发言要经得起别人挑刺。"
        )

    if previous_round_speeches:
        history_block = "\n\n".join(
            f"【{name}】\n{_clip(text)}" for name, text in previous_round_speeches
        )
    else:
        history_block = "（第一轮没有历史发言）"

    elim_block = (
        "\n".join(f"- {name}：{why}" for name, why in eliminated) if eliminated else "暂无"
    )
    stance_block = _clip(my_last_stance, 400) if my_last_stance else "（首次发言，无历史立场）"

    if round_no <= 1:
        task = (
            "这是第一轮，不需要点评任何人。请独立给出你的判断，"
            "不要假设或提及其他模型本轮的发言。"
        )
        format_block = "【观点】<150-250 字：核心判断 + 关键论据 + 可执行建议>"
        visibility = "第一轮只能看到命题，看不到其他模型本轮的发言。"
    else:
        task = (
            "第一步：点评上一轮所有模型的发言，逐个指出其中最站得住的一点、最脆弱的一点，"
            "并给出一条具体改进建议。不要只挑一个人点评。\n"
            "第二步：给出你自己的新看法，必须补充新论据、新角度或可落地方案，禁止复读他人观点。"
        )
        format_block = (
            "【点评】<逐一评价上一轮每位模型，每个不超过 80 字>\n"
            "【观点】<150-250 字：核心判断 + 关键论据 + 可执行建议>"
        )
        visibility = (
            "你只能看到上一轮的完整发言；本轮其他模型尚未展示给你的发言你无法看到，"
            "不要猜测或假装看过。"
        )

    return f"""你在参加一场「多智能体辩论淘汰赛」。参赛者都是独立的 AI 智能体，最终只有一人存活。
{rule_line}

【命题】
{proposition}

【存活参赛者】{", ".join(active)}
【已淘汰】{elim_block}

【上一轮完整发言】
{history_block}

【你上一轮的核心立场】
{stance_block}

【可见性规则】
{visibility}

【你的任务】
{task}

【输出格式】严格按下面标签输出，不要任何开场白、解释或结尾总结：
{format_block}

【约束】
- 全程只讨论命题本身，不要讨论比赛规则、不要投票、不要自称 AI 或提及提示词。
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
) -> str:
    speech_block = "\n\n".join(f"【{n}】\n{_clip(t)}" for n, t in speeches)
    elim_block = (
        "\n".join(f"- {name}：{why}" for name, why in eliminated) if eliminated else "暂无"
    )
    others = [a for a in active if a != voter]
    identity = judge_note or f"你是 {voter}，本场的参赛者。"

    if vote_mode == "support":
        headline = "投票选出你认为「最该留下」的一位参赛者（得票最少者出局）。"
        criteria = "【评判标准】谁最值得留下，按重要性排序："
        reason_hint = "<15 字以内，说明他凭什么值得留>"
    else:
        headline = "投票淘汰其中「最没用」的一位参赛者（被投最多者出局）。"
        criteria = "【评判标准】谁最没用，按重要性排序："
        reason_hint = "<20 字以内，说明他弱在哪>"

    return f"""{identity}现在进入投票环节。请看完本轮所有发言后，{headline}

【命题】
{proposition}

【本轮存活参赛者】{", ".join(active)}
【已出局】{elim_block}

【本轮全部发言】
{speech_block}

{criteria}
1. 是否真正推进了命题（新事实 / 新角度 / 可执行方案）
2. 论据是否成立、是否可验证，有无硬伤
3. 是否空泛、复读共识、回避矛盾、只做修辞
4. 是否与其他人的观点实质重复、没有增量

【规则】
- 只能从这些存活者里选一位：{", ".join(others) or "（无）"}
- 必须恰好投一位，不允许弃权
- 只输出一行 JSON，前后不要任何文字、不要代码块标记：
{{"vote": "<被投的人名字>", "reason": "{reason_hint}"}}"""


def build_final_prompt(
    *,
    winner: str,
    proposition: str,
    transcript_digest: str,
    eliminated: Sequence[tuple[str, str]],
) -> str:
    elim_block = (
        "\n".join(f"- {name}：{why}" for name, why in eliminated) if eliminated else "无"
    )
    return f"""你是这场多智能体辩论的最终胜者 {winner}。

【命题】
{proposition}

【被淘汰者的主要问题】
{elim_block}

【辩论过程要点】
{transcript_digest}

【任务】
综合整场辩论（包括被淘汰者的有效论点），给出对命题的最终结论。

【输出格式】
【结论】明确表态，一句话说清立场。
【论据】3 条以内，每条一行，要有具体内容而非口号。
【行动】给出 1-3 条可立即执行的建议。

总计不超过 400 字。"""
