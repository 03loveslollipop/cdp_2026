"""Prediction and outcome routes map malformed requests to stable HTTP errors."""

from __future__ import annotations

import io
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from etl_scripts.src.model_deploy.api import predictions
from etl_scripts.src.model_deploy.models.api import PredictionRequest
from etl_scripts.src.model_deploy.services.prediction_service import (
    IdempotencyConflictError,
    PredictionValidationError,
)
from etl_scripts.src.model_monitoring.visualization.api import outcomes
from etl_scripts.src.database.repositories.outcome_repository import OutcomeConflictError


def inference_runtime(max_upload_bytes=100):
    return SimpleNamespace(settings=SimpleNamespace(max_upload_bytes=max_upload_bytes))


def test_prediction_errors_keep_validation_and_idempotency_distinct():
    class Service:
        def __init__(self, error):
            self.error = error

        def predict(self, records, key):
            raise self.error

    for error, status in (
        (PredictionValidationError("bad row"), 422),
        (IdempotencyConflictError("changed batch"), 409),
    ):
        with pytest.raises(HTTPException) as caught:
            predictions._predict(Service(error), [{}], "request-key")
        assert caught.value.status_code == status


def test_json_and_csv_prediction_routes_use_same_service(monkeypatch):
    captured = []

    class Service:
        def predict(self, records, key):
            captured.append((records, key))
            return {"items": []}

    monkeypatch.setattr(predictions, "_service", lambda runtime, request: Service())
    request = SimpleNamespace(state=SimpleNamespace(principal=None))
    runtime = inference_runtime()
    payload = PredictionRequest(records=[{"amount": 5}])
    assert predictions.predict_json(payload, request, "request-key", runtime) == {"items": []}
    csv_file = UploadFile(file=io.BytesIO(b"amount\n10\n"), filename="sample.csv")
    assert predictions.predict_csv(request, "request-key", runtime, csv_file) == {"items": []}
    assert captured == [([{"amount": 5}], "request-key"), ([{"amount": 10}], "request-key")]


def test_csv_route_rejects_size_parse_and_duplicate_columns(monkeypatch):
    request = SimpleNamespace(state=SimpleNamespace(principal=None))
    with pytest.raises(HTTPException) as oversized:
        predictions.predict_csv(
            request, "request-key", inference_runtime(max_upload_bytes=1),
            UploadFile(file=io.BytesIO(b"a,b\n1,2\n"), filename="large.csv"),
        )
    assert oversized.value.status_code == 413
    with pytest.raises(HTTPException) as malformed:
        predictions.predict_csv(
            request, "request-key", inference_runtime(),
            UploadFile(file=io.BytesIO(b""), filename="empty.csv"),
        )
    assert malformed.value.status_code == 422
    monkeypatch.setattr(
        predictions.pd, "read_csv",
        lambda stream: pd.DataFrame([[1, 2]], columns=["duplicate", "duplicate"]),
    )
    with pytest.raises(HTTPException) as duplicate:
        predictions.predict_csv(
            request, "request-key", inference_runtime(),
            UploadFile(file=io.BytesIO(b"anything"), filename="duplicate.csv"),
        )
    assert duplicate.value.status_code == 422


def test_outcome_route_maps_missing_and_conflicting_records(monkeypatch):
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(HTTPException) as not_ready:
        outcomes.save_outcomes(SimpleNamespace(outcomes=[]), request)
    assert not_ready.value.status_code == 503
    request.app.state.runtime = SimpleNamespace(session_factory=object())

    class Service:
        error = None

        def __init__(self, factory):
            pass

        def save(self, rows):
            if self.error:
                raise self.error
            return len(rows)

    monkeypatch.setattr(outcomes, "OutcomeService", Service)
    payload = SimpleNamespace(outcomes=[{"event_id": "event-1"}])
    assert outcomes.save_outcomes(payload, request) == {"accepted": 1}
    for error, code in ((LookupError("missing"), 404), (OutcomeConflictError("conflict"), 409)):
        Service.error = error
        with pytest.raises(HTTPException) as caught:
            outcomes.save_outcomes(payload, request)
        assert caught.value.status_code == code
