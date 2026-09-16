"""Non-production source-sample storage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SampleLoan(Base):
    __tablename__ = "sample_loans"
    __table_args__ = (
        CheckConstraint("target IS NULL OR target IN (0, 1)", name="target_binary"),
    )

    source_row_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    predictors: Mapped[dict] = mapped_column(JSONB, nullable=False)
    target: Mapped[int | None] = mapped_column(Integer)
    loan_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
