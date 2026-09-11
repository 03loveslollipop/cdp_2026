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
    jwt_private_key: str | None = None
    jwt_public_key: str | None = None
    jwt_issuer: str = "cdp-2026-credit-risk"
    jwt_audience: str = "cdp-2026-api"
    auth_disabled: bool = False
    environment: str = "production"
    log_level: str = "info"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            artifact_dir=Path(os.getenv("CDP_ARTIFACT_DIR", "deployment_artifacts")),
            max_batch_rows=int(os.getenv("CDP_MAX_BATCH_ROWS", "1000")),
            max_upload_bytes=int(os.getenv("CDP_MAX_UPLOAD_BYTES", "5000000")),
            jwt_private_key=_pem_value(os.getenv("CDP_JWT_PRIVATE_KEY")),
            jwt_public_key=_pem_value(os.getenv("CDP_JWT_PUBLIC_KEY")),
            jwt_issuer=os.getenv("CDP_JWT_ISSUER", "cdp-2026-credit-risk"),
            jwt_audience=os.getenv("CDP_JWT_AUDIENCE", "cdp-2026-api"),
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
            "CDP_JWT_PRIVATE_KEY": self.jwt_private_key,
            "CDP_JWT_PUBLIC_KEY": self.jwt_public_key,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Required authentication settings missing: {missing}")
        if not self.jwt_issuer or not self.jwt_audience:
            raise RuntimeError("JWT issuer and audience must not be empty")


def _pem_value(value: str | None) -> str | None:
    """Accept real or escaped newlines without logging key material."""
    return value.replace("\\n", "\n") if value else None
