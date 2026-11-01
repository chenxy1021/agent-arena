import tempfile
import unittest
from pathlib import Path

from apps.arena.mock import MockAgent
from apps.arena.events import RecordingSink
from apps.arena.moderator import Arena, ArenaConfig, Speech


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


if __name__ == "__main__":
    unittest.main()
