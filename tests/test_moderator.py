import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from apps.arena.agent import CallResult
from apps.arena.mock import MockAgent
from apps.arena.events import RecordingSink
from apps.arena.moderator import (
    Arena,
    ArenaConfig,
    RoundRecord,
    Speech,
    Vote,
    assign_names,
    _prior_speeches_for,
    extract_critiques_for,
    extract_stance,
    extract_view,
    parse_ballot,
    parse_claims,
)
from apps.arena import prompts


class StanceTest(unittest.TestCase):
    def test_parses_signed_stance_marker(self) -> None:
        self.assertEqual(extract_stance("【立场】+37\n【观点】支持"), 37)
        self.assertEqual(extract_stance("【立场】-82\n【观点】反对"), -82)

    def test_missing_or_malformed_stance_is_none(self) -> None:
        self.assertIsNone(extract_stance("【观点】没有立场标记"))
        self.assertIsNone(extract_stance("【立场】abc"))

    def test_stance_is_clamped_to_range(self) -> None:
        self.assertEqual(extract_stance("【立场】999"), 100)
        self.assertEqual(extract_stance("【立场】-999"), -100)

    def test_stance_marker_is_stripped_from_view_text(self) -> None:
        view = extract_view("【立场】+40\n【观点】增长可以复制")
        self.assertEqual(view, "增长可以复制")


class AgentNamingTest(unittest.TestCase):
    def test_api_model_names_are_preserved(self) -> None:
        agents = [
            SimpleNamespace(name="GPT-5", label="gpt-5"),
            SimpleNamespace(name="Claude", label="claude-opus-4"),
        ]

        assign_names(agents)

        self.assertEqual([agent.name for agent in agents], ["GPT-5", "Claude"])

    def test_duplicate_names_are_numbered(self) -> None:
        agents = [
            SimpleNamespace(name="GPT-5", label="gpt-5"),
            SimpleNamespace(name="GPT-5", label="gpt-5-mini"),
        ]

        assign_names(agents)

        self.assertEqual([agent.name for agent in agents], ["GPT-5#1", "GPT-5#2"])


class DecideVoteTest(unittest.TestCase):
    def make_arena(self, mode: str) -> Arena:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Arena(
            [MockAgent("a"), MockAgent("b")],
            ArenaConfig(proposition="test", out_dir=Path(tmp.name), vote_mode=mode),
        )

    def test_unique_vote_selects_target(self) -> None:
        arena = self.make_arena("eliminate")
        a, b = arena.agents
        speeches = [
            Speech(1, a.name, "开场发言", "x" * 10, 0),
            Speech(1, b.name, "回应发言", "y" * 10, 0),
        ]

        out, votes, _ = arena._decide({a.name: 2, b.name: 1}, arena.agents, speeches)

        self.assertIs(out, a)
        self.assertEqual(votes, 2)

    def test_tied_vote_enters_tiebreak(self) -> None:
        arena = self.make_arena("eliminate")
        a, b = arena.agents
        speeches = [
            Speech(1, a.name, "开场发言", "x" * 10, 0),
            Speech(1, b.name, "回应发言", "y" * 10, 0),
        ]

        out, _, tiebreak = arena._decide({a.name: 1, b.name: 1}, arena.agents, speeches)

        self.assertIsNone(out)
        self.assertIn("进入加赛", tiebreak)


