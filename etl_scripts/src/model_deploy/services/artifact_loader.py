"""Load and cryptographically validate a portable model bundle."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

import joblib
import numpy as np

from ..models.artifact import LoadedArtifact


MODEL_FILE = "best_model.joblib"
MANIFEST_FILE = "deployment_manifest.json"
PROFILES_FILE = "reference_profiles.json"


def load_artifact(directory: str | Path) -> LoadedArtifact:
    root = Path(directory)
    model_path = root / MODEL_FILE
    manifest = json.loads((root / MANIFEST_FILE).read_text(encoding="utf-8"))
    profiles = json.loads((root / PROFILES_FILE).read_text(encoding="utf-8"))
    actual_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if actual_hash != manifest.get("artifact_sha256"):
        raise RuntimeError("Model artifact SHA-256 does not match its manifest")
    if manifest.get("class_order") != [0, 1]:
        raise RuntimeError("Deployment artifacts must expose classes [0, 1]")
    for package, expected in manifest.get("packages", {}).items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as error:
            raise RuntimeError(f"Artifact dependency is not installed: {package}") from error
        if actual != expected:
            raise RuntimeError(
                f"Artifact dependency mismatch for {package}: expected {expected}, got {actual}"
            )
    model = joblib.load(model_path)
    if not np.array_equal(getattr(model, "classes_", None), [0, 1]):
        raise RuntimeError("Loaded model has an incompatible class order")
    if not callable(getattr(model, "predict", None)) or not callable(
        getattr(model, "predict_proba", None)
    ):
        raise RuntimeError("Loaded artifact lacks the prediction interface")
    return LoadedArtifact(model=model, manifest=manifest, reference_profiles=profiles)
