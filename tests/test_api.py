import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.arena import database
from apps.arena.api import (
    accuracy,
    build_run_preset,
    delete_history,
    export_history,
    profiles,
    restore_history,
)
from apps.arena.schemas import ModelNameRequest, StartRun
from apps.arena.services import ConflictError, Manager


class RunPresetTest(unittest.TestCase):
    def test_name_suggestion_can_reuse_an_existing_saved_key(self) -> None:
        request = ModelNameRequest.model_validate({
            "model_id": 7,
            "base_url": "http://127.0.0.1:1/v1",
            "model": "test-model",
            "api_key": "",
        })

        self.assertEqual(request.model_id, 7)
        self.assertEqual(request.api_key, "")

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
        self.assertEqual(preset["mode"], "debate")

    def test_review_preset_restores_judge_and_perspective_switch(self) -> None:
        transcript = {
            "mode": "review",
            "proposition": "test",
            "judge": {"name": "Judge", "model": "judge-model"},
            "setup": {
                "mode": "review",
                "model_ids": [2, 3],
                "judge_model_id": 4,
                "diversify": False,
            },
            "participants": [
                {"name": "A", "config_id": 2},
                {"name": "B", "config_id": 3},
            ],
        }
        configs = [{"id": 2}, {"id": 3}, {"id": 4}]

        preset = build_run_preset(transcript, configs)

        self.assertEqual(preset["mode"], "review")
        self.assertEqual(preset["judge_model_id"], 4)
        self.assertFalse(preset["diversify"])
        self.assertTrue(preset["resolved"])

    def test_transcript_without_setup_is_rejected(self) -> None:
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

        with self.assertRaisesRegex(ValueError, "setup"):
            build_run_preset(transcript, configs)

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


class ArchiveInsightsTest(unittest.TestCase):
    def _seed(self, root: Path) -> Path:
        db_path = root / "arena.db"
        run_dir = root / "runs" / "20261103-120000-run"
        run_dir.mkdir(parents=True)
        database.create_run(
            run_id="run-1",
            proposition="测试方案",
            mode="review",
            vote_mode="review",
            participants=2,
            started_at="2026-11-03 12:00:00",
            run_dir=str(run_dir),
            db_path=db_path,
        )
        database.finish_run(
            run_id="run-1",
            status="done",
            winner="甲",
            duration=90,
            run_dir=str(run_dir),
            db_path=db_path,
        )
        transcript = {
            "mode": "review",
            "proposition": "测试方案",
            "judge": {"name": "裁判A", "model": "judge-a"},
            "recommended": "方案1",
            "recommended_agent": "甲",
            "ranking": ["方案1", "方案2"],
            "ranks": {"方案1": 1, "方案2": 2},
            "participants": [
                {"name": "甲", "config_id": 1, "model": "model-a"},
                {"name": "乙", "config_id": 2, "model": "model-a"},
            ],
            "answers": [
                {"agent": "甲", "text": "方案一", "error": None},
                {"agent": "乙", "text": "方案二", "error": None},
            ],
            "labels": [
                {"agent": "甲", "label": "方案1"},
                {"agent": "乙", "label": "方案2"},
            ],
            "scores": {
                "方案1": {"可行性": 8, "正确性": 8, "完备性": 8, "差异度": 6},
                "方案2": {"可行性": 7, "正确性": 7, "完备性": 7, "差异度": 9},
            },
        }
        (run_dir / "transcript.json").write_text(
            json.dumps(transcript, ensure_ascii=False), encoding="utf-8"
        )
        (run_dir / "review.md").write_text("# 战报\n", encoding="utf-8")
        return db_path

    def test_accuracy_profiles_export_delete_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = self._seed(root)
            with patch.object(database, "DB_PATH", db_path):
                database.save_decision(
                    run_id="run-1",
                    decision="adopted",
                    adopted_kind="label",
                    adopted_ref="方案1",
                    db_path=db_path,
                )
                stats = accuracy("review")
                profile_data = profiles("review")
                markdown = export_history("run-1", "md")
                archive = export_history("run-1", "zip")
                deleted = delete_history("run-1", purge_files=False)
                hidden = database.list_runs(db_path=db_path)
                restored = restore_history("run-1")

        self.assertEqual(stats["summary"]["n_completed"], 1)
        self.assertEqual(stats["summary"]["recommend_adopted"], 1)
        self.assertEqual(stats["summary"]["top1_hit"], 1)
        self.assertEqual(len(profile_data["rows"]), 2)
        self.assertTrue(all(row["suspected_same_model"] for row in profile_data["rows"]))
        self.assertEqual(markdown.body, b"# \xe6\x88\x98\xe6\x8a\xa5\n")
        self.assertEqual(archive.media_type, "application/zip")
        self.assertTrue(deleted["deleted"])
        self.assertEqual(hidden, [])
        self.assertEqual(restored["run"]["status"], "done")

    def test_same_source_judge_is_rejected_before_run_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "arena.db"
            with patch.object(database, "DB_PATH", db_path):
                a = database.create_model(
                    name="甲",
                    base_url="http://127.0.0.1:1/v1",
                    api_key="a",
                    model="same-model",
                    db_path=db_path,
                )
                b = database.create_model(
                    name="乙",
                    base_url="http://127.0.0.1:1/v1",
                    api_key="b",
                    model="same-model",
                    db_path=db_path,
                )
                judge = database.create_model(
                    name="裁判",
                    base_url="http://127.0.0.1:1/v1",
                    api_key="c",
                    model="same-model",
                    db_path=db_path,
                )
                payload = StartRun.model_validate({
                    "proposition": "测试",
                    "mode": "review",
                    "model_ids": [a["id"], b["id"]],
                    "judge_model_id": judge["id"],
                })
                with self.assertRaisesRegex(ConflictError, "同源"):
                    Manager().start(payload)
                self.assertEqual(database.list_runs(db_path=db_path), [])


if __name__ == "__main__":
    unittest.main()
