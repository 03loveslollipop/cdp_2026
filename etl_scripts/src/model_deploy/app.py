"""FastAPI application factory with the Dash monitor mounted at ``/monitor/``."""

from __future__ import annotations

from contextlib import asynccontextmanager

from a2wsgi import WSGIMiddleware
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from ..database.connectors.postgres import (
    create_database_engine,
    create_session_factory,
)
from ..database.repositories import ModelRepository
from ..model_monitoring.dashboard import create_dashboard
from .api import auth, health, model, outcomes, predictions
from .dependencies import Runtime
from .frontend.routes import FRONTEND_DIRECTORY, router as frontend_router
from .security import TokenAuthMiddleware
from .services.auth_service import get_auth_service
from .services.artifact_loader import load_artifact
from .settings import Settings


def _add_bearer_security_schema(application: FastAPI) -> None:
    def build_openapi() -> dict:
        if application.openapi_schema:
            return application.openapi_schema
        schema = get_openapi(
            title=application.title,
            version=application.version,
            routes=application.routes,
        )
        components = schema.setdefault("components", {})
        components.setdefault("securitySchemes", {})["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
        public_operations = {
            ("/health/live", "get"),
            ("/health/ready", "get"),
            ("/v1/auth/login", "post"),
            ("/.well-known/jwks.json", "get"),
        }
        for path, path_item in schema["paths"].items():
            for method, operation in path_item.items():
                if (path, method) not in public_operations:
                    operation["security"] = [{"BearerAuth": []}]
        application.openapi_schema = schema
        return schema

    application.openapi = build_openapi


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configured.validate()
        if not configured.auth_disabled:
            get_auth_service(application, configured)
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
        version="1.1.0",
        lifespan=lifespan,
    )
    application.state.settings = configured
    application.add_middleware(GZipMiddleware, minimum_size=1000)
    application.add_middleware(TokenAuthMiddleware, settings=configured)
    application.include_router(auth.router)
    application.include_router(auth.discovery_router)
    application.include_router(health.router)
    application.include_router(model.router)
    application.include_router(predictions.router)
    application.include_router(outcomes.router)
    application.include_router(frontend_router)
    _add_bearer_security_schema(application)
    application.mount(
        "/static",
        StaticFiles(directory=str(FRONTEND_DIRECTORY / "static")),
        name="static",
    )
    dashboard = create_dashboard(lambda: getattr(application.state, "runtime", None))
    application.mount("/monitor", WSGIMiddleware(dashboard.server))
    return application


app = create_app()
