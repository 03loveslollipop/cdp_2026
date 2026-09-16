"""Authentication-service environment settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _pem_value(value: str | None) -> str | None:
    return value.replace("\\n", "\n") if value else None


@dataclass(frozen=True)
class AuthSettings:
    jwt_private_key: str | None = None
    jwt_public_key: str | None = None
    jwt_issuer: str = "cdp-2026-credit-risk"
    jwt_audience: str = "cdp-2026-api"
    internal_service_token: str | None = None
    allowed_origins: tuple[str, ...] = ()
    environment: str = "production"

    @classmethod
    def from_env(cls) -> "AuthSettings":
        origins = tuple(
            origin.strip()
            for origin in os.getenv("CDP_ALLOWED_ORIGINS", "").split(",")
            if origin.strip()
        )
        return cls(
            jwt_private_key=_pem_value(os.getenv("CDP_JWT_PRIVATE_KEY")),
            jwt_public_key=_pem_value(os.getenv("CDP_JWT_PUBLIC_KEY")),
            jwt_issuer=os.getenv("CDP_JWT_ISSUER", "cdp-2026-credit-risk"),
            jwt_audience=os.getenv("CDP_JWT_AUDIENCE", "cdp-2026-api"),
            internal_service_token=os.getenv("CDP_INTERNAL_SERVICE_TOKEN"),
            allowed_origins=origins,
            environment=os.getenv("CDP_ENVIRONMENT", "production"),
        )

    def validate(self) -> None:
        required = {
            "CDP_JWT_PRIVATE_KEY": self.jwt_private_key,
            "CDP_JWT_PUBLIC_KEY": self.jwt_public_key,
            "CDP_INTERNAL_SERVICE_TOKEN": self.internal_service_token,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Required authentication settings missing: {missing}")
        if len(self.internal_service_token or "") < 32:
            raise RuntimeError("CDP_INTERNAL_SERVICE_TOKEN must be at least 32 characters")
        if not self.jwt_issuer or not self.jwt_audience:
            raise RuntimeError("JWT issuer and audience must not be empty")
