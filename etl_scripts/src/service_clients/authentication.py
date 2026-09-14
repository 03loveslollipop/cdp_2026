"""HTTP contract for authentication service consumers."""

from __future__ import annotations

from datetime import datetime

import httpx

from .contracts import (
    AuthRole,
    AuthenticationError,
    AuthServiceUnavailable,
    Principal,
    SERVICE_TOKEN_HEADER,
)


class AuthClient:
    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(10.0, connect=5.0),
            transport=transport,
        )
        self.service_token = service_token

    async def close(self) -> None:
        await self.client.aclose()

    async def ready(self) -> bool:
        try:
            response = await self.client.get("/health/ready")
            return response.status_code == 200
        except httpx.RequestError:
            return False

    async def login(self, username: str, password: str) -> dict:
        try:
            response = await self.client.post(
                "/v1/auth/login",
                json={"username": username, "password": password},
            )
        except httpx.RequestError as error:
            raise AuthServiceUnavailable("Authentication service unavailable") from error
        if response.status_code == 401:
            raise AuthenticationError("Invalid username or password")
        if response.status_code != 200:
            raise AuthServiceUnavailable("Authentication service unavailable")
        try:
            payload = response.json()
            if not isinstance(payload.get("access_token"), str):
                raise ValueError("access token missing")
            return payload
        except (AttributeError, TypeError, ValueError) as error:
            raise AuthServiceUnavailable(
                "Authentication service returned an invalid contract"
            ) from error

    async def authenticate(self, token: str) -> Principal:
        try:
            response = await self.client.post(
                "/v1/auth/introspect",
                headers={
                    "Authorization": f"Bearer {token}",
                    SERVICE_TOKEN_HEADER: self.service_token,
                },
            )
        except httpx.RequestError as error:
            raise AuthServiceUnavailable("Authentication service unavailable") from error
        if response.status_code in {401, 403}:
            raise AuthenticationError("Invalid or expired access token")
        if response.status_code != 200:
            raise AuthServiceUnavailable("Authentication service unavailable")
        try:
            payload = response.json()
            return Principal(
                user_id=str(payload["user_id"]),
                username=str(payload["username"]),
                role=AuthRole(payload["role"]),
                token_version=int(payload["token_version"]),
                expires_at=datetime.fromisoformat(payload["expires_at"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise AuthServiceUnavailable(
                "Authentication service returned an invalid contract"
            ) from error

    async def jwks(self) -> dict:
        try:
            response = await self.client.get("/.well-known/jwks.json")
        except httpx.RequestError as error:
            raise AuthServiceUnavailable("Authentication service unavailable") from error
        if response.status_code != 200:
            raise AuthServiceUnavailable("Authentication service unavailable")
        try:
            payload = response.json()
            if not isinstance(payload.get("keys"), list):
                raise ValueError("keys missing")
            return payload
        except (AttributeError, TypeError, ValueError) as error:
            raise AuthServiceUnavailable(
                "Authentication service returned an invalid contract"
            ) from error
