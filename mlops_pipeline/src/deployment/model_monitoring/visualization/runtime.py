"""Monitoring visualization runtime state."""

from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ...service_clients.authentication import AuthClient
from .settings import VisualizationSettings


@dataclass(frozen=True)
class VisualizationRuntime:
    settings: VisualizationSettings
    engine: Engine
    session_factory: sessionmaker[Session]
    auth_client: AuthClient
