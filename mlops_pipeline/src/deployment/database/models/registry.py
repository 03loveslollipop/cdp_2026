"""Deployed model registry model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    model_family: Mapped[str] = mapped_column(String(64), nullable=False)
    hyperparameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    class_order: Mapped[list] = mapped_column(JSONB, nullable=False)
    training_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    source_revision: Mapped[str | None] = mapped_column(String(64))
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
