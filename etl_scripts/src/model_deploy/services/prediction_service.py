"""Validated, idempotent, transactionally logged batch inference."""

from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ...database.repositories import PredictionRepository
from ..models import LoadedArtifact


class PredictionValidationError(ValueError):
    pass


class IdempotencyConflictError(ValueError):
    pass


class PredictionService:
    def __init__(
        self,
        artifact: LoadedArtifact,
        model_version_id: str,
        session_factory: sessionmaker[Session],
        max_batch_rows: int,
    ):
        self.artifact = artifact
        self.model_version_id = model_version_id
        self.session_factory = session_factory
        self.max_batch_rows = max_batch_rows
        self.required = list(artifact.manifest["required_predictors"])

    def _validate(self, records: list[dict[str, Any]]) -> tuple[list[dict], list[str | None]]:
        if not records or len(records) > self.max_batch_rows:
            raise PredictionValidationError(
                f"Batch must contain between 1 and {self.max_batch_rows} records"
            )
        required = set(self.required)
        allowed = required | {"_external_reference"}
        normalized: list[dict] = []
        references: list[str | None] = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise PredictionValidationError(f"Record {index} must be an object")
            missing = required - set(record)
            extra = set(record) - allowed
            if missing or extra:
                raise PredictionValidationError(
                    f"Record {index} schema mismatch; missing={sorted(missing)}, "
                    f"extra={sorted(extra)}"
                )
            reference = record.get("_external_reference")
            if reference is not None and (not isinstance(reference, str) or len(reference) > 128):
                raise PredictionValidationError(
                    f"Record {index} _external_reference must be a string of at most 128 characters"
                )
            row = {column: record[column] for column in self.required}
            for column, value in row.items():
                if value is not None and not isinstance(
                    value, (str, int, float, bool)
                ):
                    raise PredictionValidationError(
                        f"Record {index} predictor {column} must be a JSON scalar or null"
                    )
                if isinstance(value, float) and not math.isfinite(value):
                    row[column] = None
            normalized.append(row)
            references.append(reference)
        try:
            json.dumps(normalized, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise PredictionValidationError(
                "Predictor values must be finite JSON scalars or null"
            ) from error
        return normalized, references

    @staticmethod
    def _request_hash(records: list[dict], references: list[str | None]) -> str:
        payload = json.dumps(
            {"records": records, "external_references": references},
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _result(self, batch, events, replay: bool) -> dict:
        return {
            "batch_id": batch.id,
            "idempotent_replay": replay,
            "model_version_id": self.model_version_id,
            "model_family": self.artifact.model_family,
            "class_order": [0, 1],
            "items": [{
                "event_id": event.id,
                "row_number": event.row_number,
                "external_reference": event.external_reference,
                "predicted_label": event.predicted_label,
                "default_probability": event.default_probability,
                "on_time_probability": event.on_time_probability,
            } for event in events],
        }

    def _existing(self, key: str, request_hash: str):
        with self.session_factory() as session:
            found = PredictionRepository(session).by_idempotency_key(key)
            if found is None:
                return None
            batch, events = found
            if batch.request_sha256 != request_hash:
                raise IdempotencyConflictError(
                    "Idempotency key was already used for a different request"
                )
            return self._result(batch, events, True)

    def predict(self, records: list[dict[str, Any]], idempotency_key: str) -> dict:
        if not 8 <= len(idempotency_key) <= 128:
            raise PredictionValidationError(
                "Idempotency-Key must contain between 8 and 128 characters"
            )
        normalized, references = self._validate(records)
        request_hash = self._request_hash(normalized, references)
        existing = self._existing(idempotency_key, request_hash)
        if existing is not None:
            return existing
        frame = pd.DataFrame(normalized, columns=self.required)
        started = time.perf_counter()
        try:
            probabilities = np.asarray(
                self.artifact.model.predict_proba(frame), dtype=float
            )
            predictions = np.asarray(self.artifact.model.predict(frame), dtype=int)
        except (TypeError, ValueError) as error:
            raise PredictionValidationError(str(error)) from error
        duration_ms = 1000 * (time.perf_counter() - started)
        if (
            probabilities.shape != (len(frame), 2)
            or predictions.shape != (len(frame),)
            or not np.isfinite(probabilities).all()
            or not np.isin(predictions, [0, 1]).all()
            or not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-6)
        ):
            raise RuntimeError("Model returned an invalid prediction contract")
        try:
            with self.session_factory.begin() as session:
                repository = PredictionRepository(session)
                found = repository.by_idempotency_key(idempotency_key)
                if found is not None:
                    batch, events = found
                    if batch.request_sha256 != request_hash:
                        raise IdempotencyConflictError(
                            "Idempotency key was already used for a different request"
                        )
                    return self._result(batch, events, True)
                batch, events = repository.save_completed(
                    idempotency_key=idempotency_key,
                    request_sha256=request_hash,
                    model_version_id=self.model_version_id,
                    duration_ms=duration_ms,
                    records=normalized,
                    probabilities=[tuple(row) for row in probabilities.tolist()],
                    predictions=predictions.tolist(),
                    external_references=references,
                )
                result = self._result(batch, events, False)
            return result
        except IntegrityError:
            replay = self._existing(idempotency_key, request_hash)
            if replay is None:
                raise
            return replay
