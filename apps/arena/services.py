"""业务服务层：比赛生命周期、agent 发现缓存与后台线程。"""

from __future__ import annotations

import copy
import threading
import time
import uuid
from typing import Any

from config import settings

from . import database
from .adapters import CliAgent, discover, make_custom_agent, unavailable_agents
from .events import RecordingSink
from .mock import MockAgent
from .moderator import Arena, ArenaConfig
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
            out_dir=settings.RUNS_DIR,
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
