import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.arena.adapters import CallResult
from apps.arena.mock import MockAgent
from apps.arena.events import RecordingSink
from apps.arena.moderator import Arena, ArenaConfig, RoundRecord, Speech, Vote
from apps.arena import prompts


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
    def test_tiebreak_revotes_then_reduces_voters_until_unique(self) -> None:
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
                patch("apps.arena.moderator.random.choice", return_value=a),
            ):
                out, _, tiebreak = arena._resolve_vote(
                    [a, b], [a, b], record, [], 2
                )

        self.assertIs(out, a)
        self.assertIn("随机移出投票人", tiebreak)
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

    def test_later_round_summarizes_prior_rounds_and_focuses_on_new_view(self) -> None:
        prompt = self.build(2, [("模型A", "上一轮观点"), ("模型B", "另一个上一轮观点")])

        self.assertIn("【前几轮完整发言】", prompt)
        self.assertIn("上一轮观点", prompt)
        self.assertIn("另一个上一轮观点", prompt)
        self.assertIn("整体优点和不足", prompt)
        self.assertIn("不要逐个模型点评", prompt)
        self.assertIn("主要篇幅放在你自己的新观点", prompt)
        self.assertNotIn("本轮已有发言", prompt)


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
            event["round_no"] for event in sink.events if event["kind"] == "voting_start"
        ]
        self.assertEqual(voting_rounds, [2, 3])


if __name__ == "__main__":
    unittest.main()
