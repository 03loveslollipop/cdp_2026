"""Configurable raw prediction retention; aggregate monitoring rows remain."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from ...database.models import PredictionBatch


def retain_recent_predictions(
    factory: sessionmaker[Session], retention_days: int
) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    with factory.begin() as session:
        result = session.execute(
            delete(PredictionBatch).where(PredictionBatch.created_at < cutoff)
        )
        return int(result.rowcount or 0)