class TiebreakVoteTest(unittest.TestCase):
    def test_stop_interrupts_waiting_model_call(self) -> None:
        class SlowAgent:
            name = "slow"
            label = "slow"

            def ask(self, prompt, timeout=0, retries=0, on_output=None, **_kwargs):
                time.sleep(0.8)
                return CallResult(text="late")

        with tempfile.TemporaryDirectory() as tmp:
            arena = Arena(
                [SlowAgent(), MockAgent("b")],
                ArenaConfig(proposition="test", out_dir=Path(tmp)),
            )
            cancel = threading.Event()
            cancel.set()
            arena.cancel_hook = cancel

            started = time.monotonic()
            result = arena._ask_with_progress(arena.agents[0], "prompt", "发言")
            elapsed = time.monotonic() - started

        self.assertTrue(result.cancelled)
        self.assertLess(elapsed, 0.6)

    def test_failed_judge_ballot_is_retried_before_tiebreak(self) -> None:
        class BallotAgent:
            def __init__(self, name: str, ballots: list[str]):
                self.name = name
                self.label = name
                self.ballots = ballots
                self.calls = 0

            def ask(self, prompt, timeout=0, retries=0, on_output=None, **_kwargs):
                self.calls += 1
                text = self.ballots[min(self.calls - 1, len(self.ballots) - 1)]
                return CallResult(text=text)

        with tempfile.TemporaryDirectory() as tmp:
            a = BallotAgent("a", ['{"vote":"b","reason":"a"}'])
            b = BallotAgent("b", ['{"vote":"a","reason":"b"}'])
            judge = BallotAgent("j", ["无法解析", '{"vote":"a","reason":"j"}'])
            arena = Arena(
                [a, b, judge],
                ArenaConfig(proposition="test", out_dir=Path(tmp)),
            )
            arena._judges = [judge]
            record = RoundRecord(no=3, order=["a", "b"])

            out, _, tiebreak = arena._resolve_vote([judge, a, b], [a, b], record, [], 3)

        self.assertEqual(out.name, "a")
        self.assertEqual(judge.calls, 2)
        self.assertIsNone(tiebreak)

    def test_exhausted_tiebreak_is_marked_undecided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = RecordingSink()
            arena = Arena(
                [MockAgent("a"), MockAgent("b")],
                ArenaConfig(proposition="test", out_dir=Path(tmp)),
                sink=sink,
            )
            a, b = arena.agents
            record = RoundRecord(
                no=2,
                order=[a.name, b.name],
                speeches=[
                    Speech(2, a.name, "跨轮点评", "a speech", 0),
                    Speech(2, b.name, "跨轮点评", "b speech", 0),
                ],
            )
            ballots = [
                [Vote(2, a.name, b.name), Vote(2, b.name, a.name)],
                [Vote(2, a.name, b.name, stage="tiebreak-1"),
                 Vote(2, b.name, a.name, stage="tiebreak-1")],
                [Vote(2, b.name, a.name, stage="tiebreak-2")],
            ]
            with (
                patch.object(arena, "_collect_votes", side_effect=ballots),
                patch.object(
                    arena,
                    "_ask_with_progress",
                    return_value=CallResult(text="【观点】加赛补充论证", elapsed=0),
                ),
            ):
                out, _, tiebreak = arena._resolve_vote(
                    [a, b], [a, b], record, [], 2
                )

        # 加赛仍然平票 → 走三级裁决；完全相同时明确未决，不按姓名兜底。
        self.assertIsNone(out)
        self.assertIn("未决", tiebreak or "")
        self.assertNotIn("随机移出投票人", tiebreak or "")
        self.assertEqual(len([s for s in record.speeches if s.role == "平票加赛"]), 2)
        self.assertTrue(any(v.stage.startswith("tiebreak") for v in record.votes))
        self.assertTrue(any(event["kind"] == "tiebreak" for event in sink.events))


class ProgressEventTest(unittest.TestCase):
    def test_long_call_emits_waiting_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = RecordingSink()
            arena = Arena(
                [MockAgent("a"), MockAgent("b")],
                ArenaConfig(
                    proposition="test",
                    out_dir=Path(tmp),
                    waiting_interval=0.01,
                ),
                sink=sink,
            )

            result = arena._ask_with_progress(arena.agents[0], "测试", "测试发言")

        self.assertFalse(result.error)
        self.assertTrue(any(event["kind"] == "waiting" for event in sink.events))
        self.assertTrue(any(event["kind"] == "model_output" for event in sink.events))


