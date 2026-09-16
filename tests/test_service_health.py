"""Readiness fails closed when a database, model, or auth dependency is absent."""

from __future__ import annotations

import asyncio
import json
from contextlib import nullcontext
from types import SimpleNamespace

from fastapi.responses import JSONResponse

from mlops_pipeline.src.deployment.model_auth.api import health as auth_health
from mlops_pipeline.src.deployment.model_deploy.api import health as inference_health
from mlops_pipeline.src.deployment.model_monitoring.visualization.api import health as monitor_health


def request(**state):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(**state)))


def engine(*, available=True):
    class Connection:
        def execute(self, statement):
            if not available:
                raise RuntimeError("database unavailable")

    return SimpleNamespace(connect=lambda: nullcontext(Connection()))


class AuthClient:
    def __init__(self, available=True):
        self.available = available

    async def ready(self):
        return self.available


def status(response):
    if isinstance(response, JSONResponse):
        return response.status_code, json.loads(response.body)
    return 200, response


def test_auth_health_requires_service_and_database():
    assert auth_health.live()["status"] == "alive"
    assert status(auth_health.ready(request()))[0] == 503
    assert status(auth_health.ready(request(engine=engine(available=False), auth_service=object())))[0] == 503
    code, payload = status(auth_health.ready(request(engine=engine(), auth_service=object())))
    assert code == 200
    assert payload["dependencies"]["database"] == "ready"


def test_inference_health_requires_runtime_database_and_remote_auth():
    assert inference_health.live()["status"] == "alive"
    assert status(asyncio.run(inference_health.ready(request())))[0] == 503
    runtime = SimpleNamespace(
        engine=engine(available=False),
        settings=SimpleNamespace(auth_disabled=False),
        auth_client=AuthClient(),
        artifact=SimpleNamespace(model_family="xgboost", artifact_sha256="abc"),
    )
    assert status(asyncio.run(inference_health.ready(request(runtime=runtime))))[1][
        "dependencies"
    ]["database"] == "unavailable"
    runtime.engine = engine()
    runtime.auth_client = AuthClient(available=False)
    assert status(asyncio.run(inference_health.ready(request(runtime=runtime))))[1][
        "dependencies"
    ]["authentication"] == "unavailable"
    runtime.auth_client = AuthClient()
    code, payload = status(asyncio.run(inference_health.ready(request(runtime=runtime))))
    assert code == 200
    assert payload["model_family"] == "xgboost"
    runtime.settings.auth_disabled = True
    runtime.auth_client = None
    assert status(asyncio.run(inference_health.ready(request(runtime=runtime))))[1][
        "dependencies"
    ]["authentication"] == "disabled"


def test_monitoring_visualization_health_requires_database_and_auth():
    assert monitor_health.live()["status"] == "alive"
    assert status(asyncio.run(monitor_health.ready(request())))[0] == 503
    runtime = SimpleNamespace(engine=engine(available=False), auth_client=AuthClient())
    assert status(asyncio.run(monitor_health.ready(request(runtime=runtime))))[1][
        "dependencies"
    ]["database"] == "unavailable"
    runtime.engine = engine()
    runtime.auth_client = AuthClient(available=False)
    assert status(asyncio.run(monitor_health.ready(request(runtime=runtime))))[1][
        "dependencies"
    ]["authentication"] == "unavailable"
    runtime.auth_client = AuthClient()
    code, payload = status(asyncio.run(monitor_health.ready(request(runtime=runtime))))
    assert code == 200
    assert payload["service"] == "monitoring-visualization"
