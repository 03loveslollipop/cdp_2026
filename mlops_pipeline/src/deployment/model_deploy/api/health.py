"""Liveness and dependency readiness endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict:
    return {"status": "alive"}


@router.get("/ready")
async def ready(request: Request):
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
    if not runtime.settings.auth_disabled:
        if runtime.auth_client is None or not await runtime.auth_client.ready():
            return JSONResponse(
                {
                    "status": "not_ready",
                    "dependencies": {
                        "database": "ready",
                        "model": "ready",
                        "authentication": "unavailable",
                    },
                },
                status_code=503,
            )
    return {
        "status": "ready",
        "service": "inference",
        "dependencies": {
            "database": "ready",
            "model": "ready",
            "authentication": "disabled"
            if runtime.settings.auth_disabled
            else "ready",
        },
        "model_family": runtime.artifact.model_family,
        "artifact_sha256": runtime.artifact.artifact_sha256,
    }
