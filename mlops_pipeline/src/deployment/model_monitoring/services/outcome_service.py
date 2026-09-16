"""Atomic observed-outcome ingestion."""

from sqlalchemy.orm import Session, sessionmaker

from ...database.repositories import OutcomeRepository
from ..models.outcomes import OutcomeItem


class OutcomeService:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def save(self, outcomes: list[OutcomeItem]) -> int:
        with self.session_factory.begin() as session:
            repository = OutcomeRepository(session)
            for item in outcomes:
                repository.save(item.event_id, item.actual_label, item.matured_at)
        return len(outcomes)
