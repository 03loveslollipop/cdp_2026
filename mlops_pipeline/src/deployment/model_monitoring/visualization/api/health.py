"""Monitoring visualization health endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict:
    return {"status": "alive", "service": "monitoring-visualization"}


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
    if not await runtime.auth_client.ready():
        return JSONResponse(
            {
                "status": "not_ready",
                "dependencies": {
                    "database": "ready",
                    "authentication": "unavailable",
                },
            },
            status_code=503,
        )
    return {
        "status": "ready",
        "service": "monitoring-visualization",
        "dependencies": {"database": "ready", "authentication": "ready"},
    }
