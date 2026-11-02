import tempfile
import unittest
from pathlib import Path

from apps.arena import database


class HistoryDatabaseTest(unittest.TestCase):
    def test_finish_run_updates_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "arena.db"
            database.create_run(
                run_id="run-1",
                proposition="测试",
                vote_mode="eliminate",
                participants=2,
                started_at="2026-01-01 12:00:00",
                db_path=db_path,
            )
            database.finish_run(
                run_id="run-1",
                status="done",
                winner="mock#2",
                duration=3.2,
                db_path=db_path,
            )
            row = database.get_run("run-1", db_path=db_path)

        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "done")
        self.assertEqual(row["winner"], "mock#2")


class ModelDatabaseTest(unittest.TestCase):
    def test_model_crud_never_lists_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "arena.db"
            created = database.create_model(
                name="模型A",
                base_url="https://example.com/v1",
                api_key="secret-key",
                model="model-a",
                system_prompt="简洁回答",
                temperature=0.5,
                db_path=db_path,
            )
            rows = database.list_models(db_path=db_path)
            full = database.get_model(created["id"], db_path=db_path)
            updated = database.update_model(
                created["id"],
                name="模型B",
                base_url="https://example.com/v2",
                api_key=None,
                model="model-b",
                system_prompt="详细回答",
                temperature=0.8,
                db_path=db_path,
            )
            deleted = database.delete_model(created["id"], db_path=db_path)

        self.assertEqual(rows[0]["name"], "模型A")
        self.assertNotIn("api_key", rows[0])
        self.assertEqual(rows[0]["has_api_key"], 1)
        self.assertEqual(full["api_key"], "secret-key")
        self.assertEqual(updated["name"], "模型B")
        self.assertEqual(updated["api_key"], "secret-key")
        self.assertEqual(updated["temperature"], 0.8)
        self.assertTrue(deleted)


if __name__ == "__main__":
    unittest.main()
