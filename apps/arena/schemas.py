"""Agent Arena 的请求模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ModelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(default="", max_length=8000)
    temperature: float | None = Field(default=None, ge=0, le=2)


class ModelUpdate(ModelCreate):
    api_key: str = Field(default="", max_length=500)


class ModelNameRequest(BaseModel):
    model_id: int | None = None
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=500)
    model: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(default="", max_length=8000)
    temperature: float | None = Field(default=None, ge=0, le=2)


class StartRun(BaseModel):
    proposition: str = Field(min_length=1, max_length=2000)
    vote_mode: Literal["eliminate", "support"] = "eliminate"
    model_ids: list[int] = Field(min_length=2, max_length=16)
    timeout: float = Field(default=240, ge=5, le=1200)
