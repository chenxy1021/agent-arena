"""SQLite 历史索引：只存提问与结果元数据，完整战报仍在 runs/ 下。"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from config import settings

DB_PATH = Path(os.environ.get("ARENA_DB", settings.DATABASE_PATH))

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    proposition TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'debate',
    vote_mode TEXT NOT NULL DEFAULT 'eliminate',
    status TEXT NOT NULL,
    winner TEXT,
    error TEXT,
    participants INTEGER NOT NULL DEFAULT 0,
    duration REAL,
    started_at TEXT,
    finished_at TEXT,
    run_dir TEXT,
    created_ts REAL NOT NULL,
    decision TEXT NOT NULL DEFAULT 'pending',
    deleted_at REAL,
    deleted_status TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_ts DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    adopted_kind TEXT,
    adopted_ref TEXT,
    reason_code TEXT,
    note TEXT NOT NULL DEFAULT '',
    decided_at REAL NOT NULL,
    reverted_at REAL,
    version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_decisions_run ON decisions(run_id, decided_at DESC);
CREATE TABLE IF NOT EXISTS model_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    api_key TEXT NOT NULL,
    model TEXT NOT NULL,
    system_prompt TEXT NOT NULL DEFAULT '',
    temperature REAL,
    persona TEXT NOT NULL DEFAULT '',
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL,
    model_key_norm TEXT
);
CREATE INDEX IF NOT EXISTS idx_model_configs_created ON model_configs(created_ts DESC);
"""


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        columns = {
            str(row["name"]) for row in conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        if "mode" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN mode TEXT NOT NULL DEFAULT 'debate'")
        if "decision" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN decision TEXT NOT NULL DEFAULT 'pending'")
        if "deleted_at" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN deleted_at REAL")
        if "deleted_status" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN deleted_status TEXT")
        model_columns = {
            str(row["name"]) for row in conn.execute("PRAGMA table_info(model_configs)").fetchall()
        }
        if "model_key_norm" not in model_columns:
            conn.execute("ALTER TABLE model_configs ADD COLUMN model_key_norm TEXT")
        conn.execute(
            """
            UPDATE model_configs
            SET model_key_norm = lower(trim(model))
            WHERE model_key_norm IS NULL OR model_key_norm = ''
            """
        )
        if version < 1:
            conn.execute("PRAGMA user_version = 1")


def create_model(
    *,
    name: str,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str = "",
    temperature: float | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    now = time.time()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO model_configs
                (name, base_url, api_key, model, system_prompt, temperature,
                 created_ts, updated_ts, model_key_norm)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name, base_url, api_key, model, system_prompt, temperature,
                now, now, model.strip().lower(),
            ),
        )
        model_id = int(cursor.lastrowid)
    return get_model(model_id, db_path=db_path) or {}


