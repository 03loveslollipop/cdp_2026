"""Authentication-service HTTP contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class IntrospectionResponse(BaseModel):
    user_id: str
    username: str
    role: Literal["inference", "owner"]
    token_version: int
    expires_at: datetime
