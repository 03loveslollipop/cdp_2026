"""Transactional prediction-batch persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ModelVersion, PredictionBatch, PredictionEvent


class PredictionRepository:
    def __init__(self, session: Session):
        self.session = session

    def by_idempotency_key(
        self, key: str, requested_by_user_id: str | None
    ) -> tuple[PredictionBatch, list[PredictionEvent]] | None:
        stored = self.session.execute(
            select(PredictionBatch, ModelVersion.model_family)
            .join(ModelVersion, ModelVersion.id == PredictionBatch.model_version_id)
            .where(
                PredictionBatch.idempotency_key == key,
                PredictionBatch.requested_by_user_id == requested_by_user_id,
            )
        ).one_or_none()
        if stored is None:
            return None
        batch, model_family = stored
        batch.model_family = model_family
        events = list(self.session.scalars(
            select(PredictionEvent)
            .where(PredictionEvent.batch_id == batch.id)
            .order_by(PredictionEvent.row_number)
        ))
        return batch, events

    def save_completed(
        self,
        *,
        idempotency_key: str,
        request_sha256: str,
        model_version_id: str,
        requested_by_user_id: str | None,
        duration_ms: float,
        records: list[dict],
        probabilities: list[tuple[float, float]],
        predictions: list[int],
        external_references: list[str | None],
    ) -> tuple[PredictionBatch, list[PredictionEvent]]:
        now = datetime.now(UTC)
        batch = PredictionBatch(
            id=str(uuid4()),
            idempotency_key=idempotency_key,
            request_sha256=request_sha256,
            model_version_id=model_version_id,
            requested_by_user_id=requested_by_user_id,
            status="complete",
            row_count=len(records),
            duration_ms=duration_ms,
            completed_at=now,
        )
        self.session.add(batch)
        self.session.flush()
        events = []
        for row_number, (record, probability, prediction, reference) in enumerate(zip(
            records, probabilities, predictions, external_references, strict=True
        )):
            event = PredictionEvent(
                id=str(uuid4()),
                batch_id=batch.id,
                model_version_id=model_version_id,
                row_number=row_number,
                external_reference=reference,
                predictors=record,
                default_probability=float(probability[0]),
                on_time_probability=float(probability[1]),
                predicted_label=int(prediction),
            )
            self.session.add(event)
            events.append(event)
        self.session.flush()
        return batch, events
