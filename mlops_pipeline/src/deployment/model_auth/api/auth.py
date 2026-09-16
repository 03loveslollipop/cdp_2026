"""Login, introspection, logout, and public verification-key endpoints."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Header, HTTPException, Request, Response

from ...service_clients.contracts import (
    AuthenticationError,
    SERVICE_TOKEN_HEADER,
    TOKEN_COOKIE_NAME,
    TOKEN_TTL_SECONDS,
)
from ..models import IntrospectionResponse, LoginRequest, TokenResponse


router = APIRouter(prefix="/v1/auth", tags=["authentication"])
discovery_router = APIRouter(tags=["authentication"])


def _service(request: Request):
    service = getattr(request.app.state, "auth_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Authentication service is not ready")
    return service


def _bearer(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    try:
        grant = _service(request).login(payload.username, payload.password)
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
        secure=request.app.state.settings.environment != "development",
        samesite="strict",
        path="/",
    )
    return {
        "access_token": grant.token,
        "expires_at": grant.principal.expires_at,
        "role": grant.principal.role.value,
    }


@router.post("/introspect", response_model=IntrospectionResponse)
def introspect(
    request: Request,
    service_token: str = Header(alias=SERVICE_TOKEN_HEADER),
) -> dict:
    expected = request.app.state.settings.internal_service_token or ""
    if not secrets.compare_digest(service_token, expected):
        raise HTTPException(status_code=403, detail="Invalid service credential")
    try:
        principal = _service(request).authenticate_token(_bearer(request))
    except AuthenticationError as error:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    return {
        "user_id": principal.user_id,
        "username": principal.username,
        "role": principal.role.value,
        "token_version": principal.token_version,
        "expires_at": principal.expires_at,
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
    return _service(request).jwks()
