"""Monitoring visualization environment settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class VisualizationSettings:
    auth_service_url: str | None = None
    internal_service_token: str | None = None
    inference_service_url: str | None = None
    environment: str = "production"

    @classmethod
    def from_env(cls) -> "VisualizationSettings":
        return cls(
            auth_service_url=os.getenv("CDP_AUTH_SERVICE_URL"),
            internal_service_token=os.getenv("CDP_INTERNAL_SERVICE_TOKEN"),
            inference_service_url=os.getenv("CDP_INFERENCE_SERVICE_URL"),
            environment=os.getenv("CDP_ENVIRONMENT", "production"),
        )

    def validate(self) -> None:
        required = {
            "CDP_AUTH_SERVICE_URL": self.auth_service_url,
            "CDP_INTERNAL_SERVICE_TOKEN": self.internal_service_token,
            "CDP_INFERENCE_SERVICE_URL": self.inference_service_url,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Required visualization settings missing: {missing}")
        if len(self.internal_service_token or "") < 32:
            raise RuntimeError("CDP_INTERNAL_SERVICE_TOKEN must be at least 32 characters")
        for value in (self.auth_service_url, self.inference_service_url):
            if not (value or "").startswith(("http://", "https://")):
                raise RuntimeError("Service URLs must use HTTP(S)")
