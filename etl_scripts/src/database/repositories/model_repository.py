"""Persistence operations for deployed models and reference profiles."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..models import ModelVersion, ReferenceProfile


class ModelRepository:
    def __init__(self, session: Session):
        self.session = session

    def register(self, manifest: dict, profiles: dict[str, dict]) -> ModelVersion:
        artifact_hash = manifest["artifact_sha256"]
        existing = self.session.scalar(
            select(ModelVersion).where(ModelVersion.artifact_sha256 == artifact_hash)
        )
        if existing is not None:
            self.session.execute(update(ModelVersion).values(active=False))
            existing.model_family = manifest["model_family"]
            existing.hyperparameters = manifest["hyperparameters"]
            existing.threshold = float(manifest["threshold"])
            existing.class_order = manifest["class_order"]
            existing.training_fingerprint = manifest["training_fingerprint"]
            existing.stage = manifest["stage"]
            existing.source_revision = manifest.get("source_revision")
            existing.manifest = manifest
            existing.notes = manifest.get("notes")
            existing.active = True
            self.session.execute(delete(ReferenceProfile).where(
                ReferenceProfile.model_version_id == existing.id
            ))
            self._add_profiles(existing.id, profiles)
            self.session.flush()
            return existing
        self.session.execute(update(ModelVersion).values(active=False))
        model = ModelVersion(
            id=str(uuid4()),
            artifact_sha256=artifact_hash,
            model_family=manifest["model_family"],
            hyperparameters=manifest["hyperparameters"],
            threshold=float(manifest["threshold"]),
            class_order=manifest["class_order"],
            training_fingerprint=manifest["training_fingerprint"],
            stage=manifest["stage"],
            source_revision=manifest.get("source_revision"),
            manifest=manifest,
            active=True,
            notes=manifest.get("notes"),
        )
        self.session.add(model)
        self.session.flush()
        self._add_profiles(model.id, profiles)
        self.session.flush()
        return model

    def _add_profiles(self, model_version_id: str, profiles: dict[str, dict]) -> None:
        for feature_name, profile in profiles.items():
            self.session.add(ReferenceProfile(
                id=str(uuid4()),
                model_version_id=model_version_id,
                feature_name=feature_name,
                feature_type=profile["type"],
                profile=profile,
            ))

    def active(self) -> ModelVersion | None:
        return self.session.scalar(
            select(ModelVersion)
            .where(ModelVersion.active.is_(True))
            .order_by(ModelVersion.created_at.desc())
            .limit(1)
        )

    def reference_profiles(self, model_version_id: str) -> dict[str, dict]:
        rows = self.session.scalars(
            select(ReferenceProfile).where(
                ReferenceProfile.model_version_id == model_version_id
            )
        )
        return {row.feature_name: row.profile for row in rows}
