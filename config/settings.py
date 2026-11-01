"""项目级路径与运行配置。"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
RUNS_DIR = BASE_DIR / "runs"
DATABASE_PATH = Path(os.environ.get("ARENA_DB", BASE_DIR / "arena.db"))

APP_TITLE = "Agent Arena"
APP_VERSION = "2.0.0"
