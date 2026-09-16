"""Monitoring windows are transactional, replayable, and bounded in catch-up."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from mlops_pipeline.src.deployment.model_monitoring.services import monitoring_runner
from mlops_pipeline.src.deployment.model_monitoring.settings import MonitoringSettings


START = datetime(2026, 9, 10, tzinfo=UTC)
END = START + timedelta(days=1)


def make_runner(monkeypatch, *, active=True, fail_metrics=False):
    state = {"run": None, "completed": [], "failures": [], "restarts": 0}

    class Session:
        def get(self, _model_type, run_id):
            assert run_id == "run-1"
            return state["run"]

    class Factory:
        def begin(self):
            return nullcontext(Session())

    class Models:
        def __init__(self, _session):
            pass

        def active(self):
            return SimpleNamespace(id="model-1") if active else None

        def reference_profiles(self, model_id):
            assert model_id == "model-1"
            return {"amount": {"type": "numeric"}}

    class Runs:
        def __init__(self, _session):
            pass

        def find_run(self, model_id, start, end):
            assert (model_id, start, end) == ("model-1", START, END)
            return state["run"]

        def start_run(self, model_id, start, end):
            state["run"] = SimpleNamespace(id="run-1", status="running")
            return state["run"]

        def restart_run(self, run):
            state["restarts"] += 1
            run.status = "running"

        def prediction_rows(self, model_id, start, end):
            assert model_id == "model-1"
            return [{"id": "prediction-1"}]

        def matured_rows(self, model_id, start, end):
            assert model_id == "model-1"
            return []

        def complete_run(self, run, metrics, status):
            run.status = status
            state["completed"].append(metrics)

        def fail_run(self, run, error):
            run.status = "failed"
            state["failures"].append(str(error))

    def drift(rows, profiles, settings):
        assert rows == [{"id": "prediction-1"}]
        assert "amount" in profiles
        if fail_metrics:
            raise RuntimeError("calculation failed")
        return [SimpleNamespace(as_record=lambda: {"metric_name": "drift"})]

    monkeypatch.setattr(monitoring_runner, "ModelRepository", Models)
    monkeypatch.setattr(monitoring_runner, "MonitoringRepository", Runs)
    monkeypatch.setattr(monitoring_runner, "calculate_drift", drift)
    monkeypatch.setattr(monitoring_runner, "calculate_performance", lambda rows, settings: [])
    settings = MonitoringSettings(minimum_rows=1, max_catchup_days=2, window_days=3)
    return monitoring_runner.MonitoringRunner(Factory(), settings), state


def test_window_completes_then_replays_without_recomputing(monkeypatch):
    runner, state = make_runner(monkeypatch)
    result = runner.run_window(START, END)
    assert result == {
        "run_id": "run-1", "status": "complete", "replayed": False,
        "prediction_rows": 1, "matured_rows": 0, "metrics": 1,
    }
    assert state["completed"] == [[{"metric_name": "drift"}]]
    assert runner.run_window(START, END) == {
        "run_id": "run-1", "status": "complete", "replayed": True,
    }
    assert len(state["completed"]) == 1


def test_window_failure_is_recorded_and_can_restart(monkeypatch):
    runner, state = make_runner(monkeypatch, fail_metrics=True)
    with pytest.raises(RuntimeError, match="calculation failed"):
        runner.run_window(START, END)
    assert state["run"].status == "failed"
    assert state["failures"] == ["calculation failed"]
    with pytest.raises(RuntimeError, match="calculation failed"):
        runner.run_window(START, END)
    assert state["restarts"] == 1


def test_window_rejects_invalid_boundaries_and_missing_model(monkeypatch):
    runner, _ = make_runner(monkeypatch, active=False)
    with pytest.raises(ValueError, match="timezone-aware"):
        runner.run_window(START.replace(tzinfo=None), END)
    with pytest.raises(ValueError, match="ordered"):
        runner.run_window(END, START)
    with pytest.raises(RuntimeError, match="No active model"):
        runner.run_window(START, END)


def test_catchup_uses_bounded_utc_windows(monkeypatch):
    runner, _ = make_runner(monkeypatch)
    windows = []
    monkeypatch.setattr(
        runner, "run_window", lambda start, end: windows.append((start, end)) or {},
    )
    assert runner.run_catchup(datetime(2026, 9, 13, 18, tzinfo=UTC)) == [{}, {}]
    assert windows == [
        (datetime(2026, 9, 9, tzinfo=UTC), datetime(2026, 9, 12, tzinfo=UTC)),
        (datetime(2026, 9, 10, tzinfo=UTC), datetime(2026, 9, 13, tzinfo=UTC)),
    ]
    with pytest.raises(ValueError, match="timezone"):
        runner.run_catchup(datetime(2026, 9, 13))
