"""Reference distributions and aggregate monitoring results."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..connectors.postgres import SCHEMA_NAME
from .base import Base


class ReferenceProfile(Base):
    __tablename__ = "reference_profiles"
    __table_args__ = (UniqueConstraint("model_version_id", "feature_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA_NAME}.model_versions.id"), nullable=False, index=True
    )
    feature_name: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_type: Mapped[str] = mapped_column(String(24), nullable=False)
    profile: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"
    __table_args__ = (
        UniqueConstraint("model_version_id", "window_start", "window_end"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA_NAME}.model_versions.id"), nullable=False, index=True
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class MonitoringMetric(Base):
    __tablename__ = "monitoring_metrics"
    __table_args__ = (
        UniqueConstraint("run_id", "metric_name", "feature_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA_NAME}.monitoring_runs.id"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_name: Mapped[str | None] = mapped_column(String(128))
    feature_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    metric_value: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
