"""Authentication-service health endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict:
    return {"status": "alive", "service": "authentication"}


@router.get("/ready")
def ready(request: Request):
    engine = getattr(request.app.state, "engine", None)
    service = getattr(request.app.state, "auth_service", None)
    if engine is None or service is None:
        return JSONResponse({"status": "not_ready"}, status_code=503)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            {"status": "not_ready", "dependencies": {"database": "unavailable"}},
            status_code=503,
        )
    return {
        "status": "ready",
        "service": "authentication",
        "dependencies": {"database": "ready"},
    }
