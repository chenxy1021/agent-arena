import json
import tempfile
import unittest
from pathlib import Path

from apps.arena.agent import CallResult
from apps.arena.events import RecordingSink
from apps.arena.review import ReviewArena, ReviewConfig, parse_judgement, parse_plan


class ReviewAgent:
    def __init__(self, name: str, plan_name: str, score: float):
        self.name = name
        self.label = f"model-{name}"
        self.model = self.label
        self.config_id = 0
        self.path = "builtin://review"
        self.plan_name = plan_name
        self.score = score
        self.prompts = []
        self.calls = 0
        self.break_json = False

    def ask(self, prompt, timeout=0, retries=0, on_output=None, **_kwargs):
        self.calls += 1
        self.prompts.append(prompt)
        if self.plan_name == "FAIL":
            raise RuntimeError("接口连接失败")
        if "匿名方案" in prompt:
            labels = [
                part.split("】", 1)[0].removeprefix("【")
                for part in prompt.split("【匿名方案】", 1)[1].split("【")[1:]
            ][:2]
            labels = [label for label in labels if label.startswith("方案")]
            scores = {
                label: {
                    "可行性": self.score if label == "方案1" else 7,
                    "正确性": self.score if label == "方案1" else 7,
                    "完备性": self.score if label == "方案1" else 7,
                    "差异度": self.score if label == "方案1" else 7,
                }
                for label in labels
            }
            text = (
                "不是 JSON"
                if self.break_json
                else json.dumps(
                    {
                        "scores": scores,
                        "ranking": labels,
                        "recommended": labels[0],
                        "reasons": {labels[0]: "方案步骤完整，差异明确，可以进入小范围验证。"},
                        "risks": {labels[0]: "风险在于首轮验证样本不足，需要设置止损线。"},
                        "rejections": {labels[1]: "方案缺少可验证的止损条件，执行成本也没有上限。"},
                    },
                    ensure_ascii=False,
                )
            )
            return CallResult(text=text, elapsed=0)
        if "整合建议" in prompt:
            return CallResult(
                text=(
                    "【推荐结论】推荐方案1，先做最小闭环。\n"
                    "【关键理由】步骤清晰。\n"
                    "【必须吸收】无跨方案补充\n"
                    "【整合方案】两周验证。\n"
                    "【前提与失效条件】样本不足时失效。"
                ),
                elapsed=0,
            )
        text = (
            f"【方案名】{self.plan_name}\n"
            "【核心主张】先做小范围验证。\n"
            "【做法步骤】访谈；原型；灰度。\n"
            "【代价】两周人力。\n"
            "【风险】样本偏差。\n"
            "【与主流做法的差异】先验证后扩张。"
        )
        if on_output:
            on_output(text)
        return CallResult(text=text, elapsed=0)


