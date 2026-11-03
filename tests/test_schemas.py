import unittest

from apps.arena.schemas import StartRun


class StartRunSchemaTest(unittest.TestCase):
    def test_unknown_fields_are_ignored(self) -> None:
        payload = StartRun.model_validate({
            "proposition": "test",
            "win_condition": "投票至最后一人",
            "model_ids": [1, 2],
            "max_calls": 10,
            "max_wall_clock": 60,
        })

        self.assertFalse(hasattr(payload, "max_calls"))
        self.assertFalse(hasattr(payload, "max_wall_clock"))

    def test_win_condition_is_required_and_not_blank(self) -> None:
        with self.assertRaises(ValueError):
            StartRun.model_validate({
                "proposition": "test",
                "win_condition": "   ",
                "model_ids": [1, 2],
            })


if __name__ == "__main__":
    unittest.main()
