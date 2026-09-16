"""Owner-only authentication boundary for monitoring HTTP routes."""

from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from ...service_clients import (
    AuthRole,
    AuthenticationError,
    AuthServiceUnavailable,
)
from ...service_clients.contracts import TOKEN_COOKIE_NAME


class OwnerAuthMiddleware(BaseHTTPMiddleware):
    PUBLIC_PATHS = {
        "/",
        "/health/live",
        "/health/ready",
        "/v1/auth/login",
        "/v1/auth/logout",
        "/.well-known/jwks.json",
    }

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.PUBLIC_PATHS:
            return self._secure(await call_next(request), request)
        runtime = getattr(request.app.state, "runtime", None)
        if runtime is None:
            return self._unavailable(request)
        token = self._bearer(request)
        if token is None and not request.url.path.startswith("/v1/"):
            token = request.cookies.get(TOKEN_COOKIE_NAME)
        if token is None:
            return self._authentication_required(request)
        try:
            principal = await runtime.auth_client.authenticate(token)
        except AuthenticationError:
            return self._authentication_required(request)
        except AuthServiceUnavailable:
            return self._unavailable(request)
        if principal.role is not AuthRole.OWNER:
            return self._secure(
                JSONResponse({"detail": "Owner role required"}, status_code=403),
                request,
            )
        request.state.principal = principal
        return self._secure(await call_next(request), request)

    @staticmethod
    def _bearer(request: Request) -> str | None:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return None
        return token.strip()

    def _authentication_required(self, request: Request) -> Response:
        if request.url.path.startswith("/monitor") and "text/html" in request.headers.get(
            "accept", ""
        ):
            destination = quote(request.url.path, safe="/")
            return self._secure(
                RedirectResponse(f"/?next={destination}", status_code=303), request
            )
        return self._secure(
            JSONResponse(
                {"detail": "Bearer token required"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            ),
            request,
        )

    def _unavailable(self, request: Request) -> Response:
        return self._secure(
            JSONResponse(
                {"detail": "Authentication service unavailable"}, status_code=503
            ),
            request,
        )

    @staticmethod
    def _secure(response: Response, request: Request) -> Response:
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
