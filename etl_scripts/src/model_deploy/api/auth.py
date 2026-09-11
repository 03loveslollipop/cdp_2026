"""Login, logout, and public verification-key endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from ..models import LoginRequest, TokenResponse
from ..services.auth_service import (
    AuthenticationError,
    TOKEN_COOKIE_NAME,
    TOKEN_TTL_SECONDS,
    get_auth_service,
)


router = APIRouter(prefix="/v1/auth", tags=["authentication"])
discovery_router = APIRouter(tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    settings = request.app.state.settings
    try:
        grant = get_auth_service(request.app).login(
            payload.username, payload.password
        )
    except AuthenticationError as error:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    response.set_cookie(
        TOKEN_COOKIE_NAME,
        grant.token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        secure=settings.environment != "development",
        samesite="strict",
        path="/",
    )
    return {
        "access_token": grant.token,
        "expires_at": grant.principal.expires_at,
        "role": grant.principal.role.value,
    }


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
def jwks(request: Request) -> dict:
    return get_auth_service(request.app).jwks()
