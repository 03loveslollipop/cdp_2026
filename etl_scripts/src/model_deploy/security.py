"""JWT authentication and role authorization boundary for HTTP routes."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..service_clients import AuthenticationError, AuthServiceUnavailable
from ..service_clients.contracts import (
    TOKEN_COOKIE_NAME,
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
        runtime = getattr(request.app.state, "runtime", None)
        if runtime is None or runtime.auth_client is None:
            return self._service_unavailable(request)
        try:
            principal = await runtime.auth_client.authenticate(token)
        except AuthenticationError:
            return self._authentication_required(request)
        except AuthServiceUnavailable:
            return self._service_unavailable(request)
        request.state.principal = principal
        return self._secure(await call_next(request), request)

    def _required_role(self, request: Request) -> bool | None:
        path = request.url.path
        if path in self.PUBLIC_PATHS or path.startswith("/static/"):
            return None
        return True

    @staticmethod
    def _bearer_token(request: Request) -> str | None:
        scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not credentials.strip():
            return None
        return credentials.strip()

    def _authentication_required(self, request: Request) -> Response:
        return self._secure(
            JSONResponse(
                {"detail": "Bearer token required"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            ),
            request,
        )

    def _service_unavailable(self, request: Request) -> Response:
        return self._secure(
            JSONResponse(
                {"detail": "Authentication service unavailable"}, status_code=503
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
