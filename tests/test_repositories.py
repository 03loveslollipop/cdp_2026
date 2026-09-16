"""Repository writes preserve ownership, idempotency, and immutable outcomes."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from mlops_pipeline.src.deployment.database.repositories.auth_user_repository import AuthUserRepository
from mlops_pipeline.src.deployment.database.repositories.model_repository import ModelRepository
from mlops_pipeline.src.deployment.database.repositories.monitoring_repository import MonitoringRepository
from mlops_pipeline.src.deployment.database.repositories.outcome_repository import (
    OutcomeConflictError,
    OutcomeRepository,
)
from mlops_pipeline.src.deployment.database.repositories.prediction_repository import PredictionRepository
from mlops_pipeline.src.deployment.database.repositories.sample_repository import SampleRepository


class Session:
    def __init__(self):
        self.added = []
        self.executed = []
        self.scalar_result = None
        self.scalars_result = []
        self.get_result = None
        self.result = None
        self.flushes = 0

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flushes += 1

    def execute(self, statement):
        self.executed.append(statement)
        return self.result

    def scalar(self, statement):
        return self.scalar_result

    def scalars(self, statement):
        return self.scalars_result

    def get(self, model, identity):
        return self.get_result


def test_model_registry_creates_then_reactivates_same_artifact():
    session = Session()
    repository = ModelRepository(session)
    manifest = {
        "artifact_sha256": "a" * 64, "model_family": "xgboost",
        "hyperparameters": {"max_depth": 3}, "threshold": 0.2,
        "class_order": [0, 1], "training_fingerprint": "f" * 64,
        "stage": "staging", "source_revision": "abc", "notes": "demo",
    }
    model = repository.register(manifest, {"amount": {"type": "numeric"}})
    assert model.active
    assert model.artifact_sha256 == "a" * 64
    assert session.added[1].feature_name == "amount"
    assert session.flushes >= 2

    session.scalar_result = model
    refreshed = repository.register(
        {**manifest, "threshold": 0.3}, {"kind": {"type": "categorical"}}
    )
    assert refreshed is model
    assert refreshed.threshold == 0.3
    assert session.added[-1].feature_name == "kind"
    assert len(session.executed) >= 3
    assert repository.active() is model
    session.scalars_result = [SimpleNamespace(feature_name="kind", profile={"a": 1})]
    assert repository.reference_profiles(model.id) == {"kind": {"a": 1}}


def test_auth_user_repository_updates_token_version_on_security_changes():
    session = Session()
    repository = AuthUserRepository(session)
    user = repository.create("analyst", "argon2-hash", "inference")
    assert user.token_version == 0
    assert user.active
    session.get_result = user
    session.scalar_result = user
    session.scalars_result = [user]
    assert repository.by_id(user.id) is user
    assert repository.by_username("analyst") is user
    assert repository.list_all() == [user]
    session.scalar_result = 1
    assert repository.count() == 1
    assert repository.active_owner_count() == 1
    repository.record_login(user, "upgraded-hash")
    assert user.password_hash == "upgraded-hash"
    assert user.last_login_at.tzinfo is not None
    repository.set_password(user, "new-hash")
    repository.set_role(user, "owner")
    repository.set_active(user, False)
    assert user.token_version == 3
    repository.set_role(user, "owner")
    repository.set_active(user, False)
    assert user.token_version == 3


def test_monitoring_repository_records_metrics_and_terminal_states():
    session = Session()
    repository = MonitoringRepository(session)
    start = datetime(2026, 9, 10, tzinfo=UTC)
    end = datetime(2026, 9, 11, tzinfo=UTC)
    run = repository.start_run("model-1", start, end)
    assert run.status == "running"
    session.scalar_result = run
    assert repository.find_run("model-1", start, end) is run
    run.status = "failed"
    run.error_message = "old error"
    repository.restart_run(run)
    assert run.status == "running"
    assert run.error_message is None
    repository.complete_run(run, [{
        "metric_name": "population_psi", "feature_name": "amount",
        "metric_value": 0.2, "status": "warning", "details": {"rows": 10},
    }])
    assert run.status == "complete"
    assert session.added[-1].feature_key == "amount"
    assert session.added[-1].metric_value == 0.2
    repository.fail_run(run, RuntimeError("bad calculation"))
    assert run.status == "failed"
    assert run.error_message == "bad calculation"

    row = SimpleNamespace(_mapping={"metric_name": "population_psi"})
    session.result = SimpleNamespace(all=lambda: [row])
    assert repository.prediction_rows("model-1", start, end) == [row._mapping]
    assert repository.matured_rows("model-1", start, end) == [row._mapping]
    assert repository.recent_metrics("model-1") == [row._mapping]


def test_prediction_repository_keeps_batch_identity_and_order():
    session = Session()
    repository = PredictionRepository(session)
    session.result = SimpleNamespace(one_or_none=lambda: None)
    assert repository.by_idempotency_key("request-1", "user-1") is None
    batch = SimpleNamespace(id="batch-1")
    events = [SimpleNamespace(row_number=0)]
    session.result = SimpleNamespace(one_or_none=lambda: (batch, "xgboost"))
    session.scalars_result = events
    assert repository.by_idempotency_key("request-1", "user-1") == (batch, events)
    assert batch.model_family == "xgboost"

    saved_batch, saved_events = repository.save_completed(
        idempotency_key="request-1", request_sha256="a" * 64,
        model_version_id="model-1", requested_by_user_id="user-1",
        duration_ms=3.2, records=[{"amount": 10}, {"amount": 20}],
        probabilities=[(0.2, 0.8), (0.7, 0.3)], predictions=[1, 0],
        external_references=[None, "row-b"],
    )
    assert saved_batch.row_count == 2
    assert saved_batch.requested_by_user_id == "user-1"
    assert [event.row_number for event in saved_events] == [0, 1]
    assert saved_events[1].default_probability == 0.7
    assert saved_events[1].external_reference == "row-b"


def test_outcome_repository_is_immutable_and_replayable():
    session = Session()
    repository = OutcomeRepository(session)
    matured_at = datetime(2026, 9, 13, tzinfo=UTC)
    with pytest.raises(LookupError, match="Unknown prediction"):
        repository.save("event-1", 0, matured_at)
    session.get_result = object()
    outcome = repository.save("event-1", 0, matured_at)
    assert outcome.actual_label == 0
    session.scalar_result = outcome
    assert repository.save("event-1", 0, matured_at) is outcome
    with pytest.raises(OutcomeConflictError, match="different values"):
        repository.save("event-1", 1, matured_at)


def test_sample_repository_skips_empty_imports_and_counts_insertions():
    session = Session()
    repository = SampleRepository(session)
    assert repository.insert_missing([]) == 0
    session.scalars_result = SimpleNamespace(all=lambda: ["hash-1"])
    assert repository.insert_missing([{"source_row_hash": "hash-1"}]) == 1
