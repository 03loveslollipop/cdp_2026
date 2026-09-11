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
    auth_username: str | None = None
    auth_password: str | None = None
    auth_disabled: bool = False
    environment: str = "development"
    log_level: str = "info"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            artifact_dir=Path(os.getenv("CDP_ARTIFACT_DIR", "deployment_artifacts")),
            max_batch_rows=int(os.getenv("CDP_MAX_BATCH_ROWS", "1000")),
            max_upload_bytes=int(os.getenv("CDP_MAX_UPLOAD_BYTES", "5000000")),
            auth_username=os.getenv("CDP_AUTH_USERNAME"),
            auth_password=os.getenv("CDP_AUTH_PASSWORD"),
            auth_disabled=_flag("CDP_AUTH_DISABLED"),
            environment=os.getenv("CDP_ENVIRONMENT", "development"),
            log_level=os.getenv("CDP_LOG_LEVEL", "info"),
        )

    def validate(self) -> None:
        if self.max_batch_rows < 1 or self.max_upload_bytes < 1:
            raise ValueError("Batch and upload limits must be positive")
        if not self.auth_disabled and not (self.auth_username and self.auth_password):
            raise RuntimeError(
                "CDP_AUTH_USERNAME and CDP_AUTH_PASSWORD are required"
            )
