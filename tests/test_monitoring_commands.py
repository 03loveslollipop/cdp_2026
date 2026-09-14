"""Scheduler CLI dispatches catch-up and retention without duplicate schedules."""

from __future__ import annotations

import json

import pytest

from etl_scripts.src.model_monitoring import __main__ as commands
from etl_scripts.src.model_monitoring.settings import MonitoringSettings


@pytest.mark.parametrize(
    "arguments,expected_windows,expected_retention",
    [
        (["compute"], 1, False),
        (["compute", "--catch-up"], 2, False),
        (["compute", "--catch-up", "--include-retention"], 2, True),
        (["retention"], 0, True),
    ],
)
def test_monitoring_command_dispatch(
    monkeypatch, capsys, arguments, expected_windows, expected_retention
):
    settings = MonitoringSettings(max_catchup_days=2, window_days=3)
    factory = object()
    calls = []
    monkeypatch.setattr(commands.MonitoringSettings, "from_env", lambda: settings)
    monkeypatch.setattr(commands, "create_database_engine", object)
    monkeypatch.setattr(commands, "create_session_factory", lambda engine: factory)

    class Runner:
        def __init__(self, received_factory, received_settings):
            assert (received_factory, received_settings) == (factory, settings)

        def run_catchup(self):
            calls.append("catchup")
            return [{"run_id": "a"}, {"run_id": "b"}]

        def run_window(self, start, end):
            assert (end - start).days == 3
            calls.append("window")
            return {"run_id": "a"}

    monkeypatch.setattr(commands, "MonitoringRunner", Runner)
    monkeypatch.setattr(
        commands, "retain_recent_predictions",
        lambda received_factory, days: calls.append(("retention", days)) or 4,
    )
    commands.main(arguments)
    result = json.loads(capsys.readouterr().out)
    assert len(result.get("windows", [])) == expected_windows
    assert ("deleted_batches" in result) == expected_retention
    if expected_retention:
        assert result["deleted_batches"] == 4
        assert ("retention", settings.retention_days) in calls
