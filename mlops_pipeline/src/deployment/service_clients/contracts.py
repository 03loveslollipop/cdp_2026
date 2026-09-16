"""Shared authentication values with no HTTP-client dependency."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


TOKEN_COOKIE_NAME = "cdp_access_token"
TOKEN_TTL_SECONDS = 2 * 60 * 60
SERVICE_TOKEN_HEADER = "X-CDP-Service-Token"


class AuthRole(StrEnum):
    INFERENCE = "inference"
    OWNER = "owner"


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    role: AuthRole
    token_version: int
    expires_at: datetime


class AuthenticationError(ValueError):
    """The presented user credentials or bearer token are invalid."""


class AuthServiceUnavailable(RuntimeError):
    """The authentication service could not complete a request."""
