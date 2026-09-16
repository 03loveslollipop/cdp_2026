"""Observed-outcome HTTP contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OutcomeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=36)
    actual_label: Literal[0, 1]
    matured_at: datetime

    @field_validator("matured_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("matured_at must include a timezone")
        return value


class OutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcomes: list[OutcomeItem] = Field(min_length=1, max_length=1000)


class OutcomeResponse(BaseModel):
    accepted: int
