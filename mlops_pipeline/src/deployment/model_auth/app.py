"""FastAPI authentication microservice."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..database.connectors.postgres import (
    create_database_engine,
    create_session_factory,
)
from .api import auth, health
from .services import AuthService
from .settings import AuthSettings


def create_app(settings: AuthSettings | None = None) -> FastAPI:
    configured = settings or AuthSettings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configured.validate()
        engine = create_database_engine()
        factory = create_session_factory(engine)
        application.state.engine = engine
        application.state.auth_service = AuthService(configured, factory)
        try:
            yield
        finally:
            application.state.auth_service = None
            application.state.engine = None
            engine.dispose()

    application = FastAPI(
        title="CDP 2026 authentication service",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.settings = configured
    application.state.engine = None
    application.state.auth_service = None
    if configured.allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(configured.allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )
    application.include_router(auth.router)
    application.include_router(auth.discovery_router)
    application.include_router(health.router)
    return application


app = create_app()
