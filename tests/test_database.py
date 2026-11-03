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
        self.assertEqual(row["mode"], "debate")

    def test_old_database_gets_mode_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "arena.db"
            with database._connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE runs (id TEXT PRIMARY KEY, proposition TEXT NOT NULL, "
                    "vote_mode TEXT NOT NULL DEFAULT 'eliminate', status TEXT NOT NULL, "
                    "winner TEXT, error TEXT, participants INTEGER NOT NULL DEFAULT 0, "
                    "duration REAL, started_at TEXT, finished_at TEXT, run_dir TEXT, "
                    "created_ts REAL NOT NULL)"
                )
            database.init_db(db_path)
            with database._connect(db_path) as conn:
                columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(runs)")
                }
                version = conn.execute("PRAGMA user_version").fetchone()[0]

        self.assertIn("mode", columns)
        self.assertEqual(version, 1)

    def test_decision_history_and_revert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "arena.db"
            database.create_run(
                run_id="run-1",
                proposition="测试",
                mode="review",
                vote_mode="review",
                participants=2,
                started_at="2026-01-01 12:00:00",
                db_path=db_path,
            )
            database.finish_run(run_id="run-1", status="done", db_path=db_path)
            first = database.save_decision(
                run_id="run-1",
                decision="adopted",
                adopted_kind="label",
                adopted_ref="方案1",
                db_path=db_path,
            )
            database.revert_decision("run-1", db_path=db_path)
            second = database.save_decision(
                run_id="run-1",
                decision="rejected",
                reason_code="infeasible",
                note="成本无法接受",
                db_path=db_path,
            )
            latest = database.latest_decision("run-1", db_path=db_path)
            history = database.decision_history("run-1", db_path=db_path)
            run = database.get_run("run-1", db_path=db_path)

        self.assertEqual(first["version"], 1)
        self.assertEqual(second["version"], 2)
        self.assertEqual(latest["decision"], "rejected")
        self.assertEqual(len(history), 2)
        self.assertIsNotNone(history[1]["reverted_at"])
        self.assertEqual(run["decision"], "rejected")

    def test_soft_delete_hides_run_and_restore_keeps_status(self) -> None:
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
            database.finish_run(run_id="run-1", status="cancelled", db_path=db_path)
            database.soft_delete_run("run-1", db_path=db_path)
            hidden = database.list_runs(db_path=db_path)
            deleted = database.get_run("run-1", db_path=db_path)
            restored = database.restore_run("run-1", db_path=db_path)

        self.assertEqual(hidden, [])
        self.assertEqual(deleted["status"], "deleted")
        self.assertEqual(restored["status"], "cancelled")


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
        self.assertEqual(full["model_key_norm"], "model-a")
        self.assertEqual(updated["name"], "模型B")
        self.assertEqual(updated["api_key"], "secret-key")
        self.assertEqual(updated["temperature"], 0.8)
        self.assertTrue(deleted)


if __name__ == "__main__":
    unittest.main()
