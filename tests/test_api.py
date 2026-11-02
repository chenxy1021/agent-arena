import unittest

from apps.arena.api import build_run_preset


class RunPresetTest(unittest.TestCase):
    def test_setup_snapshot_reuses_config_ids_and_context(self) -> None:
        transcript = {
            "proposition": "test",
            "vote_mode": "support",
            "setup": {
                "model_ids": [2, 3],
                "vote_mode": "support",
                "speech_mode": "sequential_live",
                "timeout": 90,
                "background": "context",
                "constraints": ["constraint"],
                "criteria": ["criterion"],
            },
            "participants": [
                {"name": "已改名", "model": "old-model", "config_id": 2},
                {"name": "B", "model": "model-b", "config_id": 3},
            ],
        }
        configs = [
            {"id": 2, "name": "A", "model": "new-model"},
            {"id": 3, "name": "B", "model": "model-b"},
        ]

        preset = build_run_preset(transcript, configs)

        self.assertTrue(preset["resolved"])
        self.assertEqual(preset["model_ids"], [2, 3])
        self.assertEqual(preset["speech_mode"], "sequential_live")
        self.assertEqual(preset["background"], "context")
        self.assertEqual(preset["constraints"], ["constraint"])
        self.assertEqual(preset["criteria"], ["criterion"])

    def test_legacy_transcript_without_setup_is_not_reusable(self) -> None:
        transcript = {
            "proposition": "old",
            "vote_mode": "eliminate",
            "participants": [
                {"name": "A", "label": "model-a"},
                {"name": "B", "label": "model-b"},
            ],
        }
        configs = [
            {"id": 7, "name": "A", "model": "model-a"},
            {"id": 8, "name": "B", "model": "model-b"},
        ]

        preset = build_run_preset(transcript, configs)

        self.assertFalse(preset["reusable"])
        self.assertFalse(preset["resolved"])
        self.assertEqual(preset["model_ids"], [])
        self.assertTrue(preset["warnings"])

    def test_missing_model_blocks_a_silent_rerun(self) -> None:
        transcript = {
            "proposition": "old",
            "setup": {"model_ids": [7, 9]},
            "participants": [
                {"name": "A", "model": "model-a", "config_id": 7},
                {"name": "B", "model": "deleted-model", "config_id": 9},
            ],
        }
        configs = [{"id": 7, "name": "A", "model": "model-a"}]

        preset = build_run_preset(transcript, configs)

        self.assertFalse(preset["resolved"])
        self.assertEqual(preset["missing_models"][0]["name"], "B")


if __name__ == "__main__":
    unittest.main()