def list_models(db_path: Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, name, base_url, model, system_prompt, temperature,
                   created_ts, updated_ts, 1 AS has_api_key
            FROM model_configs
            ORDER BY created_ts DESC, id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_model(model_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM model_configs WHERE id = ?", (model_id,)).fetchone()
    return dict(row) if row else None


def update_model(
    model_id: int,
    *,
    name: str,
    base_url: str,
    api_key: str | None,
    model: str,
    system_prompt: str = "",
    temperature: float | None = None,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    current = get_model(model_id, db_path=db_path)
    if not current:
        return None
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE model_configs
            SET name = ?, base_url = ?, api_key = ?, model = ?,
                system_prompt = ?, temperature = ?, updated_ts = ?,
                model_key_norm = ?
            WHERE id = ?
            """,
            (
                name,
                base_url,
                api_key or current["api_key"],
                model,
                system_prompt,
                temperature,
                time.time(),
                model.strip().lower(),
                model_id,
            ),
        )
    return get_model(model_id, db_path=db_path)


def delete_model(model_id: int, db_path: Path | None = None) -> bool:
    init_db(db_path)
    with _connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM model_configs WHERE id = ?", (model_id,))
    return cursor.rowcount > 0


def create_run(
    *,
    run_id: str,
    proposition: str,
    mode: str = "debate",
    vote_mode: str,
    participants: int,
    started_at: str,
    run_dir: str = "",
    db_path: Path | None = None,
) -> None:
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO runs
                (id, proposition, mode, vote_mode, status, participants, started_at, run_dir, created_ts)
            VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?)
            """,
            (run_id, proposition, mode, vote_mode, participants, started_at, run_dir, time.time()),
        )


def update_run_dir(run_id: str, run_dir: str, db_path: Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute("UPDATE runs SET run_dir = ? WHERE id = ?", (run_dir, run_id))


def finish_run(
    *,
    run_id: str,
    status: str,
    winner: str | None = None,
    error: str | None = None,
    duration: float | None = None,
    run_dir: str = "",
    db_path: Path | None = None,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE runs
            SET status = ?, winner = ?, error = ?, duration = ?,
                run_dir = COALESCE(NULLIF(?, ''), run_dir), finished_at = ?
            WHERE id = ?
            """,
            (status, winner, error, duration, run_dir, time.strftime("%Y-%m-%d %H:%M:%S"), run_id),
        )


def list_runs(limit: int = 50, db_path: Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, proposition, mode, vote_mode, status, winner, error,
                   participants, duration, started_at, finished_at, run_dir, created_ts,
                   decision
            FROM runs
            WHERE deleted_at IS NULL
            ORDER BY created_ts DESC
            LIMIT ?
            """,
            (max(1, min(limit, 200)),),
        ).fetchall()
    return [dict(row) for row in rows]


def get_run(run_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def soft_delete_run(
    run_id: str, *, purge_files: bool = False, db_path: Path | None = None
) -> dict[str, Any] | None:
    """Hide a run from lists; physical file removal is explicit and irreversible."""
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT status, run_dir FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        target = Path(str(row["run_dir"] or "")).resolve()
        runs_root = settings.RUNS_DIR.resolve()
        if purge_files and row["run_dir"] and (
            target == runs_root or runs_root not in target.parents
        ):
            raise ValueError("战报目录不在 runs/ 范围内，已拒绝物理删除")
        conn.execute(
            """
            UPDATE runs
            SET deleted_at = ?, deleted_status = ?, status = 'deleted'
            WHERE id = ?
            """,
            (time.time(), row["status"], run_id),
        )
    meta = get_run(run_id, db_path=db_path) or {}
    if purge_files and meta.get("run_dir"):
        import shutil

        if target.exists():
            shutil.rmtree(target)
        with _connect(db_path) as conn:
            conn.execute("DELETE FROM decisions WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    return meta


def restore_run(run_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT deleted_at, deleted_status FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        if not row:
            return None
        if row["deleted_at"] is None:
            return get_run(run_id, db_path=db_path)
        if time.time() - float(row["deleted_at"]) > 30 * 24 * 60 * 60:
            raise ValueError("软删除已超过 30 天，无法恢复")
        restored = str(row["deleted_status"] or "done")
        conn.execute(
            """
            UPDATE runs
            SET status = ?, deleted_at = NULL, deleted_status = NULL
            WHERE id = ?
            """,
            (restored, run_id),
        )
    return get_run(run_id, db_path=db_path)


def mark_stale_runs_interrupted(db_path: Path | None = None) -> int:
    """服务启动时把陈旧的 running 记录刷成 interrupted，避免被当成进行中接回来。"""
    init_db(db_path)
    with _connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE runs SET status = 'interrupted' WHERE status = 'running'"
        )
        return cursor.rowcount


def save_decision(
    *,
    run_id: str,
    decision: str,
    adopted_kind: str | None = None,
    adopted_ref: str | None = None,
    reason_code: str | None = None,
    note: str = "",
    db_path: Path | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    now = time.time()
    with _connect(db_path) as conn:
        version = int(
            conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM decisions WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
        )
        conn.execute(
            """
            INSERT INTO decisions
                (run_id, decision, adopted_kind, adopted_ref, reason_code, note,
                 decided_at, version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, decision, adopted_kind, adopted_ref, reason_code,
             note.strip(), now, version),
        )
        conn.execute("UPDATE runs SET decision = ? WHERE id = ?", (decision, run_id))
    return latest_decision(run_id, db_path=db_path) or {}


def latest_decision(run_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM decisions
            WHERE run_id = ? AND reverted_at IS NULL
            ORDER BY decided_at DESC, id DESC
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()
    return dict(row) if row else None


def decision_history(run_id: str, db_path: Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM decisions WHERE run_id = ? ORDER BY decided_at DESC, id DESC",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def revert_decision(run_id: str, db_path: Path | None = None) -> bool:
    init_db(db_path)
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE decisions SET reverted_at = ?
            WHERE run_id = ? AND reverted_at IS NULL
            """,
            (time.time(), run_id),
        )
        conn.execute("UPDATE runs SET decision = 'pending' WHERE id = ?", (run_id,))
    return cursor.rowcount > 0
