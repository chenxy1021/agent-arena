"""业务服务层：比赛生命周期与后台线程。"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from config import settings

from . import database
from .events import RecordingSink
from .moderator import Arena, ArenaConfig
from .providers import ApiModelAgent
from .schemas import StartRun


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
        self.cancel_event = threading.Event()

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

    def get(self, run_id: str) -> RunState | None:
        with self.lock:
            return self.runs.get(run_id)

    def active(self) -> RunState | None:
        with self.lock:
            return next((run for run in self.runs.values() if run.status == "running"), None)

    def cancel(self, run_id: str) -> bool:
        """请求中止一场比赛；实际停止由赛制层在下一个检查点完成。"""
        with self.lock:
            run = self.runs.get(run_id)
            if not run or run.status != "running":
                return False
            run.cancel_event.set()
            return True

    def start(self, payload: StartRun) -> RunState:
        proposition = payload.proposition.strip()
        if not proposition:
            raise ValueError("命题不能为空")

        agents: list[ApiModelAgent] = []
        seen: set[int] = set()
        for model_id in payload.model_ids:
            if model_id in seen:
                continue
            seen.add(model_id)
            config = database.get_model(model_id)
            if not config:
                raise ValueError(f"模型配置 #{model_id} 不存在")
            agents.append(
                ApiModelAgent(
                    config_id=model_id,
                    name=str(config["name"]),
                    base_url=str(config["base_url"]),
                    api_key=str(config["api_key"]),
                    model=str(config["model"]),
                    system_prompt=str(config.get("system_prompt") or ""),
                    temperature=config.get("temperature"),
                    persona=str(config.get("persona") or ""),
                )
            )
        if len(agents) < 2:
            raise ValueError("至少需要选择 2 个参赛大模型")

        run_id = uuid.uuid4().hex[:12]
        run = RunState(run_id, proposition)
        arena_holder: dict[str, Arena] = {}
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
            max_rounds=0,
            timeout=payload.timeout,
            out_dir=settings.RUNS_DIR,
            vote_mode=payload.vote_mode,
            speech_mode=payload.speech_mode,
            criteria=list(payload.criteria or []),
            background=payload.background,
            constraints=list(payload.constraints or []),
            max_calls=payload.max_calls,
            max_wall_clock=float(payload.max_wall_clock or 0),
        )

        def worker() -> None:
            try:
                arena = Arena(agents, cfg, sink=run.sink)
                arena_holder["arena"] = arena
                arena.cancel_hook = run.cancel_event
                run.run_dir = str(arena.run_dir)
                database.update_run_dir(run_id, run.run_dir)
                result = arena.run()
                run.result = result.to_dict()
                run.status = "cancelled" if result.stop_reason == "用户中止" else "done"
                database.finish_run(
                    run_id=run_id,
                    status=run.status,
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
