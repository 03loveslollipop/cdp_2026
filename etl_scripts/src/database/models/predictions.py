"""Prediction request, event, and outcome models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..connectors.postgres import SCHEMA_NAME
from .base import Base


class PredictionBatch(Base):
    __tablename__ = "prediction_batches"
    __table_args__ = (
        CheckConstraint("row_count >= 0", name="row_count_non_negative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA_NAME}.model_versions.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PredictionEvent(Base):
    __tablename__ = "prediction_events"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_number"),
        CheckConstraint("row_number >= 0", name="row_number_non_negative"),
        CheckConstraint(
            "default_probability >= 0 AND default_probability <= 1",
            name="default_probability_range",
        ),
        CheckConstraint(
            "on_time_probability >= 0 AND on_time_probability <= 1",
            name="on_time_probability_range",
        ),
        CheckConstraint("predicted_label IN (0, 1)", name="predicted_label_binary"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA_NAME}.prediction_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA_NAME}.model_versions.id"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(128), index=True)
    predictors: Mapped[dict] = mapped_column(JSONB, nullable=False)
    default_probability: Mapped[float] = mapped_column(Float, nullable=False)
    on_time_probability: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_label: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class ObservedOutcome(Base):
    __tablename__ = "observed_outcomes"
    __table_args__ = (
        CheckConstraint("actual_label IN (0, 1)", name="actual_label_binary"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    prediction_event_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA_NAME}.prediction_events.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    actual_label: Mapped[int] = mapped_column(Integer, nullable=False)
    matured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