class SpeechPromptVisibilityTest(unittest.TestCase):
    def build(self, round_no: int, prior):
        return prompts.build_speech_prompt(
            speaker="模型A",
            proposition="测试命题",
            active=["模型A", "模型B"],
            eliminated=[],
            round_no=round_no,
            prior_speeches=prior,
            my_last_stance=None,
        )

    def test_round_one_is_independent_and_has_no_critique(self) -> None:
        prompt = self.build(1, [])

        self.assertIn("这是第一轮", prompt)
        self.assertNotIn("【点评】", prompt)
        self.assertIn("看不到其他模型本轮的发言", prompt)

    def test_later_round_only_sees_last_round_and_asks_for_a_response(self) -> None:
        prompt = self.build(2, [("模型A", "上一轮观点"), ("模型B", "另一个上一轮观点")])

        self.assertIn("【上一轮发言】", prompt)
        self.assertNotIn("【前几轮完整发言】", prompt)
        self.assertIn("上一轮观点", prompt)
        self.assertIn("另一个上一轮观点", prompt)
        self.assertIn("点名回应其中一条", prompt)
        self.assertIn("接受还是反驳", prompt)
        self.assertIn("【主张】", prompt)
        self.assertNotIn("本轮已有发言", prompt)

    def test_prior_speeches_exclude_eliminated_models(self) -> None:
        rounds = [
            RoundRecord(
                no=1,
                order=["模型A", "模型B", "模型C"],
                speeches=[
                    Speech(1, "模型A", "独立发言", "A 的论点", 0),
                    Speech(1, "模型B", "独立发言", "B 的论点", 0),
                    Speech(1, "模型C", "独立发言", "C 的论点", 0),
                ],
            )
        ]
        current = [MockAgent("模型A"), MockAgent("模型C")]

        prior = _prior_speeches_for(current, rounds)

        self.assertEqual(prior, [("模型A", "A 的论点"), ("模型C", "C 的论点")])

    def test_custom_win_condition_is_included_in_speech_prompt(self) -> None:
        prompt = prompts.build_speech_prompt(
            speaker="模型A",
            proposition="测试命题",
            active=["模型A", "模型B"],
            eliminated=[],
            round_no=1,
            prior_speeches=[],
            my_last_stance=None,
            win_condition="甲、乙同阵营，淘汰丙即该阵营获胜",
        )

        self.assertIn("【胜出标准】", prompt)
        self.assertIn("甲、乙同阵营，淘汰丙即该阵营获胜", prompt)


class VoteProgressEventTest(unittest.TestCase):
    def test_each_voter_emits_thinking_and_done_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = RecordingSink()
            arena = Arena(
                [MockAgent("a"), MockAgent("b")],
                ArenaConfig(proposition="test", out_dir=Path(tmp)),
                sink=sink,
            )
            a, b = arena.agents

            votes = arena._collect_votes([a, b], [a, b], [], [], 2)

        self.assertEqual(len(votes), 2)
        progress = [event for event in sink.events if event["kind"] == "voting"]
        self.assertEqual(len(progress), 4)
        self.assertEqual({event["status"] for event in progress}, {"thinking", "done"})
        self.assertTrue(all(event["stage"] == "main" for event in progress))


