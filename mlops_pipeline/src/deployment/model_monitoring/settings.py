"""Monitoring job settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MonitoringSettings:
    minimum_rows: int = 30
    window_days: int = 7
    max_catchup_days: int = 7
    retention_days: int = 365
    psi_warning: float = 0.10
    psi_alert: float = 0.25

    @classmethod
    def from_env(cls) -> "MonitoringSettings":
        return cls(
            minimum_rows=int(os.getenv("CDP_MONITOR_MIN_ROWS", "30")),
            window_days=int(os.getenv("CDP_MONITOR_WINDOW_DAYS", "7")),
            max_catchup_days=int(os.getenv("CDP_MONITOR_MAX_CATCHUP_DAYS", "7")),
            retention_days=int(os.getenv("CDP_RETENTION_DAYS", "365")),
            psi_warning=float(os.getenv("CDP_PSI_WARNING", "0.10")),
            psi_alert=float(os.getenv("CDP_PSI_ALERT", "0.25")),
        )

    def validate(self) -> None:
        if min(
            self.minimum_rows,
            self.window_days,
            self.max_catchup_days,
            self.retention_days,
        ) < 1:
            raise ValueError("Monitoring row, window, catch-up, and retention limits must be positive")
        if not 0 < self.psi_warning < self.psi_alert:
            raise ValueError("PSI thresholds must be positive and ordered")
