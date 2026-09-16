"""Service entrypoints bind locally unless their container opts into public traffic."""

from __future__ import annotations

import importlib

import pytest
import uvicorn


@pytest.mark.parametrize(
    "module_name,arguments",
    [
        ("mlops_pipeline.src.deployment.model_auth.__main__", None),
        ("mlops_pipeline.src.deployment.model_deploy.__main__", ["serve"]),
        ("mlops_pipeline.src.deployment.model_monitoring.visualization.__main__", None),
    ],
)
@pytest.mark.parametrize("configured_host", [None, "0.0.0.0"])
def test_service_bind_host(monkeypatch, module_name, arguments, configured_host):
    if configured_host is None:
        monkeypatch.delenv("CDP_BIND_HOST", raising=False)
    else:
        monkeypatch.setenv("CDP_BIND_HOST", configured_host)
    monkeypatch.setenv("PORT", "8765")
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))

    module = importlib.import_module(module_name)
    if arguments is None:
        module.main()
    else:
        module.main(arguments)

    assert len(calls) == 1
    assert calls[0]["host"] == (configured_host or "127.0.0.1")
    assert calls[0]["port"] == 8765