class TournamentScheduleTest(unittest.TestCase):
    def test_first_round_has_no_vote_and_second_round_starts_voting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = RecordingSink()
            result = Arena(
                [MockAgent("a"), MockAgent("b"), MockAgent("c")],
                ArenaConfig(proposition="test", out_dir=Path(tmp)),
                sink=sink,
            ).run()

        self.assertEqual(result.rounds[0].votes, [])
        self.assertIsNone(result.rounds[0].eliminated)
        self.assertTrue(result.rounds[1].votes)
        self.assertIsNotNone(result.rounds[1].eliminated)
        voting_rounds = [
            event["round_no"]
            for event in sink.events
            if event["kind"] == "voting_start" and event.get("stage") == "main"
        ]
        self.assertEqual(voting_rounds, [2, 3])

    def test_judge_win_condition_can_end_match_early(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = RecordingSink()
            judge = MockAgent("judge", win_condition_met=True)
            result = Arena(
                [MockAgent("a"), MockAgent("b"), MockAgent("c")],
                ArenaConfig(
                    proposition="test",
                    out_dir=Path(tmp),
                    win_condition="甲、乙同阵营，淘汰丙即获胜",
                ),
                sink=sink,
                judge=judge,
            ).run()

        self.assertEqual(result.winner_agents, ["a", "b"])
        self.assertTrue(result.judge)
        self.assertTrue(result.win_checks)
        self.assertTrue(result.win_checks[-1]["met"])
        self.assertIn("裁判认定胜出标准已满足", result.stop_reason)
        self.assertTrue(any(event["kind"] == "win_check" for event in sink.events))


class ClaimParsingTest(unittest.TestCase):
    def test_parses_claim_tag(self) -> None:
        text = "【观点】一些观点\n【主张】先收定金再交付，不要免费定制"
        self.assertEqual(parse_claims(text), ["先收定金再交付，不要免费定制"])

    def test_falls_back_to_first_sentence_of_view(self) -> None:
        text = "【观点】先收定金再交付。其他内容。"
        self.assertEqual(parse_claims(text), ["先收定金再交付"])

    def test_ledger_records_author_and_round(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            arena = Arena(
                [MockAgent("a"), MockAgent("b")],
                ArenaConfig(proposition="test", out_dir=Path(tmp)),
            )
            entries = arena._add_claims("a", "【主张】先做最小闭环", 2, 30)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["author"], "a")
        self.assertEqual(entries[0]["round"], 2)
        self.assertEqual(entries[0]["final_status"], "dormant")


class BallotParsingTest(unittest.TestCase):
    def test_parses_multidimensional_scores(self) -> None:
        text = (
            '{"scores": {"模型B": {"论证": 8, "证据": 5, "可执行": 7, "增量": 9}}, '
            '"vote": "模型B", "reason": "证据链更完整"}'
        )
        target, reason, scores = parse_ballot(text, ["模型A", "模型B"], "模型A")

        self.assertEqual(target, "模型B")
        self.assertEqual(reason, "证据链更完整")
        self.assertEqual(scores["模型B"]["论证"], 8)

    def test_accepts_ballot_without_scores(self) -> None:
        target, reason, scores = parse_ballot(
            '{"vote": "模型B", "reason": "缺少证据"}', ["模型A", "模型B"], "模型A"
        )

        self.assertEqual(target, "模型B")
        self.assertEqual(reason, "缺少证据")
        self.assertEqual(scores, {})

    def test_rejects_legacy_plain_text_vote(self) -> None:
        target, reason, scores = parse_ballot(
            'vote: "模型B"', ["模型A", "模型B"], "模型A"
        )

        self.assertIsNone(target)
        self.assertEqual(reason, "")
        self.assertEqual(scores, {})

    def test_reason_is_kept_up_to_200_chars(self) -> None:
        long_reason = "理" * 300
        _, reason, _ = parse_ballot(
            '{"vote": "模型B", "reason": "' + long_reason + '"}',
            ["模型A", "模型B"],
            "模型A",
        )

        self.assertEqual(len(reason), 200)


class WeightedVoteTest(unittest.TestCase):
    def make_arena(self) -> Arena:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Arena(
            [MockAgent("a"), MockAgent("b"), MockAgent("c")],
            ArenaConfig(proposition="test", out_dir=Path(tmp.name)),
        )

    def test_judge_votes_count_half(self) -> None:
        arena = self.make_arena()
        votes = [
            Vote(2, "a", "b", weight=1.0),
            Vote(2, "judge", "b", weight=0.5, is_judge=True),
        ]

        counts = arena._weighted_counts(votes)

        self.assertEqual(counts["b"], 1.5)

    def test_judge_keeps_half_weight_with_two_alive(self) -> None:
        arena = self.make_arena()

        self.assertEqual(arena._judge_weight_for(3), 0.5)
        self.assertEqual(arena._judge_weight_for(2), 0.5)

    def test_zero_weight_voter_is_not_called_or_listed(self) -> None:
        arena = self.make_arena()
        arena.cfg.judge_weight = 0
        judge = MockAgent("judge")
        judge.calls = 0
        arena._judges = [judge]

        votes = arena._collect_votes(
            [judge, arena.agents[0], arena.agents[1]],
            [arena.agents[0], arena.agents[1]],
            [],
            [],
            2,
        )

        self.assertEqual(judge.calls, 0)
        self.assertNotIn(judge.name, [vote.voter for vote in votes])


class ConvergenceTest(unittest.TestCase):
    def test_converged_stances_stop_the_match_early(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = RecordingSink()
            arena = Arena(
                [MockAgent("a"), MockAgent("b"), MockAgent("c")],
                ArenaConfig(proposition="test", out_dir=Path(tmp)),
                sink=sink,
            )
            a, b, c = arena.agents
            record = RoundRecord(no=1, order=[a.name, b.name, c.name])
            record.speeches = [
                Speech(1, a.name, "独立发言", "", 0, None, 10),
                Speech(1, b.name, "独立发言", "", 0, None, 12),
                Speech(1, c.name, "独立发言", "", 0, None, 8),
            ]
            spread = arena._stance_spread(arena.agents, record)

        self.assertEqual(spread, 4)
        self.assertLessEqual(spread, 25)

    def test_first_round_cannot_end_the_match_as_converged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(Arena, "_stance_spread", return_value=0):
                result = Arena(
                    [MockAgent("a"), MockAgent("b"), MockAgent("c")],
                    ArenaConfig(proposition="test", out_dir=Path(tmp)),
                ).run()

        self.assertGreaterEqual(len(result.rounds), 2)
        self.assertIsNotNone(result.winner)

    def test_convergence_round_still_names_a_winner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(Arena, "_stance_spread", return_value=0):
                result = Arena(
                    [MockAgent("a"), MockAgent("b"), MockAgent("c")],
                    ArenaConfig(proposition="test", out_dir=Path(tmp)),
                ).run()

        self.assertTrue(result.converged)
        self.assertIn("收敛", result.stop_reason)
        self.assertIsNotNone(result.winner)
        self.assertEqual(len(result.rounds), 3)


class StanceSpreadTest(unittest.TestCase):
    def test_spread_is_max_minus_min(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            arena = Arena(
                [MockAgent("a"), MockAgent("b")],
                ArenaConfig(proposition="test", out_dir=Path(tmp)),
            )
            a, b = arena.agents
            record = RoundRecord(no=1, order=[a.name, b.name])
            record.speeches = [
                Speech(1, a.name, "独立发言", "", 0, None, 40),
                Speech(1, b.name, "独立发言", "", 0, None, -10),
            ]

            spread = arena._stance_spread(arena.agents, record)

        self.assertEqual(spread, 50)


class CritiqueExtractionTest(unittest.TestCase):
    def test_picks_up_comments_naming_the_model(self) -> None:
        speeches = [
            Speech(1, "模型A", "独立发言", "【点评】模型B 的证据链有缺口", 0),
            Speech(1, "模型B", "独立发言", "【点评】模型A 的结论过于笼统", 0),
        ]
        votes = [Vote(1, "模型C", "模型B", reason="模型B 的方案不可验收")]

        critiques = extract_critiques_for("模型B", speeches, votes)

        self.assertEqual(len(critiques), 2)
        self.assertTrue(any("模型A" in c for c in critiques))
        self.assertTrue(any("模型C" in c for c in critiques))


class ParallelSpeechTest(unittest.TestCase):
    def test_parallel_mode_emits_parallel_events_and_keeps_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = RecordingSink()
            result = Arena(
                [MockAgent("a"), MockAgent("b")],
                ArenaConfig(
                    proposition="test",
                    out_dir=Path(tmp),
                    speech_mode="parallel_buffered",
                ),
                sink=sink,
            ).run()

        kinds = [event["kind"] for event in sink.events]
        self.assertIn("parallel_start", kinds)
        self.assertIn("parallel_done", kinds)
        self.assertIn("parallel_replay", kinds)
        progress = [event for event in sink.events if event["kind"] == "parallel_progress"]
        self.assertTrue(progress)
        self.assertTrue(all(event.get("text") for event in progress))
        self.assertEqual([s.agent for s in result.rounds[0].speeches], result.rounds[0].order)

    def test_transcript_has_claims_and_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = Arena(
                [MockAgent("a"), MockAgent("b")],
                ArenaConfig(proposition="test", out_dir=Path(tmp)),
            ).run()

        data = result.to_dict()
        self.assertEqual(data["schema_version"], 3)
        self.assertTrue(data["claims"])
        self.assertIn("calls", data["budget"])
        self.assertEqual(data["setup"]["vote_mode"], "eliminate")
        self.assertEqual(data["setup"]["speech_mode"], "parallel_buffered")
        self.assertEqual(len(data["setup"]["model_ids"]), 2)
        self.assertIn("weight_breakdown", data["rounds"][1])


if __name__ == "__main__":
    unittest.main()


class JudgeFinalSummaryTest(unittest.TestCase):
    def test_final_prompt_asks_judge_to_summarize(self) -> None:
        prompt = prompts.build_final_prompt(
            winners=["甲"],
            judge="裁判",
            proposition="命题",
            transcript_digest="要点",
            eliminated=[("乙", "淘汰")],
            win_condition="只剩最后一人",
        )
        self.assertIn("你是自定义淘汰赛的独立裁判 裁判", prompt)
        self.assertIn("最终胜者是：甲", prompt)
        self.assertIn("你代表裁判做整场总结", prompt)
