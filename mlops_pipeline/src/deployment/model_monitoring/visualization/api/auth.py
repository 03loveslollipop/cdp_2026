"""Same-origin authentication proxy for the monitoring browser."""

from fastapi import APIRouter, HTTPException, Request, Response

from ....model_auth.models import LoginRequest, TokenResponse
from ....service_clients import AuthenticationError, AuthServiceUnavailable
from ....service_clients.contracts import TOKEN_COOKIE_NAME, TOKEN_TTL_SECONDS


router = APIRouter(prefix="/v1/auth", tags=["authentication proxy"])
discovery_router = APIRouter(tags=["authentication proxy"])


def _runtime(request: Request):
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Visualization service is not ready")
    return runtime


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    try:
        grant = await _runtime(request).auth_client.login(
            payload.username, payload.password
        )
    except AuthenticationError as error:
        raise HTTPException(
            status_code=401, detail="Invalid username or password"
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
        secure=_runtime(request).settings.environment != "development",
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
        secure=_runtime(request).settings.environment != "development",
        httponly=True,
        samesite="strict",
    )
    return response


@discovery_router.get("/.well-known/jwks.json")
async def jwks(request: Request) -> dict:
    try:
        return await _runtime(request).auth_client.jwks()
    except AuthServiceUnavailable as error:
        raise HTTPException(
            status_code=503, detail="Authentication service unavailable"
        ) from error
