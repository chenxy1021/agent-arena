"""Shared result type returned by model adapters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CallResult:
    text: str = ""
    elapsed: float = 0.0
    error: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    cancelled: bool = False
