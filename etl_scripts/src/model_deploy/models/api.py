"""Pydantic HTTP contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: Literal[7200] = 7200
    expires_at: datetime
    role: Literal["inference", "owner"]


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[dict[str, Any]] = Field(min_length=1)


class PredictionItem(BaseModel):
    event_id: str
    row_number: int
    external_reference: str | None
    predicted_label: Literal[0, 1]
    default_probability: float
    on_time_probability: float


class PredictionResponse(BaseModel):
    batch_id: str
    idempotent_replay: bool
    model_version_id: str
    model_family: str
    class_order: list[int]
    items: list[PredictionItem]


class PredictorField(BaseModel):
    name: str
    data_type: Literal["numeric", "categorical"]
    suggested_values: list[str] = Field(default_factory=list)


class ModelResponse(BaseModel):
    model_version_id: str
    model_family: str
    artifact_sha256: str
    threshold: float
    class_order: list[int]
    stage: str
    source_revision: str | None
    required_predictors: list[str]
    predictor_fields: list[PredictorField]


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
