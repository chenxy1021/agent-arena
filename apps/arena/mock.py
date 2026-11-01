"""Mock agent：不调外部 CLI，用本地假数据跑通整场赛制。

用途：离线验证流程（--mock）、演示、以及在没有额度时做回归测试。
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from typing import Sequence

from .adapters import CallResult

_ANGLE = [
    "从成本结构看，真正的瓶颈不在技术而在单位经济模型",
    "从使用者视角看，这类方案的门槛在于学习成本而非功能缺失",
    "从历史经验看，同类尝试失败多因组织协同而非工具能力",
    "从风险角度看，最大的不确定性是监管口径而非市场竞争",
    "从规模效应看，前期投入换来的边际成本下降需要订单量支撑",
    "从替代成本看，现有工作流的惯性被严重低估",
]
_EVIDENCE = [
    "过去三年的公开案例里，能跑通的方案都先把单点做透再扩展",
    "把范围收敛到一类用户后，转化率通常能提升一个量级",
    "先做最小闭环验证，比一次性铺开节省 60% 以上的试错成本",
    "关键指标应该落在留存而非拉新上，否则规模越大亏得越快",
]
_ACTION = [
    "建议先用两周做一个可关闭的最小验证，用真实数据决定是否加注",
    "建议把目标拆成可度量的三个阶段，每个阶段设明确的止损线",
    "建议先找 5 个真实用户做深度访谈，再决定产品形态",
    "建议把预算的 70% 投在验证上，30% 留给规模化",
]
_CRITIQUE_GOOD = [
    "对成本的量化是对的，这是多数讨论里最容易含糊的部分",
    "把问题从技术拉回商业本质，这个视角有价值",
    "提到的止损线设置很务实，能直接落地",
]
_CRITIQUE_BAD = [
    "但没有给出任何可验证的数据来源，结论悬空",
    "结论过于依赖宏观判断，缺少可执行的第一歩",
    "忽略了执行成本，方案在真实场景里很难推下去",
]
_SUGGEST = [
    "建议补一组可对比的历史数据来支撑",
    "建议把结论收窄到一个具体场景再论证",
    "建议给出反例分析，说明什么情况下你的判断会失效",
]


_JUDGEMENT = [
    "这件事的成败取决于能否在小范围内闭环验证，而不是方案本身的完整性",
    "真正的变量是组织愿不愿意承担短期效率损失换取长期结构改善",
    "关键不在工具能力，而在输入输出能否被稳定度量",
    "要区分短期效率提升和长期能力沉淀，这两件事经常被混为一谈",
]


@dataclass
class MockAgent:
    """与 CliAgent 同构的假 agent。"""

    name: str
    seed: int = 0
    fail_rate: float = 0.0

    def __post_init__(self) -> None:
        self.rng = random.Random(f"{self.seed}-{self.name}")
        self.spec = type("Spec", (), {"key": "mock", "label": "Mock", "note": ""})()
        self.version = "mock"
        self.path = "builtin://mock"
        self.calls = 0

    @property
    def label(self) -> str:
        return f"Mock Agent {self.name}"

    def __repr__(self) -> str:
        return f"<MockAgent {self.name}>"

    def ask(self, prompt: str, workdir=None, timeout: float = 0, retries: int = 0) -> CallResult:
        started = time.monotonic()
        time.sleep(self.rng.uniform(0.05, 0.35))
        self.calls += 1
        if self.rng.random() < self.fail_rate:
            return CallResult(elapsed=time.monotonic() - started, error="mock 注入的调用失败")

        if "投票环节" in prompt:
            text = self._vote(prompt)
        elif "最终胜者" in prompt:
            text = self._final(prompt)
        else:
            text = self._speech(prompt)
        return CallResult(text=text, elapsed=time.monotonic() - started)

    # -- 内部 ----------------------------------------------------------
    def _speech(self, prompt: str) -> str:
        has_prior = "没有前序发言" not in prompt
        prev = ""
        if has_prior:
            m = re.search(r"【本轮已有发言】\n\n【([^】]+)】", prompt)
            prev = m.group(1) if m else "对方"

        body = (
            f"{self.rng.choice(_ANGLE)}。" if not has_prior
            else f"{self.rng.choice(_ANGLE)}，我认同{prev}的一部分判断，但方向要修正。"
        )
        view = (
            f"{body}具体来说，{self.rng.choice(_EVIDENCE)}。"
            f"我的判断是：{self.rng.choice(_JUDGEMENT)}。"
            f"{self.rng.choice(_ACTION)}"
        )
        if has_prior:
            comment = (
                f"{self.rng.choice(_CRITIQUE_GOOD)}；{self.rng.choice(_CRITIQUE_BAD)}。"
                f"{self.rng.choice(_SUGGEST)}"
            )
        else:
            comment = "（开场）"
        return f"【点评】{comment}\n【观点】{view}"

    def _vote(self, prompt: str) -> str:
        m = re.search(r"【(?:本轮)?存活参赛者】(.*)", prompt)
        names: Sequence[str] = [x.strip() for x in m.group(1).split(",")] if m else []
        candidates = [n for n in names if n != self.name]
        target = self.rng.choice(candidates) if candidates else (names[0] if names else "unknown")
        return json.dumps(
            {"vote": target, "reason": self.rng.choice(["论证空泛", "与共识重复", "缺少可执行方案", "回避了核心矛盾"])},
            ensure_ascii=False,
        )

    def _final(self, prompt: str) -> str:
        return (
            "【结论】值得做，但必须先压小范围验证，再谈规模。\n"
            "【论据】1. 现有案例证明单点闭环是可行的最低成本路径。\n"
            "2. 成本结构的改善依赖订单密度，而非技术升级。\n"
            "3. 主要风险在执行节奏，而非方向本身。\n"
            "【行动】先用两周做可关闭的最小验证；设定明确止损线；拿到真实数据后再决定加注。"
        )
