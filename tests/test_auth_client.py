"""The HTTP authentication boundary fails closed on bad upstream contracts."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from mlops_pipeline.src.deployment.service_clients.authentication import AuthClient
from mlops_pipeline.src.deployment.service_clients.contracts import (
    AuthRole,
    AuthenticationError,
    AuthServiceUnavailable,
    SERVICE_TOKEN_HEADER,
)


def run_client(handler, exercise):
    async def run():
        client = AuthClient(
            "https://auth.example.test/", "internal-token",
            transport=httpx.MockTransport(handler),
        )
        try:
            return await exercise(client)
        finally:
            await client.close()

    return asyncio.run(run())


def test_auth_client_happy_path_and_service_headers():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/health/ready":
            return httpx.Response(200)
        if request.url.path == "/v1/auth/login":
            return httpx.Response(200, json={"access_token": "jwt"})
        if request.url.path == "/v1/auth/introspect":
            return httpx.Response(200, json={
                "user_id": "user-1", "username": "analyst", "role": "owner",
                "token_version": 2, "expires_at": "2026-09-13T12:00:00+00:00",
            })
        return httpx.Response(200, json={"keys": []})

    async def exercise(client):
        assert await client.ready()
        assert (await client.login("analyst", "password"))["access_token"] == "jwt"
        principal = await client.authenticate("jwt")
        assert principal.user_id == "user-1"
        assert principal.role == AuthRole.OWNER
        assert principal.token_version == 2
        assert await client.jwks() == {"keys": []}

    run_client(handler, exercise)
    introspection = next(request for request in seen if request.url.path.endswith("introspect"))
    assert introspection.headers["Authorization"] == "Bearer jwt"
    assert introspection.headers[SERVICE_TOKEN_HEADER] == "internal-token"


@pytest.mark.parametrize(
    "method,path,status,payload,error_type",
    [
        ("login", "/v1/auth/login", 401, {}, AuthenticationError),
        ("login", "/v1/auth/login", 500, {}, AuthServiceUnavailable),
        ("login", "/v1/auth/login", 200, {}, AuthServiceUnavailable),
        ("authenticate", "/v1/auth/introspect", 403, {}, AuthenticationError),
        ("authenticate", "/v1/auth/introspect", 502, {}, AuthServiceUnavailable),
        ("authenticate", "/v1/auth/introspect", 200, {"role": "invalid"}, AuthServiceUnavailable),
        ("jwks", "/.well-known/jwks.json", 503, {}, AuthServiceUnavailable),
        ("jwks", "/.well-known/jwks.json", 200, {}, AuthServiceUnavailable),
    ],
)
def test_auth_client_rejects_bad_responses(method, path, status, payload, error_type):
    def handler(request):
        assert request.url.path == path
        return httpx.Response(status, json=payload)

    async def exercise(client):
        with pytest.raises(error_type):
            if method == "login":
                await client.login("analyst", "password")
            elif method == "authenticate":
                await client.authenticate("jwt")
            else:
                await client.jwks()

    run_client(handler, exercise)


@pytest.mark.parametrize("method", ["ready", "login", "authenticate", "jwks"])
def test_auth_client_handles_transport_failure(method):
    def handler(request):
        raise httpx.ConnectError("unreachable", request=request)

    async def exercise(client):
        if method == "ready":
            assert not await client.ready()
        else:
            with pytest.raises(AuthServiceUnavailable):
                if method == "login":
                    await client.login("analyst", "password")
                elif method == "authenticate":
                    await client.authenticate("jwt")
                else:
                    await client.jwks()

    run_client(handler, exercise)