class ReviewArenaTest(unittest.TestCase):
    def test_review_is_anonymous_and_uses_n_plus_two_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agents = [ReviewAgent("甲", "精益验证", 9), ReviewAgent("乙", "全面铺开", 6)]
            judge = ReviewAgent("裁判", "裁判", 8)
            judge.config_id = 99
            judge.score = 8
            sink = RecordingSink()
            result = ReviewArena(
                agents,
                judge,
                ReviewConfig(
                    proposition="是否应该先做小范围验证",
                    out_dir=Path(tmp),
                    run_id="fixed-seed",
                ),
                sink=sink,
            ).run()

            judge_prompt = next(
                prompt for prompt in judge.prompts if "匿名方案" in prompt
            )

        self.assertEqual(result.budget["calls"], 4)
        self.assertNotIn("甲", judge_prompt)
        self.assertNotIn("乙", judge_prompt)
        self.assertIn("方案1", judge_prompt)
        self.assertEqual(len(result.labels), 2)
        self.assertEqual(result.schema_version, 5)
        self.assertTrue(result.recommended_agent)
        self.assertTrue(result.synthesis_sections["recommendation"])
        self.assertTrue(any(event["kind"] == "review_judge_done" for event in sink.events))

    def test_plan_parser_marks_missing_sections(self) -> None:
        plan, missing = parse_plan("【方案名】A\n【核心主张】B")

        self.assertEqual(plan["name"], "A")
        self.assertIn("风险", missing)

    def test_plan_parser_accepts_markdown_headings(self) -> None:
        plan, missing = parse_plan(
            "## 方案名：灰度试点\n### 核心主张：先小后大\n"
            "**做法步骤**：试点两周\n代价：一周人力\n"
            "风险：样本偏差\n与主流做法的差异：先验证"
        )

        self.assertEqual(plan["name"], "灰度试点")
        self.assertEqual(plan["claim"], "先小后大")
        self.assertEqual(missing, [])

    def test_equal_totals_share_first_place_without_mismatch(self) -> None:
        parsed, anomalies = parse_judgement(
            json.dumps(
                {
                    "scores": {
                        "方案1": {"可行性": 8, "正确性": 8, "完备性": 8, "差异度": 6},
                        "方案2": {"可行性": 8, "正确性": 8, "完备性": 8, "差异度": 6},
                    },
                    "ranking": ["方案1", "方案2"],
                    "recommended": "方案2",
                    "reasons": {"方案2": "同分时更贴近现有资源约束。"},
                    "rejections": {"方案1": "与方案2同分，但没有额外资源优势。"},
                },
                ensure_ascii=False,
            ),
            ["方案1", "方案2"],
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["ranks"], {"方案1": 1, "方案2": 1})
        self.assertEqual(parsed["tie"]["tied_labels"], ["方案1", "方案2"])
        self.assertTrue(parsed["recommend_deviation"]["matched"])
        self.assertNotIn("recommend_mismatch", {item["code"] for item in anomalies})

    def test_difference_dimension_does_not_affect_total(self) -> None:
        parsed, _ = parse_judgement(
            json.dumps(
                {
                    "scores": {
                        "方案1": {"可行性": 7, "正确性": 7, "完备性": 7, "差异度": 10},
                        "方案2": {"可行性": 8, "正确性": 8, "完备性": 8, "差异度": 1},
                    },
                    "ranking": ["方案2", "方案1"],
                    "recommended": "方案2",
                    "reasons": {"方案2": "三维更完整。"},
                    "rejections": {"方案1": "差异度高但不代表更可行。"},
                },
                ensure_ascii=False,
            ),
            ["方案1", "方案2"],
        )

        self.assertEqual(parsed["totals"], {"方案1": 7.0, "方案2": 8.0})
        self.assertEqual(parsed["ranking"], ["方案2", "方案1"])

    def test_judge_failure_degrades_without_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            judge = ReviewAgent("裁判", "裁判", 0)
            judge.break_json = True
            sink = RecordingSink()
            result = ReviewArena(
                [ReviewAgent("甲", "A", 8), ReviewAgent("乙", "B", 6)],
                judge,
                ReviewConfig(proposition="test", out_dir=Path(tmp), run_id="x"),
                sink=sink,
            ).run()

        self.assertEqual(result.stop_reason, "评审未完成")
        self.assertEqual(result.scores, {})
        self.assertEqual(result.ranking, [])
        self.assertTrue(result.anomalies)
        self.assertTrue(any(
            event["kind"] == "saved" for event in sink.events
        ))

    def test_single_valid_answer_blocks_review_with_notice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            judge = ReviewAgent("裁判", "裁判", 0)
            sink = RecordingSink()
            arena = ReviewArena(
                [ReviewAgent("甲", "A", 8), ReviewAgent("乙", "FAIL", 0)],
                judge,
                ReviewConfig(proposition="test", out_dir=Path(tmp), run_id="x"),
                sink=sink,
            )

            with self.assertRaises(ValueError) as ctx:
                arena.run()

        self.assertIn("有效方案不足", str(ctx.exception))
        blocked = next(
            event for event in sink.events if event["kind"] == "review_blocked"
        )
        self.assertEqual(blocked["absent"][0]["agent"], "乙")

    def test_rerun_absent_seat_reuses_other_answers_and_keeps_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agents = [ReviewAgent("甲", "精益验证", 9), ReviewAgent("乙", "FAIL", 7)]
            judge = ReviewAgent("裁判", "裁判", 8)
            judge.config_id = 99
            cfg = ReviewConfig(
                proposition="测试席位重跑",
                out_dir=Path(tmp),
                run_id="retry-seed",
            )
            arena = ReviewArena(agents, judge, cfg)
            with self.assertRaisesRegex(ValueError, "有效方案不足"):
                arena.run()
            transcript = json.loads((arena.run_dir / "transcript.json").read_text())
            first_calls = agents[0].calls

            agents[1].plan_name = "补齐方案"
            retried = ReviewArena(agents, judge, cfg, run_dir=arena.run_dir)
            result = retried.rerun_answer(transcript, "乙")

        self.assertEqual(agents[0].calls, first_calls)
        self.assertEqual(agents[1].calls, 2)
        self.assertEqual(len(result.answers), 2)
        self.assertEqual(next(item for item in result.answers if item["agent"] == "乙")["attempt"], 2)
        self.assertEqual(len(result.attempts), 3)
        self.assertTrue(result.recommended_agent)

    def test_judge_parser_clamps_scores_and_flags_missing_dimensions(self) -> None:
        parsed, anomalies = parse_judgement(
            json.dumps(
                {
                    "scores": {
                        "方案1": {
                            "可行性": 11,
                            "正确性": 8,
                            "完备性": 7,
                        }
                    },
                    "ranking": ["方案1"],
                    "recommended": "方案1",
                    "reasons": {"方案1": "理由"},
                },
                ensure_ascii=False,
            ),
            ["方案1"],
        )

        self.assertEqual(parsed["scores"]["方案1"]["可行性"], 10)
        self.assertNotIn("差异度", parsed["scores"]["方案1"])
        codes = {item["code"] for item in anomalies}
        self.assertIn("clamped_dimension", codes)
        self.assertIn("missing_dimension", codes)

    def test_judge_parser_marks_recommendation_mismatch(self) -> None:
        parsed, anomalies = parse_judgement(
            json.dumps(
                {
                    "scores": {
                        "方案1": {
                            "可行性": 9, "正确性": 9, "完备性": 9, "差异度": 9,
                        },
                        "方案2": {
                            "可行性": 8, "正确性": 8, "完备性": 8, "差异度": 8,
                        },
                    },
                    "ranking": ["方案1", "方案2"],
                    "recommended": "方案2",
                    "reasons": {"方案2": "方案2 更贴近约束。"},
                    "rejections": {"方案1": "方案1 的执行细节和止损条件仍不够完整。"},
                },
                ensure_ascii=False,
            ),
            ["方案1", "方案2"],
        )

        self.assertEqual(parsed["recommended"], "方案2")
        self.assertIn("recommend_mismatch", {item["code"] for item in anomalies})


if __name__ == "__main__":
    unittest.main()
