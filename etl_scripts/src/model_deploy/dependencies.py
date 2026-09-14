"""Runtime state and FastAPI dependencies."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..service_clients.authentication import AuthClient
from .models import LoadedArtifact
from .settings import Settings


@dataclass(frozen=True)
class Runtime:
    settings: Settings
    artifact: LoadedArtifact
    engine: Engine
    session_factory: sessionmaker[Session]
    model_version_id: str
    auth_client: AuthClient | None


def get_runtime(request: Request) -> Runtime:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application is not ready",
        )
    return runtime
