"""项目路由入口，类似 Django 的 urls.py。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.arena import database
from apps.arena.api import router
from config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_db()
    database.sync_run_history()
    database.mark_stale_runs_interrupted()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_TITLE, version=settings.APP_VERSION, lifespan=lifespan)
    app.include_router(router, prefix="/api")
    app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(settings.TEMPLATES_DIR / "index.html")

    return app
