"""Persistence operations for later-arriving observed outcomes."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ObservedOutcome, PredictionEvent


class OutcomeConflictError(ValueError):
    pass


class OutcomeRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, event_id: str, actual_label: int, matured_at: datetime) -> ObservedOutcome:
        if self.session.get(PredictionEvent, event_id) is None:
            raise LookupError(f"Unknown prediction event: {event_id}")
        existing = self.session.scalar(
            select(ObservedOutcome).where(
                ObservedOutcome.prediction_event_id == event_id
            )
        )
        if existing is not None:
            if existing.actual_label != actual_label or existing.matured_at != matured_at:
                raise OutcomeConflictError(
                    f"Outcome already exists with different values: {event_id}"
                )
            return existing
        outcome = ObservedOutcome(
            id=str(uuid4()),
            prediction_event_id=event_id,
            actual_label=actual_label,
            matured_at=matured_at,
        )
        self.session.add(outcome)
        self.session.flush()
        return outcome
