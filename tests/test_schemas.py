import unittest

from apps.arena.schemas import StartRun


class StartRunSchemaTest(unittest.TestCase):
    def test_unknown_fields_are_ignored(self) -> None:
        payload = StartRun.model_validate({
            "proposition": "test",
            "model_ids": [1, 2],
            "max_calls": 10,
            "max_wall_clock": 60,
        })

        self.assertFalse(hasattr(payload, "max_calls"))
        self.assertFalse(hasattr(payload, "max_wall_clock"))


if __name__ == "__main__":
    unittest.main()
