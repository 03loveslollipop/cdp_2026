"""Same-origin proxy for the independent authentication service."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from ...service_clients.contracts import (
    AuthenticationError,
    AuthServiceUnavailable,
    TOKEN_COOKIE_NAME,
    TOKEN_TTL_SECONDS,
)
from ..models import LoginRequest, TokenResponse


router = APIRouter(prefix="/v1/auth", tags=["authentication proxy"])
discovery_router = APIRouter(tags=["authentication proxy"])


def _client(request: Request):
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None or runtime.auth_client is None:
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    return runtime.auth_client


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    try:
        grant = await _client(request).login(payload.username, payload.password)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except AuthServiceUnavailable as error:
        raise HTTPException(
            status_code=503, detail="Authentication service unavailable"
        ) from error
    response.set_cookie(
        TOKEN_COOKIE_NAME,
        grant["access_token"],
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        secure=request.app.state.settings.environment != "development",
        samesite="strict",
        path="/",
    )
    return grant


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    response = Response(status_code=204)
    response.delete_cookie(
        TOKEN_COOKIE_NAME,
        path="/",
        secure=request.app.state.settings.environment != "development",
        httponly=True,
        samesite="strict",
    )
    return response


@discovery_router.get("/.well-known/jwks.json")
async def jwks(request: Request) -> dict:
    try:
        return await _client(request).jwks()
    except AuthServiceUnavailable as error:
        raise HTTPException(
            status_code=503, detail="Authentication service unavailable"
        ) from error
