"""Queries and writes for aggregate monitoring jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    MonitoringMetric,
    MonitoringRun,
    ObservedOutcome,
    PredictionEvent,
)


class MonitoringRepository:
    def __init__(self, session: Session):
        self.session = session

    def find_run(self, model_version_id: str, start: datetime, end: datetime) -> MonitoringRun | None:
        return self.session.scalar(select(MonitoringRun).where(
            MonitoringRun.model_version_id == model_version_id,
            MonitoringRun.window_start == start,
            MonitoringRun.window_end == end,
        ))

    def start_run(self, model_version_id: str, start: datetime, end: datetime) -> MonitoringRun:
        run = MonitoringRun(
            id=str(uuid4()),
            model_version_id=model_version_id,
            window_start=start,
            window_end=end,
            status="running",
        )
        self.session.add(run)
        self.session.flush()
        return run

    def restart_run(self, run: MonitoringRun) -> None:
        run.status = "running"
        run.error_message = None
        run.completed_at = None
        self.session.flush()

    def prediction_rows(self, model_version_id: str, start: datetime, end: datetime) -> list[dict]:
        rows = self.session.execute(select(
            PredictionEvent.id,
            PredictionEvent.predictors,
            PredictionEvent.predicted_label,
            PredictionEvent.default_probability,
            PredictionEvent.created_at,
        ).where(
            PredictionEvent.model_version_id == model_version_id,
            PredictionEvent.created_at >= start,
            PredictionEvent.created_at < end,
        )).all()
        return [dict(row._mapping) for row in rows]

    def matured_rows(self, model_version_id: str, start: datetime, end: datetime) -> list[dict]:
        rows = self.session.execute(select(
            PredictionEvent.id,
            PredictionEvent.predicted_label,
            PredictionEvent.default_probability,
            ObservedOutcome.actual_label,
            ObservedOutcome.matured_at,
        ).join(
            ObservedOutcome,
            ObservedOutcome.prediction_event_id == PredictionEvent.id,
        ).where(
            PredictionEvent.model_version_id == model_version_id,
            ObservedOutcome.matured_at >= start,
            ObservedOutcome.matured_at < end,
        )).all()
        return [dict(row._mapping) for row in rows]

    def complete_run(self, run: MonitoringRun, metrics: list[dict], status: str = "complete") -> None:
        for metric in metrics:
            feature = metric.get("feature_name")
            self.session.add(MonitoringMetric(
                id=str(uuid4()),
                run_id=run.id,
                metric_name=metric["metric_name"],
                feature_name=feature,
                feature_key=feature or "",
                metric_value=metric.get("metric_value"),
                status=metric.get("status", "ok"),
                details=metric.get("details", {}),
            ))
        run.status = status
        run.completed_at = datetime.now(UTC)
        self.session.flush()

    def fail_run(self, run: MonitoringRun, error: Exception) -> None:
        run.status = "failed"
        run.error_message = str(error)[:2000]
        run.completed_at = datetime.now(UTC)
        self.session.flush()

    def recent_metrics(
        self, model_version_id: str, limit: int = 500
    ) -> list[dict]:
        rows = self.session.execute(select(
            MonitoringRun.window_start,
            MonitoringRun.window_end,
            MonitoringRun.status.label("run_status"),
            MonitoringMetric.metric_name,
            MonitoringMetric.feature_name,
            MonitoringMetric.metric_value,
            MonitoringMetric.status,
            MonitoringMetric.details,
        ).join(
            MonitoringMetric, MonitoringMetric.run_id == MonitoringRun.id
        ).where(
            MonitoringRun.model_version_id == model_version_id
        ).order_by(MonitoringRun.window_end.desc()).limit(limit)).all()
        return [dict(row._mapping) for row in rows]
