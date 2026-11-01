"""FastAPI 后端：启动比赛、实时 SSE、SQLite 历史与 Vue 静态页面。"""

from __future__ import annotations

import asyncio
import copy
import json
import socket
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import database
from .adapters import CliAgent, discover, make_custom_agent, unavailable_agents
from .events import RecordingSink
from .mock import MockAgent
from .moderator import Arena, ArenaConfig

WEB_DIR = Path(__file__).parent / "web"
RUNS_DIR = Path.cwd() / "runs"


class CustomAgent(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    cmd: str = Field(min_length=1, max_length=2000)


class StartRun(BaseModel):
    proposition: str = Field(min_length=1, max_length=2000)
    vote_mode: Literal["eliminate", "support"] = "eliminate"
    agents: list[str] = Field(default_factory=list)
    customs: list[CustomAgent] = Field(default_factory=list)
    repeat: int = Field(default=1, ge=1, le=8)
    max_rounds: int = Field(default=0, ge=0, le=30)
    timeout: float = Field(default=240, ge=5, le=1200)
    mock: int = Field(default=0, ge=0, le=16)
    refresh: bool = False


class RunState:
    def __init__(self, run_id: str, proposition: str):
        self.id = run_id
        self.proposition = proposition
        self.status = "running"
        self.error: str | None = None
        self.result: dict[str, Any] | None = None
        self.run_dir = ""
        self.started_ts = time.time()
        self.sink = RecordingSink()

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "proposition": self.proposition,
            "status": self.status,
            "error": self.error,
            "events": self.sink.count(),
            "run_dir": self.run_dir,
        }


class Manager:
    def __init__(self) -> None:
        self.runs: dict[str, RunState] = {}
        self.lock = threading.Lock()
        self._agent_cache: dict[str, Any] = {"at": 0.0, "agents": []}
        self._cache_ttl = 30.0

    def get(self, run_id: str) -> RunState | None:
        with self.lock:
            return self.runs.get(run_id)

    def active(self) -> RunState | None:
        with self.lock:
            return next((run for run in self.runs.values() if run.status == "running"), None)

    def list_agents(self, deep: bool = True, refresh: bool = False) -> list[CliAgent]:
        with self.lock:
            fresh = time.monotonic() - self._agent_cache["at"] < self._cache_ttl
            if fresh and not refresh and self._agent_cache["agents"]:
                return self._agent_cache["agents"]
            agents = discover(deep=deep)
            self._agent_cache.update(at=time.monotonic(), agents=agents)
            return agents

    def start(self, payload: StartRun) -> RunState:
        proposition = payload.proposition.strip()
        if not proposition:
            raise ValueError("命题不能为空")

        agents: list[Any] = []
        if payload.mock:
            agents = [MockAgent(name=f"mock{i + 1}") for i in range(max(payload.mock, 2))]
        else:
            found = self.list_agents(refresh=payload.refresh)
            blocked = unavailable_agents()
            selected = set(payload.agents)
            picked = [a for a in found if a.spec.key in selected] if selected else [
                a for a in found if a.spec.key not in blocked
            ]
            for agent in picked:
                for _ in range(payload.repeat):
                    agents.append(copy.copy(agent))
            for item in payload.customs:
                try:
                    custom = make_custom_agent(item.name.strip(), item.cmd.strip())
                except ValueError as exc:
                    raise ValueError(f"自定义命令无效：{exc}") from exc
                for _ in range(payload.repeat):
                    agents.append(copy.copy(custom))

        if len(agents) < 2:
            raise ValueError("至少需要 2 个 agent（可提高每个 CLI 的实例数）")

        run_id = uuid.uuid4().hex[:12]
        run = RunState(run_id, proposition)
        started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        database.create_run(
            run_id=run_id,
            proposition=proposition,
            vote_mode=payload.vote_mode,
            participants=len(agents),
            started_at=started_at,
        )

        cfg = ArenaConfig(
            proposition=proposition,
            max_rounds=payload.max_rounds,
            timeout=payload.timeout,
            out_dir=RUNS_DIR,
            vote_mode=payload.vote_mode,
        )

        def worker() -> None:
            try:
                arena = Arena(agents, cfg, sink=run.sink)
                run.run_dir = str(arena.run_dir)
                database.update_run_dir(run_id, run.run_dir)
                result = arena.run()
                run.result = result.to_dict()
                run.status = "done"
                database.finish_run(
                    run_id=run_id,
                    status="done",
                    winner=result.winner,
                    duration=result.duration,
                    run_dir=run.run_dir,
                )
            except Exception as exc:
                run.error = f"{type(exc).__name__}: {exc}"
                run.status = "error"
                run.sink.emit("error", message=run.error)
                run.sink.emit("done", duration=0, rounds=0, winner=None, run_dir=run.run_dir)
                database.finish_run(
                    run_id=run_id,
                    status="error",
                    error=run.error,
                    run_dir=run.run_dir,
                )

        with self.lock:
            self.runs[run_id] = run
        threading.Thread(target=worker, daemon=True, name=f"arena-{run_id}").start()
        return run


manager = Manager()
app = FastAPI(title="Agent Arena", version="2.0.0")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.on_event("startup")
def startup() -> None:
    database.init_db()
    database.sync_run_history()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/agents")
def agents(refresh: bool = False, deep: bool = True) -> dict[str, Any]:
    found = manager.list_agents(deep=deep, refresh=refresh)
    blocked = unavailable_agents()
    return {
        "agents": [
            {
                "key": agent.spec.key,
                "label": agent.label,
                "path": agent.path,
                "version": agent.version,
                "note": agent.spec.note,
                "requires": agent.spec.requires,
                "discovered": agent.spec.discovered,
                "unavailable": blocked.get(agent.spec.key, ""),
            }
            for agent in found
        ]
    }


@app.post("/api/runs", status_code=201)
def start_run(payload: StartRun) -> dict[str, str]:
    try:
        run = manager.start(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run": run.id}


@app.get("/api/runs/active")
def active_run() -> dict[str, Any]:
    run = manager.active()
    return {"run": run.snapshot() if run else None}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, after: int = Query(default=0, ge=0)):
    run = manager.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    header = request.headers.get("last-event-id")
    start = max(after, int(header)) if header and header.isdigit() else after

    async def stream():
        index = start
        last_heartbeat = time.monotonic()
        while True:
            events = run.sink.since(index)
            for event in events:
                payload = json.dumps(event, ensure_ascii=False)
                yield f"id: {index}\ndata: {payload}\n\n"
                index += 1
            if run.status != "running" and not events:
                yield "event: end\ndata: {}\n\n"
                return
            if time.monotonic() - last_heartbeat >= 10:
                yield ": keepalive\n\n"
                last_heartbeat = time.monotonic()
            if not events:
                await asyncio.sleep(0.2)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/history")
def history(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return {"runs": database.list_runs(limit)}


@app.get("/api/history/{run_id}")
def history_run(run_id: str) -> dict[str, Any]:
    meta = database.get_run(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="history not found")
    transcript = None
    run_dir = Path(meta.get("run_dir") or "")
    if not run_dir.is_absolute():
        run_dir = RUNS_DIR / run_id
    transcript_path = run_dir / "transcript.json"
    if transcript_path.is_file():
        try:
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            transcript = None
    return {"meta": meta, "transcript": transcript}


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
    if not (WEB_DIR / "vendor" / "vue.global.prod.js").is_file():
        print("缺少 Vue 运行时：agent_arena/web/vendor/vue.global.prod.js")
        return 1
    database.init_db()
    database.sync_run_history()
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
