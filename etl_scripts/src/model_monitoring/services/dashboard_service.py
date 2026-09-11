"""Read only precomputed aggregates for Dash pages."""

from sqlalchemy.orm import Session, sessionmaker

from ...database.repositories import MonitoringRepository


class DashboardService:
    def __init__(self, factory: sessionmaker[Session]):
        self.factory = factory

    def snapshot(self, model_version_id: str, limit: int = 1000) -> list[dict]:
        with self.factory() as session:
            return MonitoringRepository(session).recent_metrics(
                model_version_id, limit
            )
