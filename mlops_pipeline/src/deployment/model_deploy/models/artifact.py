"""Validated artifact bundle passed to prediction services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoadedArtifact:
    model: object
    manifest: dict
    reference_profiles: dict[str, dict]

    @property
    def model_family(self) -> str:
        return str(self.manifest["model_family"])

    @property
    def artifact_sha256(self) -> str:
        return str(self.manifest["artifact_sha256"])
