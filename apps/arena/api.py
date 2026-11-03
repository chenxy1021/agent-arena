"""Agent Arena API 路由。"""

from __future__ import annotations

import asyncio
import io
import json
import re
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from config import settings

from . import database
from .providers import ApiModelAgent, suggest_display_name
from .review import ReviewArena, ReviewConfig
from .schemas import (
    DecisionCreate,
    ModelCreate,
    ModelNameRequest,
    ModelUpdate,
    SeatRetryRequest,
    StartRun,
)
from .services import ConflictError, manager

router = APIRouter()


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
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run": run.id, "mode": run.mode}


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
        run["mode"] = str(transcript.get("mode") or run.get("mode") or "debate")
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
        run["recommended_agent"] = str(transcript.get("recommended_agent") or "")
        run["judge_name"] = str((transcript.get("judge") or {}).get("name") or "")
        run["answer_count"] = len(transcript.get("answers") or [])
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

    mode = str(setup.get("mode") or transcript.get("mode") or "debate")
    judge_model_id = int(setup.get("judge_model_id") or 0)

    missing_models: list[dict[str, str]] = []
    for config_id in model_ids:
        if config_id in by_id:
            continue
        participant = participant_by_id.get(config_id) or {}
        missing_models.append({
            "name": str(participant.get("name") or f"配置 #{config_id}"),
            "model": str(participant.get("model") or participant.get("label") or ""),
        })
    missing_judge: dict[str, str] | None = None
    if mode == "review":
        if not judge_model_id:
            missing_judge = {"name": "裁判模型", "model": ""}
        elif judge_model_id not in by_id:
            judge = transcript.get("judge") or {}
            missing_judge = {
                "name": str(judge.get("name") or f"配置 #{judge_model_id}"),
                "model": str(judge.get("model") or judge.get("label") or ""),
            }

    return {
        "proposition": str(transcript.get("proposition") or ""),
        "mode": mode,
        "vote_mode": str(setup.get("vote_mode") or "eliminate"),
        "speech_mode": str(setup.get("speech_mode") or "parallel_buffered"),
        "timeout": float(setup.get("timeout") or 240),
        "background": str(setup.get("background") or ""),
        "constraints": list(setup.get("constraints") or []),
        "criteria": list(setup.get("criteria") or []),
        "model_ids": model_ids,
        "judge_model_id": judge_model_id or None,
        "diversify": bool(setup.get("diversify", True)),
        "missing_models": missing_models,
        "missing_judge": missing_judge,
        "resolved": len(model_ids) >= 2 and not missing_models and not missing_judge,
    }


@router.get("/history/{run_id}")
def history_run(run_id: str) -> dict[str, Any]:
    meta = database.get_run(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="history not found")
    transcript = _read_transcript(meta)
    if transcript and not transcript.get("mode"):
        transcript["mode"] = meta.get("mode") or "debate"
    return {"meta": meta, "transcript": transcript}


def _safe_filename(text: str) -> str:
    value = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "-", text.strip())
    return value.strip("-")[:36] or "agent-arena"


def _run_files(meta: dict[str, Any]) -> tuple[Path, Path, Path]:
    run_dir = Path(str(meta.get("run_dir") or "")).resolve()
    json_path = run_dir / "transcript.json"
    markdown_path = run_dir / "review.md"
    if not markdown_path.is_file():
        markdown_path = run_dir / "debate.md"
    return run_dir, json_path, markdown_path


