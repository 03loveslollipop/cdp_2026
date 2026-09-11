"""FastAPI application factory with the Dash monitor mounted at ``/monitor/``."""

from __future__ import annotations

from contextlib import asynccontextmanager

from a2wsgi import WSGIMiddleware
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text

from ..database.connectors.postgres import create_database_engine, create_session_factory
from ..database.repositories import ModelRepository
from ..model_monitoring.dashboard import create_dashboard
from .api import health, model, outcomes, predictions
from .dependencies import Runtime
from .frontend.routes import router as frontend_router
from .security import BasicAuthMiddleware
from .services.artifact_loader import load_artifact
from .settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configured.validate()
        artifact = load_artifact(configured.artifact_dir)
        engine = create_database_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        factory = create_session_factory(engine)
        with factory.begin() as session:
            model_version = ModelRepository(session).register(
                artifact.manifest, artifact.reference_profiles
            )
        application.state.runtime = Runtime(
            settings=configured,
            artifact=artifact,
            engine=engine,
            session_factory=factory,
            model_version_id=model_version.id,
        )
        try:
            yield
        finally:
            application.state.runtime = None
            engine.dispose()

    application = FastAPI(
        title="CDP 2026 credit prediction API",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.add_middleware(GZipMiddleware, minimum_size=1000)
    application.add_middleware(BasicAuthMiddleware, settings=configured)
    application.include_router(health.router)
    application.include_router(model.router)
    application.include_router(predictions.router)
    application.include_router(outcomes.router)
    application.include_router(frontend_router)
    dashboard = create_dashboard(lambda: getattr(application.state, "runtime", None))
    application.mount("/monitor", WSGIMiddleware(dashboard.server))
    return application


app = create_app()
