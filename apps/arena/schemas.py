"""Agent Arena 的请求模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
    model: str = Field(min_length=1, max_length=200)
    api_key: str = Field(default="", max_length=500)


class StartRun(BaseModel):
    proposition: str = Field(min_length=1, max_length=2000)
    mode: Literal["review", "debate"] = "review"
    vote_mode: Literal["eliminate", "support"] = "eliminate"
    win_condition: str = Field(min_length=1, max_length=1000)
    model_ids: list[int] = Field(min_length=2, max_length=8)
    judge_model_id: int | None = None
    diversify: bool = True
    timeout: float = Field(default=240, ge=5, le=1200)
    speech_mode: Literal["parallel_buffered", "sequential_live"] = "parallel_buffered"
    background: str = Field(default="", max_length=4000)
    constraints: list[str] = Field(default_factory=list, max_length=20)
    criteria: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("win_condition")
    @classmethod
    def win_condition_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("胜出标准不能为空")
        return value


class DecisionCreate(BaseModel):
    decision: Literal["adopted", "partial", "rejected", "undecided"]
    adopted_kind: str | None = None
    adopted_ref: str | None = None
    reason_code: str | None = None
    note: str = Field(default="", max_length=2000)


class SeatRetryRequest(BaseModel):
    agent: str = Field(min_length=1, max_length=120)
