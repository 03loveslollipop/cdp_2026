"""Aggregate metric value passed from calculators to repositories."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class MetricResult:
    metric_name: str
    metric_value: float | None
    status: str
    feature_name: str | None = None
    details: dict = field(default_factory=dict)

    def as_record(self) -> dict:
        return asdict(self)
