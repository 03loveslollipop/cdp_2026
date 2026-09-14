"""Idempotent loading of the approved non-production CSV sample."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models import SampleLoan


class SampleRepository:
    def __init__(self, session: Session):
        self.session = session

    def insert_missing(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        statement = insert(SampleLoan).values(rows)
        statement = statement.on_conflict_do_nothing(
            index_elements=[SampleLoan.source_row_hash]
        ).returning(SampleLoan.source_row_hash)
        return len(self.session.scalars(statement).all())
