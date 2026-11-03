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
    database.mark_stale_runs_interrupted()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_TITLE, version=settings.APP_VERSION, lifespan=lifespan)
    app.include_router(router, prefix="/api")
    app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")

    @app.middleware("http")
    async def revalidate_frontend_assets(request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            # 前端无构建产物；必须每次用 ETag 重新验证，避免浏览器长期跑旧脚本。
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(settings.TEMPLATES_DIR / "index.html")

    return app
