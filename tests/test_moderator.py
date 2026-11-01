import tempfile
import unittest
from pathlib import Path

from apps.arena.mock import MockAgent
from apps.arena.events import RecordingSink
from apps.arena.moderator import Arena, ArenaConfig, Speech
from apps.arena import prompts


class DecideTiebreakTest(unittest.TestCase):
    def make_arena(self, mode: str) -> Arena:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Arena(
            [MockAgent("a"), MockAgent("b")],
            ArenaConfig(proposition="test", out_dir=Path(tmp.name), vote_mode=mode),
        )

    def test_eliminate_uses_more_cumulative_votes(self) -> None:
        arena = self.make_arena("eliminate")
        a, b = arena.agents
        arena._cum_danger[a.name] = 5
        arena._cum_danger[b.name] = 1
        speeches = [
            Speech(1, a.name, "开场发言", "x" * 10, 0),
            Speech(1, b.name, "回应发言", "y" * 10, 0),
        ]

        out, _, _ = arena._decide({a.name: 1, b.name: 1}, arena.agents, speeches)

        self.assertIs(out, a)

    def test_support_uses_fewer_cumulative_support_votes(self) -> None:
        arena = self.make_arena("support")
        a, b = arena.agents
        arena._cum_danger[a.name] = -5
        arena._cum_danger[b.name] = -1
        speeches = [
            Speech(1, a.name, "开场发言", "x" * 10, 0),
            Speech(1, b.name, "回应发言", "y" * 10, 0),
        ]

        out, _, _ = arena._decide({a.name: 1, b.name: 1}, arena.agents, speeches)

        self.assertIs(out, b)


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
    def build(self, round_no: int, previous):
        return prompts.build_speech_prompt(
            speaker="模型A",
            proposition="测试命题",
            active=["模型A", "模型B"],
            eliminated=[],
            round_no=round_no,
            previous_round_speeches=previous,
            my_last_stance=None,
        )

    def test_round_one_is_independent_and_has_no_critique(self) -> None:
        prompt = self.build(1, [])

        self.assertIn("这是第一轮", prompt)
        self.assertNotIn("【点评】", prompt)
        self.assertIn("看不到其他模型本轮的发言", prompt)

    def test_later_round_sees_only_previous_round(self) -> None:
        prompt = self.build(2, [("模型A", "上一轮观点"), ("模型B", "另一个上一轮观点")])

        self.assertIn("【上一轮完整发言】", prompt)
        self.assertIn("上一轮观点", prompt)
        self.assertIn("另一个上一轮观点", prompt)
        self.assertIn("点评上一轮所有模型", prompt)
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
