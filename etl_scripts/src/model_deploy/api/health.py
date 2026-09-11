"""Liveness and dependency readiness endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict:
    return {"status": "alive"}


@router.get("/ready")
def ready(request: Request):
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        return JSONResponse({"status": "not_ready"}, status_code=503)
    try:
        with runtime.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            {"status": "not_ready", "dependencies": {"database": "unavailable"}},
            status_code=503,
        )
    return {
        "status": "ready",
        "dependencies": {"database": "ready", "model": "ready"},
        "model_family": runtime.artifact.model_family,
        "artifact_sha256": runtime.artifact.artifact_sha256,
    }
