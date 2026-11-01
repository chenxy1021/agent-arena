"""开发服务器启动器，对应 Django manage.py runserver 的职责。"""

from __future__ import annotations

import socket
import threading
import webbrowser

import uvicorn

from config import settings
from config.asgi import app


def _free_port(port: int) -> int | None:
    for offset in range(12):
        candidate = port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return candidate
    return None


def serve(port: int = 7788, open_browser: bool = True) -> int:
    if not (settings.STATIC_DIR / "vendor" / "vue.global.prod.js").is_file():
        print("缺少 Vue 运行时：static/vendor/vue.global.prod.js")
        return 1
    chosen = _free_port(port)
    if chosen is None:
        print(f"端口 {port}-{port + 11} 都被占用，启动失败")
        return 1
    url = f"http://127.0.0.1:{chosen}/"
    print(f"Agent Arena 已启动：{url}")
    print("按 Ctrl+C 停止")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=chosen, log_level="warning")
    except KeyboardInterrupt:
        print("\n已停止")
    return 0
