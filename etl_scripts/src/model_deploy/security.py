"""Small HTTP Basic boundary for the demo API and dashboard."""

from __future__ import annotations

import base64
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .settings import Settings


class BasicAuthMiddleware(BaseHTTPMiddleware):
    PUBLIC_PATHS = {"/health/live", "/health/ready"}

    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next):
        if self.settings.auth_disabled or request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)
        header = request.headers.get("authorization", "")
        valid = False
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
                username, password = decoded.split(":", 1)
                username_valid = secrets.compare_digest(
                    username, self.settings.auth_username or ""
                )
                password_valid = secrets.compare_digest(
                    password, self.settings.auth_password or ""
                )
                valid = username_valid and password_valid
            except (ValueError, UnicodeDecodeError):
                valid = False
        if not valid:
            return JSONResponse(
                {"detail": "Authentication required"},
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="cdp-2026"'},
            )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response
