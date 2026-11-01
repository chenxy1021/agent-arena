"""ASGI 入口：uvicorn config.asgi:app"""

from config.urls import create_app

app = create_app()