@router.get("/history/{run_id}/export")
def export_history(
    run_id: str,
    format: str = Query(default="md", pattern="^(md|json|zip)$"),
) -> Response:
    meta = database.get_run(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="history not found")
    run_dir, json_path, markdown_path = _run_files(meta)
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="原始战报缺失")

    filename = _safe_filename(str(meta.get("proposition") or run_id))
    stamp = str(meta.get("started_at") or "").replace(":", "").replace(" ", "-")[:13]
    disposition = f"attachment; filename*=UTF-8''{quote(f'{filename}-{stamp}.{format}')}"

    if format == "md":
        if not markdown_path.is_file():
            raise HTTPException(status_code=404, detail="原始战报缺失")
        return Response(
            markdown_path.read_bytes(),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": disposition},
        )
    if format == "json":
        if not json_path.is_file():
            raise HTTPException(status_code=404, detail="原始战报缺失")
        return Response(
            json_path.read_bytes(),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": disposition},
        )
    if not json_path.is_file() or not markdown_path.is_file():
        raise HTTPException(status_code=404, detail="原始战报缺失")

    manifest = {
        "run_id": run_id,
        "proposition": meta.get("proposition"),
        "mode": meta.get("mode"),
        "status": meta.get("status"),
        "started_at": meta.get("started_at"),
        "finished_at": meta.get("finished_at"),
        "files": [markdown_path.name, json_path.name, "manifest.json"],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(markdown_path, markdown_path.name)
        archive.write(json_path, json_path.name)
        archive.writestr(
            "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
        )
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": disposition},
    )


@router.delete("/history/{run_id}")
def delete_history(
    run_id: str,
    purge_files: bool = Query(default=False),
) -> dict[str, Any]:
    if not database.get_run(run_id):
        raise HTTPException(status_code=404, detail="history not found")
    try:
        meta = database.soft_delete_run(run_id, purge_files=purge_files)
    except OSError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"索引已删，文件未删，可稍后重试：{exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": True, "purge_files": purge_files, "run": meta}


@router.post("/history/{run_id}/restore")
def restore_history(run_id: str) -> dict[str, Any]:
    if not database.get_run(run_id):
        raise HTTPException(status_code=404, detail="history not found")
    try:
        meta = database.restore_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    return {"restored": True, "run": meta}


