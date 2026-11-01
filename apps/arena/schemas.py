"""Agent Arena 的请求模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
