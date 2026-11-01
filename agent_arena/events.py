"""事件总线：赛制层只负责"发生了什么"，终端和网页各自决定怎么呈现。

这样可以同时接终端 UI、Web SSE 推送、日志落盘，而不用改赛制代码。
"""

from __future__ import annotations

import threading
from typing import Any


class EventSink:
    """赛制事件的接收端。所有方法都是可选实现。"""

    def emit(self, kind: str, **data: Any) -> None:  # pragma: no cover - 接口
        raise NotImplementedError


class NullSink(EventSink):
    def emit(self, kind: str, **data: Any) -> None:
        return None


class MultiSink(EventSink):
    """把事件扇出给多个接收端（例如：终端 + Web + 文件）。"""

    def __init__(self, *sinks: EventSink):
        self.sinks = [s for s in sinks if s is not None]

    def emit(self, kind: str, **data: Any) -> None:
        for sink in self.sinks:
            try:
                sink.emit(kind, **data)
            except Exception:
                # 单个接收端出错不能拖垮比赛
                continue


class RecordingSink(EventSink):
    """把事件按顺序存起来，供 SSE 增量拉取。"""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def emit(self, kind: str, **data: Any) -> None:
        with self._lock:
            self.events.append({"kind": kind, **data})

    def since(self, index: int) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.events[index:])

    def count(self) -> int:
        with self._lock:
            return len(self.events)