@router.post("/history/{run_id}/retry")
def retry_history_seat(run_id: str, payload: SeatRetryRequest) -> dict[str, Any]:
    meta = database.get_run(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="history not found")
    if str(meta.get("mode") or "debate") != "review":
        raise HTTPException(status_code=400, detail="仅方案评审支持席位重跑")
    if meta.get("status") not in ("done", "cancelled"):
        raise HTTPException(status_code=400, detail="当前状态不支持席位重跑")
    transcript = _read_transcript(meta)
    if not transcript:
        raise HTTPException(status_code=404, detail="原始战报缺失")

    setup = transcript.get("setup") or {}
    agents = []
    configs: dict[int, dict[str, Any]] = {}
    for participant in transcript.get("participants") or []:
        config_id = int(participant.get("config_id") or 0)
        config = database.get_model(config_id) if config_id else None
        if not config:
            raise HTTPException(status_code=409, detail="模型配置已删除，请先恢复")
        configs[config_id] = config
        agents.append(
            ApiModelAgent(
                config_id=config_id,
                name=str(participant.get("name") or config["name"]),
                base_url=str(config["base_url"]),
                api_key=str(config["api_key"]),
                model=str(config["model"]),
                system_prompt=str(config.get("system_prompt") or ""),
                temperature=config.get("temperature"),
            )
        )
    judge_id = int(setup.get("judge_model_id") or 0)
    judge_config = database.get_model(judge_id) if judge_id else None
    if not judge_config:
        raise HTTPException(status_code=409, detail="裁判配置已删除，请先恢复")
    judge_info = transcript.get("judge") or {}
    judge = ApiModelAgent(
        config_id=judge_id,
        name=str(judge_info.get("name") or judge_config["name"]),
        base_url=str(judge_config["base_url"]),
        api_key=str(judge_config["api_key"]),
        model=str(judge_config["model"]),
        system_prompt=str(judge_config.get("system_prompt") or ""),
        temperature=judge_config.get("temperature"),
    )
    cfg = ReviewConfig(
        proposition=str(transcript.get("proposition") or meta.get("proposition") or ""),
        timeout=float(setup.get("timeout") or 240),
        out_dir=Path(str(meta.get("run_dir") or settings.RUNS_DIR)),
        criteria=list(setup.get("criteria") or []),
        background=str(setup.get("background") or ""),
        constraints=list(setup.get("constraints") or []),
        diversify=bool(setup.get("diversify", True)),
        run_id=run_id,
        judge_same_model=bool(transcript.get("judge_same_model")),
    )
    arena = ReviewArena(
        agents,
        judge,
        cfg,
        run_dir=Path(str(meta.get("run_dir") or "")),
    )
    try:
        result = arena.rerun_answer(transcript, payload.agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    database.finish_run(
        run_id=run_id,
        status="cancelled" if result.stop_reason == "用户中止" else "done",
        winner=result.recommended_agent,
        duration=result.duration,
        run_dir=arena.run_dir,
    )
    return {
        "retried": True,
        "winner": result.recommended_agent,
        "attempts": result.attempts,
        "stop_reason": result.stop_reason,
    }


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


@router.get("/history/{run_id}/decision")
def get_decision(run_id: str) -> dict[str, Any]:
    if not database.get_run(run_id):
        raise HTTPException(status_code=404, detail="history not found")
    return {
        "decision": database.latest_decision(run_id),
        "history": database.decision_history(run_id),
    }


@router.post("/history/{run_id}/decision", status_code=201)
def save_decision(run_id: str, payload: DecisionCreate) -> dict[str, Any]:
    meta = database.get_run(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="history not found")
    if meta.get("status") not in ("done", "cancelled"):
        raise HTTPException(status_code=400, detail="只有已结束或已中止的运行可以记录决策")
    note = payload.note.strip()
    if payload.decision in ("partial", "rejected") and len(note) < 5:
        raise HTTPException(status_code=400, detail="部分采纳或驳回需要至少 5 个字的备注")
    if payload.decision == "adopted" and not (payload.adopted_ref or "").strip():
        raise HTTPException(status_code=400, detail="采纳需要指定采纳对象")
    record = database.save_decision(
        run_id=run_id,
        decision=payload.decision,
        adopted_kind=payload.adopted_kind,
        adopted_ref=payload.adopted_ref,
        reason_code=payload.reason_code,
        note=note,
    )
    return {"decision": record, "history": database.decision_history(run_id)}


@router.delete("/history/{run_id}/decision")
def revert_decision(run_id: str) -> dict[str, Any]:
    if not database.get_run(run_id):
        raise HTTPException(status_code=404, detail="history not found")
    database.revert_decision(run_id)
    return {
        "decision": database.latest_decision(run_id),
        "history": database.decision_history(run_id),
    }


@router.get("/accuracy")
def accuracy(mode: str = Query(default="review", pattern="^(review|debate)$")) -> dict[str, Any]:
    runs = database.list_runs(200)
    rows: dict[str, dict[str, Any]] = {}
    summary = {
        "n_completed": 0,
        "n_decided": 0,
        "adopted": 0,
        "partial": 0,
        "rejected": 0,
        "undecided": 0,
        "recommend_adopted": 0,
        "top1_hit": 0,
    }
    for run in runs:
        if str(run.get("mode") or "debate") != mode or run.get("status") != "done":
            continue
        transcript = _read_transcript(run) or {}
        judge = transcript.get("judge") if isinstance(transcript.get("judge"), dict) else {}
        judge_name = str(
            judge.get("name") or judge.get("label") or transcript.get("judge_name") or "—"
        )
        row = rows.setdefault(
            judge_name,
            {
                "judge_model": judge_name,
                "n_completed": 0,
                "n_decided": 0,
                "adopted": 0,
                "partial": 0,
                "rejected": 0,
                "undecided": 0,
                "recommend_adopted": 0,
                "top1_hit": 0,
            },
        )
        for target in (summary, row):
            target["n_completed"] += 1

        recommended = str(transcript.get("recommended") or "")
        ranking = transcript.get("ranking") or []
        ranks = transcript.get("ranks") if isinstance(transcript.get("ranks"), dict) else {}
        top1 = str(ranking[0]) if ranking else ""
        hit = bool(recommended and (
            ranks.get(recommended) == 1 if ranks else recommended == top1
        ))
        if hit:
            for target in (summary, row):
                target["top1_hit"] += 1

        decision = database.latest_decision(str(run["id"]))
        if not decision:
            continue
        kind = str(decision.get("decision") or "")
        for target in (summary, row):
            target["n_decided"] += 1
            if kind in target:
                target[kind] += 1
        if (
            kind in ("adopted", "partial")
            and recommended
            and recommended in str(decision.get("adopted_ref") or "").split(",")
        ):
            for target in (summary, row):
                target["recommend_adopted"] += 1
    return {"mode": mode, "summary": summary, "rows": list(rows.values())}


@router.get("/profiles")
def profiles(mode: str = Query(default="review", pattern="^(review|debate)$")) -> dict[str, Any]:
    configs = {int(item["id"]): item for item in database.list_models()}
    profiles_by_key: dict[str, dict[str, Any]] = {}
    for run in database.list_runs(200):
        if str(run.get("mode") or "debate") != mode or run.get("status") != "done":
            continue
        transcript = _read_transcript(run) or {}
        participants = transcript.get("participants") or []
        answers = {
            str(item.get("agent") or ""): item
            for item in transcript.get("answers") or []
            if isinstance(item, dict)
        }
        labels = {
            str(item.get("agent") or ""): str(item.get("label") or "")
            for item in transcript.get("labels") or []
            if isinstance(item, dict)
        }
        scores = transcript.get("scores") if isinstance(transcript.get("scores"), dict) else {}
        speeches_by_agent: dict[str, list[dict[str, Any]]] = {}
        for round_record in transcript.get("rounds") or []:
            for speech in round_record.get("speeches") or []:
                summary = speeches_by_agent.setdefault(str(speech.get("agent") or ""), [])
                summary.append(speech)
        winner = str(
            transcript.get("recommended_agent")
            or transcript.get("winner")
            or run.get("winner")
            or ""
        )

        for participant in participants:
            if not isinstance(participant, dict):
                continue
            name = str(participant.get("name") or "")
            config_id = int(participant.get("config_id") or 0)
            model = str(participant.get("model") or participant.get("label") or "")
            key = f"id:{config_id}" if config_id else f"model:{model.strip().lower()}"
            if key not in profiles_by_key:
                config = configs.get(config_id) or {}
                profiles_by_key[key] = {
                    "identity_key": key,
                    "config_id": config_id or None,
                    "name": str(config.get("name") or name or model or "未知模型"),
                    "model": str(config.get("model") or model),
                    "appearances": 0,
                    "valid": 0,
                    "wins": 0,
                    "score_total": 0.0,
                    "score_n": 0,
                }
            profile = profiles_by_key[key]
            profile["appearances"] += 1
            if mode == "review":
                answer = answers.get(name) or {}
                valid = bool(answer.get("text")) and not answer.get("error") and not answer.get("cancelled")
                label = labels.get(name) or ""
                dims = scores.get(label) if isinstance(scores.get(label), dict) else {}
            else:
                own = speeches_by_agent.get(name, [])
                valid = any(
                    item.get("text") and not item.get("error") and not item.get("cancelled")
                    for item in own
                )
                dims = {}
                for round_record in transcript.get("rounds") or []:
                    row = (round_record.get("scores") or {}).get(name)
                    if isinstance(row, dict):
                        dims = row
                        break
            if valid:
                profile["valid"] += 1
                if winner == name:
                    profile["wins"] += 1
            if dims:
                profile["score_total"] += sum(float(value) for value in dims.values())
                profile["score_n"] += len(dims)

    model_counts: dict[str, int] = {}
    for profile in profiles_by_key.values():
        model_key = str(profile.get("model") or "").strip().lower()
        model_counts[model_key] = model_counts.get(model_key, 0) + 1
    rows = []
    for profile in profiles_by_key.values():
        model_key = str(profile.get("model") or "").strip().lower()
        profile["suspected_same_model"] = model_counts.get(model_key, 0) > 1
        profile["avg_score"] = (
            round(profile.pop("score_total") / profile["score_n"], 1)
            if profile["score_n"] else None
        )
        profile.pop("score_n", None)
        rows.append(profile)
    rows.sort(key=lambda item: (-item["wins"], -item["valid"], item["name"]))
    return {"mode": mode, "rows": rows}
