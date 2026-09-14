"""Idempotent rolling-window monitoring with missed-window catch-up."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from sqlalchemy.orm import Session, sessionmaker

from ...database.models import MonitoringRun
from ...database.repositories import ModelRepository, MonitoringRepository
from ..settings import MonitoringSettings
from .drift_service import calculate_drift
from .performance_service import calculate_performance


class MonitoringRunner:
    def __init__(
        self,
        factory: sessionmaker[Session],
        settings: MonitoringSettings | None = None,
    ):
        self.factory = factory
        self.settings = settings or MonitoringSettings.from_env()
        self.settings.validate()

    def run_window(self, start: datetime, end: datetime) -> dict:
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("Monitoring windows must be ordered timezone-aware datetimes")
        with self.factory.begin() as session:
            model_repository = ModelRepository(session)
            model = model_repository.active()
            if model is None:
                raise RuntimeError("No active model version is registered")
            repository = MonitoringRepository(session)
            run = repository.find_run(model.id, start, end)
            if run is not None and run.status == "complete":
                return {"run_id": run.id, "status": "complete", "replayed": True}
            if run is None:
                run = repository.start_run(model.id, start, end)
            else:
                repository.restart_run(run)
            run_id = run.id
            model_id = model.id
            profiles = model_repository.reference_profiles(model.id)
        try:
            with self.factory.begin() as session:
                repository = MonitoringRepository(session)
                run = session.get(MonitoringRun, run_id)
                prediction_rows = repository.prediction_rows(model_id, start, end)
                matured_rows = repository.matured_rows(model_id, start, end)
                metrics = calculate_drift(
                    prediction_rows, profiles, self.settings
                ) + calculate_performance(matured_rows, self.settings)
                repository.complete_run(
                    run,
                    [metric.as_record() for metric in metrics],
                    status="complete",
                )
            return {
                "run_id": run_id,
                "status": "complete",
                "replayed": False,
                "prediction_rows": len(prediction_rows),
                "matured_rows": len(matured_rows),
                "metrics": len(metrics),
            }
        except Exception as error:
            with self.factory.begin() as session:
                run = session.get(MonitoringRun, run_id)
                if run is not None:
                    MonitoringRepository(session).fail_run(run, error)
            raise

    def run_catchup(self, now: datetime | None = None) -> list[dict]:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise ValueError("Catch-up time must include a timezone")
        today = datetime.combine(current.date(), time.min, tzinfo=UTC)
        results = []
        for days_ago in range(self.settings.max_catchup_days - 1, -1, -1):
            end = today - timedelta(days=days_ago)
            start = end - timedelta(days=self.settings.window_days)
            results.append(self.run_window(start, end))
        return results
