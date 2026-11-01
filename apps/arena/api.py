"""Agent Arena API 路由。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from config import settings

from . import database
from .adapters import unavailable_agents
from .schemas import StartRun
from .services import manager

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/agents")
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


@router.post("/runs", status_code=201)
def start_run(payload: StartRun) -> dict[str, str]:
    try:
        run = manager.start(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run": run.id}


@router.get("/runs/active")
def active_run() -> dict[str, Any]:
    run = manager.active()
    return {"run": run.snapshot() if run else None}


@router.get("/runs/{run_id}/events")
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


@router.get("/history")
def history(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return {"runs": database.list_runs(limit)}


@router.get("/history/{run_id}")
def history_run(run_id: str) -> dict[str, Any]:
    meta = database.get_run(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="history not found")
    transcript = None
    run_dir = Path(meta.get("run_dir") or "")
    if not run_dir.is_absolute():
        run_dir = settings.RUNS_DIR / run_id
    transcript_path = run_dir / "transcript.json"
    if transcript_path.is_file():
        try:
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            transcript = None
    return {"meta": meta, "transcript": transcript}
