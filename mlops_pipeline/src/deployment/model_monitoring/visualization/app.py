"""Independent FastAPI and Dash monitoring visualization service."""

from __future__ import annotations

from contextlib import asynccontextmanager

from a2wsgi import WSGIMiddleware
from fastapi import FastAPI
from sqlalchemy import text

from ...database.connectors.postgres import (
    create_database_engine,
    create_session_factory,
)
from ...database.repositories import ModelRepository
from ...service_clients.authentication import AuthClient
from ..dashboard import create_dashboard
from .api import auth, health, outcomes
from .frontend.routes import router as frontend_router
from .runtime import VisualizationRuntime
from .security import OwnerAuthMiddleware
from .settings import VisualizationSettings


def create_app(settings: VisualizationSettings | None = None) -> FastAPI:
    configured = settings or VisualizationSettings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configured.validate()
        engine = create_database_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        factory = create_session_factory(engine)
        with factory() as session:
            active_model = ModelRepository(session).active()
        if active_model is None:
            engine.dispose()
            raise RuntimeError("No active model version is registered")
        auth_client = AuthClient(
            configured.auth_service_url or "",
            configured.internal_service_token or "",
        )
        application.state.runtime = VisualizationRuntime(
            settings=configured,
            engine=engine,
            session_factory=factory,
            auth_client=auth_client,
        )
        try:
            yield
        finally:
            application.state.runtime = None
            await auth_client.close()
            engine.dispose()

    application = FastAPI(
        title="CDP 2026 monitoring visualization service",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.settings = configured
    application.state.runtime = None
    application.add_middleware(OwnerAuthMiddleware)
    application.include_router(auth.router)
    application.include_router(auth.discovery_router)
    application.include_router(health.router)
    application.include_router(outcomes.router)
    application.include_router(frontend_router)
    dashboard = create_dashboard(
        lambda: getattr(application.state, "runtime", None),
        inference_service_url=configured.inference_service_url or "/",
    )
    application.mount("/monitor", WSGIMiddleware(dashboard.server))
    return application


app = create_app()
