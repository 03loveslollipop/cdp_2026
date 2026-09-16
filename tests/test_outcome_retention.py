"""Matured outcomes are saved atomically; retention targets raw batches only."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace

from mlops_pipeline.src.deployment.model_monitoring.models.outcomes import OutcomeItem
from mlops_pipeline.src.deployment.model_monitoring.services import outcome_service, retention_service


def test_outcome_service_uses_single_transaction(monkeypatch):
    saved = []

    class Repository:
        def __init__(self, session):
            pass

        def save(self, event_id, actual_label, matured_at):
            saved.append((event_id, actual_label, matured_at))

    monkeypatch.setattr(outcome_service, "OutcomeRepository", Repository)
    factory = SimpleNamespace(begin=lambda: nullcontext(object()))
    matured_at = datetime(2026, 9, 13, tzinfo=UTC)
    items = [
        OutcomeItem(event_id="event-1", actual_label=0, matured_at=matured_at),
        OutcomeItem(event_id="event-2", actual_label=1, matured_at=matured_at),
    ]
    assert outcome_service.OutcomeService(factory).save(items) == 2
    assert saved == [("event-1", 0, matured_at), ("event-2", 1, matured_at)]


def test_retention_returns_deleted_batch_count():
    statements = []

    class Session:
        def execute(self, statement):
            statements.append(str(statement))
            return SimpleNamespace(rowcount=3)

    factory = SimpleNamespace(begin=lambda: nullcontext(Session()))
    assert retention_service.retain_recent_predictions(factory, 365) == 3
    assert "cdp_2026.prediction_batches" in statements[0]
