"""JWT authentication and role authorization boundary for HTTP routes."""

from __future__ import annotations

from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from .services.auth_service import (
    AuthRole,
    AuthenticationError,
    TOKEN_COOKIE_NAME,
    get_auth_service,
)
from .settings import Settings


class TokenAuthMiddleware(BaseHTTPMiddleware):
    PUBLIC_PATHS = {
        "/health/live",
        "/health/ready",
        "/v1/auth/login",
        "/.well-known/jwks.json",
        "/",
        "/inference",
        "/inference/",
    }

    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next):
        required_role = self._required_role(request)
        if self.settings.auth_disabled or required_role is None:
            return self._secure(await call_next(request), request)

        token = self._bearer_token(request)
        if token is None and not request.url.path.startswith("/v1/"):
            token = request.cookies.get(TOKEN_COOKIE_NAME)
        if token is None:
            return self._authentication_required(request)
        try:
            principal = get_auth_service(request.app, self.settings).authenticate_token(
                token
            )
        except (AuthenticationError, RuntimeError):
            return self._authentication_required(request)
        if required_role is AuthRole.OWNER and principal.role is not AuthRole.OWNER:
            return self._secure(
                JSONResponse({"detail": "Owner role required"}, status_code=403),
                request,
            )
        request.state.principal = principal
        return self._secure(await call_next(request), request)

    def _required_role(self, request: Request) -> AuthRole | None:
        path = request.url.path
        if path in self.PUBLIC_PATHS or path.startswith("/static/"):
            return None
        if path.startswith("/monitor") or path.startswith("/v1/outcomes"):
            return AuthRole.OWNER
        return AuthRole.INFERENCE

    @staticmethod
    def _bearer_token(request: Request) -> str | None:
        scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not credentials.strip():
            return None
        return credentials.strip()

    def _authentication_required(self, request: Request) -> Response:
        if request.url.path.startswith(
            "/monitor"
        ) and "text/html" in request.headers.get("accept", ""):
            destination = quote(request.url.path, safe="/")
            return self._secure(
                RedirectResponse(f"/inference/?next={destination}", status_code=303),
                request,
            )
        return self._secure(
            JSONResponse(
                {"detail": "Bearer token required"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            ),
            request,
        )

    @staticmethod
    def _secure(response: Response, request: Request) -> Response:
        if not request.url.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
