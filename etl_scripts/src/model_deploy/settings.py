"""Environment-backed serving settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    artifact_dir: Path = Path("deployment_artifacts")
    max_batch_rows: int = 1000
    max_upload_bytes: int = 5_000_000
    auth_service_url: str | None = None
    internal_service_token: str | None = None
    monitor_ui_url: str | None = None
    auth_disabled: bool = False
    environment: str = "production"
    log_level: str = "info"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            artifact_dir=Path(os.getenv("CDP_ARTIFACT_DIR", "deployment_artifacts")),
            max_batch_rows=int(os.getenv("CDP_MAX_BATCH_ROWS", "1000")),
            max_upload_bytes=int(os.getenv("CDP_MAX_UPLOAD_BYTES", "5000000")),
            auth_service_url=os.getenv("CDP_AUTH_SERVICE_URL"),
            internal_service_token=os.getenv("CDP_INTERNAL_SERVICE_TOKEN"),
            monitor_ui_url=os.getenv("CDP_MONITOR_UI_URL"),
            auth_disabled=_flag("CDP_AUTH_DISABLED"),
            environment=os.getenv("CDP_ENVIRONMENT", "production"),
            log_level=os.getenv("CDP_LOG_LEVEL", "info"),
        )

    def validate(self) -> None:
        if self.max_batch_rows < 1 or self.max_upload_bytes < 1:
            raise ValueError("Batch and upload limits must be positive")
        if self.auth_disabled:
            return
        required = {
            "CDP_AUTH_SERVICE_URL": self.auth_service_url,
            "CDP_INTERNAL_SERVICE_TOKEN": self.internal_service_token,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Required authentication settings missing: {missing}")
        if len(self.internal_service_token or "") < 32:
            raise RuntimeError("CDP_INTERNAL_SERVICE_TOKEN must be at least 32 characters")
        if not (self.auth_service_url or "").startswith(("http://", "https://")):
            raise RuntimeError("CDP_AUTH_SERVICE_URL must be an HTTP(S) URL")
