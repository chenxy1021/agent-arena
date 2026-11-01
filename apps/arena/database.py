"""SQLite 历史索引：只存提问与结果元数据，完整战报仍在 runs/ 下。"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from config import settings

DB_PATH = Path(os.environ.get("ARENA_DB", settings.DATABASE_PATH))
RUNS_DIR = settings.RUNS_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    proposition TEXT NOT NULL,
    vote_mode TEXT NOT NULL DEFAULT 'eliminate',
    status TEXT NOT NULL,
    winner TEXT,
    error TEXT,
    participants INTEGER NOT NULL DEFAULT 0,
    duration REAL,
    started_at TEXT,
    finished_at TEXT,
    run_dir TEXT,
    created_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_ts DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE TABLE IF NOT EXISTS model_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    api_key TEXT NOT NULL,
    model TEXT NOT NULL,
    system_prompt TEXT NOT NULL DEFAULT '',
    temperature REAL,
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL
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
                (name, base_url, api_key, model, system_prompt, temperature, created_ts, updated_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, base_url, api_key, model, system_prompt, temperature, now, now),
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
                system_prompt = ?, temperature = ?, updated_ts = ?
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
                (id, proposition, vote_mode, status, participants, started_at, run_dir, created_ts)
            VALUES (?, ?, ?, 'running', ?, ?, ?, ?)
            """,
            (run_id, proposition, vote_mode, participants, started_at, run_dir, time.time()),
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
            SELECT id, proposition, vote_mode, status, winner, error,
                   participants, duration, started_at, finished_at, run_dir, created_ts
            FROM runs
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


def sync_run_history(runs_dir: Path | None = None, db_path: Path | None = None) -> None:
    """把旧版 runs/ 战报补进 SQLite，保留已有记录不覆盖。"""
    root = Path(runs_dir or RUNS_DIR)
    if not root.is_dir():
        return
    init_db(db_path)
    for run_dir in sorted(root.iterdir()):
        transcript = run_dir / "transcript.json"
        if not transcript.is_file():
            continue
        try:
            data = json.loads(transcript.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        created = data.get("started_at") or ""
        try:
            created_ts = time.mktime(time.strptime(created, "%Y-%m-%d %H:%M:%S"))
        except (TypeError, ValueError):
            created_ts = run_dir.stat().st_mtime
        with _connect(db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO runs
                    (id, proposition, vote_mode, status, winner, participants,
                     duration, started_at, finished_at, run_dir, created_ts)
                VALUES (?, ?, ?, 'done', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_dir.name,
                    data.get("proposition", ""),
                    data.get("vote_mode", "eliminate"),
                    data.get("winner"),
                    len(data.get("participants") or []),
                    data.get("duration"),
                    created,
                    created,
                    str(run_dir.resolve()),
                    created_ts,
                ),
            )
