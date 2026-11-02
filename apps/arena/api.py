"""Agent Arena API 路由。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from . import database
from .providers import ApiModelAgent, suggest_display_name
from .schemas import PERSONA_KEYS, ModelCreate, ModelNameRequest, ModelUpdate, StartRun
from .services import manager

router = APIRouter()


def _persona(value: str) -> str:
    """人格只接受预设值；空串表示不分配。"""
    value = (value or "").strip()
    return value if value in PERSONA_KEYS else ""


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/models")
def models() -> dict[str, Any]:
    return {"models": database.list_models()}


@router.post("/models", status_code=201)
def create_model(payload: ModelCreate) -> dict[str, Any]:
    name = payload.name.strip()
    base_url = payload.base_url.strip()
    api_key = payload.api_key.strip()
    model = payload.model.strip()
    if not name or not api_key or not model:
        raise HTTPException(status_code=400, detail="名称、API Key 和模型 ID 不能为空")
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Base URL 必须以 http:// 或 https:// 开头")
    config = database.create_model(
        name=name,
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=payload.system_prompt.strip(),
        temperature=payload.temperature,
        persona=_persona(payload.persona),
    )
    config.pop("api_key", None)
    config["has_api_key"] = True
    return config


@router.delete("/models/{model_id}")
def remove_model(model_id: int) -> dict[str, bool]:
    if not database.delete_model(model_id):
        raise HTTPException(status_code=404, detail="模型配置不存在")
    return {"deleted": True}


@router.put("/models/{model_id}")
def update_model(model_id: int, payload: ModelUpdate) -> dict[str, Any]:
    name = payload.name.strip()
    base_url = payload.base_url.strip()
    api_key = payload.api_key.strip()
    model = payload.model.strip()
    if not name or not model:
        raise HTTPException(status_code=400, detail="名称和模型 ID 不能为空")
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Base URL 必须以 http:// 或 https:// 开头")
    config = database.update_model(
        model_id,
        name=name,
        base_url=base_url,
        api_key=api_key or None,
        model=model,
        system_prompt=payload.system_prompt.strip(),
        temperature=payload.temperature,
        persona=_persona(payload.persona),
    )
    if not config:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    config.pop("api_key", None)
    config["has_api_key"] = True
    return config


@router.post("/models/suggest-name")
def suggest_model_name(payload: ModelNameRequest) -> dict[str, str]:
    base_url = payload.base_url.strip()
    api_key = payload.api_key.strip()
    model = payload.model.strip()
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Base URL 必须以 http:// 或 https:// 开头")
    if not model:
        raise HTTPException(status_code=400, detail="模型 ID 不能为空")
    if payload.model_id and not api_key:
        existing = database.get_model(payload.model_id)
        if not existing:
            raise HTTPException(status_code=404, detail="模型配置不存在")
        api_key = str(existing["api_key"])
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")

    agent = ApiModelAgent(
        config_id=payload.model_id or 0,
        name="命名助手",
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt="",
        temperature=1.0,
    )
    try:
        return {"name": suggest_display_name(agent)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs", status_code=201)
def start_run(payload: StartRun) -> dict[str, str]:
    try:
        run = manager.start(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run": run.id}


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: str) -> dict[str, Any]:
    if not manager.cancel(run_id):
        raise HTTPException(status_code=404, detail="run not running")
    return {"stopped": True}


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
                index += 1
                yield f"id: {index}\ndata: {payload}\n\n"
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
    runs = database.list_runs(limit)
    for run in runs:
        transcript = _read_transcript(run)
        if not transcript:
            continue
        roles = transcript.get("participants") or []
        run["participant_names"] = [
            str(item.get("name"))
            for item in roles
            if isinstance(item, dict) and item.get("name")
        ]
        run["eliminated_names"] = [
            str(round_record.get("eliminated"))
            for round_record in transcript.get("rounds") or []
            if isinstance(round_record, dict) and round_record.get("eliminated")
        ]
        run["round_count"] = len(transcript.get("rounds") or [])
        run["stop_reason"] = str(transcript.get("stop_reason") or "")
        run["converged"] = bool(transcript.get("converged"))
        run["reusable"] = len(
            (transcript.get("setup") or {}).get("model_ids", [])
        ) >= 2
    return {"runs": runs}


def _read_transcript(meta: dict[str, Any]) -> dict[str, Any] | None:
    run_dir = meta.get("run_dir")
    if not run_dir:
        return None
    transcript_path = Path(str(run_dir)) / "transcript.json"
    if not transcript_path.is_file():
        return None
    try:
        data = json.loads(transcript_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def build_run_preset(
    transcript: dict[str, Any], configs: list[dict[str, Any]]
) -> dict[str, Any]:
    """Resolve a historical match into a safe setup draft for a new run."""
    setup = transcript.get("setup")
    if not isinstance(setup, dict):
        raise ValueError("战报缺少当前版本所需的 setup 快照")
    participants = transcript.get("participants") or []
    by_id = {int(item["id"]): item for item in configs}
    participant_by_id = {
        int(item.get("config_id") or 0): item
        for item in participants
        if int(item.get("config_id") or 0)
    }
    model_ids = [
        int(value)
        for value in setup.get("model_ids", [])
        if int(value or 0) > 0
    ]
    if len(model_ids) < 2:
        raise ValueError("战报缺少至少两个模型配置 ID")

    missing_models: list[dict[str, str]] = []
    for config_id in model_ids:
        if config_id in by_id:
            continue
        participant = participant_by_id.get(config_id) or {}
        missing_models.append({
            "name": str(participant.get("name") or f"配置 #{config_id}"),
            "model": str(participant.get("model") or participant.get("label") or ""),
        })

    return {
        "proposition": str(transcript.get("proposition") or ""),
        "vote_mode": str(setup.get("vote_mode") or "eliminate"),
        "speech_mode": str(setup.get("speech_mode") or "parallel_buffered"),
        "timeout": float(setup.get("timeout") or 240),
        "background": str(setup.get("background") or ""),
        "constraints": list(setup.get("constraints") or []),
        "criteria": list(setup.get("criteria") or []),
        "model_ids": model_ids,
        "missing_models": missing_models,
        "resolved": len(model_ids) >= 2 and not missing_models,
    }


@router.get("/history/{run_id}")
def history_run(run_id: str) -> dict[str, Any]:
    meta = database.get_run(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="history not found")
    transcript = _read_transcript(meta)
    return {"meta": meta, "transcript": transcript}


@router.get("/history/{run_id}/preset")
def history_preset(run_id: str) -> dict[str, Any]:
    meta = database.get_run(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="history not found")
    transcript = _read_transcript(meta)
    if not transcript:
        raise HTTPException(status_code=404, detail="transcript not found")
    try:
        return build_run_preset(transcript, database.list_models())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
