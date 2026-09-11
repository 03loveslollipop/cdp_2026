"""Retrain the configured winning family and export a generic serving bundle."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from ...ft_engineering import (
    chronological_train_test_split,
    extract_dataset,
    load_config,
    read_raw_data,
)
from ...model_training_evaluation import (
    REFERENCE_MODELS,
    SelectedCreditModel,
    build_model,
    calibrated_probability,
    choose_threshold,
    evaluate_candidate,
    fit_calibrator,
    load_training_config,
    summarize_classification,
)
from .artifact_loader import MANIFEST_FILE, MODEL_FILE, PROFILES_FILE


DEPLOYMENT_CONFIG_PATH = Path(__file__).parents[2] / "deployment_model_config.json"


def load_deployment_config(path: str | Path = DEPLOYMENT_CONFIG_PATH) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"model_family", "hyperparameters", "training", "runtime", "stage"}
    if required - set(config):
        raise ValueError(f"Deployment config is missing: {sorted(required - set(config))}")
    if config["model_family"] in REFERENCE_MODELS:
        raise ValueError("Reference models cannot be deployment winners")
    if config["runtime"].get("class_order") != [0, 1]:
        raise ValueError("Deployment class_order must be [0, 1]")
    return config


def _json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_revision() -> str | None:
    if os.getenv("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _numeric_profile(values: pd.Series, bins: int = 10) -> dict:
    numeric = pd.to_numeric(values, errors="coerce")
    present = numeric.dropna().to_numpy(dtype=float)
    missing_rate = float(numeric.isna().mean())
    if len(present) == 0:
        return {"type": "numeric", "bins": [], "proportions": [1.0],
                "missing_rate": missing_rate, "rows": len(values)}
    quantiles = np.quantile(present, np.linspace(0, 1, bins + 1)[1:-1])
    boundaries = np.unique(quantiles).astype(float)
    counts = np.bincount(np.digitize(present, boundaries), minlength=len(boundaries) + 1)
    proportions = (counts / counts.sum()).astype(float)
    return {
        "type": "numeric",
        "bins": boundaries.tolist(),
        "proportions": proportions.tolist(),
        "missing_rate": missing_rate,
        "rows": len(values),
        "mean": float(np.mean(present)),
        "std": float(np.std(present)),
    }


def _categorical_profile(values: pd.Series) -> dict:
    normalized = values.astype("string")
    present = normalized.dropna()
    counts = present.value_counts(dropna=False)
    total = max(1, int(counts.sum()))
    return {
        "type": "categorical",
        "proportions": {str(key): float(value / total) for key, value in counts.items()},
        "missing_rate": float(normalized.isna().mean()),
        "rows": len(values),
    }


def build_reference_profiles(
    predictors: pd.DataFrame,
    default_probability: np.ndarray,
    project_config: dict,
) -> dict[str, dict]:
    categorical = set(project_config["predictive_pipeline"]["categorical_predictors"])
    profiles = {
        column: (
            _categorical_profile(predictors[column])
            if column in categorical
            else _numeric_profile(predictors[column])
        )
        for column in project_config["predictive_pipeline"]["required_predictors"]
    }
    profiles["__default_probability__"] = _numeric_profile(
        pd.Series(default_probability)
    )
    return profiles


def train_deployment_artifact(
    output_dir: str | Path,
    *,
    deployment_config_path: str | Path = DEPLOYMENT_CONFIG_PATH,
    project_config_path: str | Path | None = None,
    training_config_path: str | Path | None = None,
    input_path: str | Path | None = None,
    device: str | None = None,
) -> dict:
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Deployment artifact directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    deployment = load_deployment_config(deployment_config_path)
    project = load_config(project_config_path) if project_config_path else load_config()
    training = (
        load_training_config(training_config_path)
        if training_config_path else load_training_config()
    )
    configured_threads = int(deployment["training"].get("threads", 0))
    training["threads"] = configured_threads or max(1, os.cpu_count() or 1)
    training_device = device or deployment["training"].get("device", "cpu")
    random_state = int(deployment["training"].get("random_state", training["seeds"][0]))
    read_options = (
        {"config_dir": Path(project_config_path).parent}
        if project_config_path else {}
    )
    raw = read_raw_data(project, input_path, **read_options).reset_index(drop=True)
    if deployment["training"].get("training_scope") != "chronological_training_partition":
        raise ValueError("Unsupported deployment training scope")
    split = chronological_train_test_split(raw, project)
    training_data = extract_dataset(split.train, project, require_target=True)
    family = deployment["model_family"]
    parameters = dict(deployment["hyperparameters"])
    with threadpool_limits(limits=training["threads"]):
        rows, oof = evaluate_candidate(
            split.train,
            project,
            training,
            family,
            parameters,
            random_state,
            training_device,
        )
        pipeline = build_model(
            family,
            project,
            random_state,
            training_device,
            parameters=parameters,
            training_config=training,
        )
        pipeline.fit(training_data.predictors, training_data.target)
        calibrator = fit_calibrator(oof.raw_score, oof.target)
        threshold = choose_threshold(
            oof.target,
            calibrated_probability(calibrator, oof.raw_score),
        )
        model = SelectedCreditModel(pipeline, calibrator, threshold, family)
        probability = model.predict_proba(training_data.predictors)[:, 0]
    joblib.dump(model, output / MODEL_FILE)
    artifact_hash = hashlib.sha256((output / MODEL_FILE).read_bytes()).hexdigest()
    dataset_hash = hashlib.sha256(raw.to_csv(index=False).encode("utf-8")).hexdigest()
    deployment_bytes = Path(deployment_config_path).read_bytes()
    effective_training_bytes = json.dumps(
        training,
        default=str,
        sort_keys=True,
    ).encode("utf-8")
    training_config_hash = hashlib.sha256(effective_training_bytes).hexdigest()
    fingerprint = hashlib.sha256(
        dataset_hash.encode("ascii")
        + deployment_bytes
        + json.dumps(project, sort_keys=True).encode("utf-8")
        + effective_training_bytes
    ).hexdigest()
    oof_probability = calibrated_probability(calibrator, oof.raw_score)
    oof_prediction = np.where(oof_probability >= threshold, 0, 1)
    validation = summarize_classification(
        oof.target,
        oof_prediction,
        oof_probability,
        review_fraction=training["review_fraction"],
    )
    runtime_distribution = {
        "xgboost": "xgboost-cpu",
        "lightgbm": "lightgbm",
        "pytorch_mlp": "torch",
    }.get(family)
    packages = {}
    for package in (
        "numpy", "pandas", "scikit-learn", "joblib", runtime_distribution
    ):
        if package is None:
            continue
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            raise RuntimeError(f"Missing runtime distribution: {package}")
    manifest = {
        "schema_version": 1,
        "stage": deployment["stage"],
        "model_family": family,
        "hyperparameters": parameters,
        "threshold": float(threshold),
        "class_order": [0, 1],
        "default_class": 0,
        "artifact_sha256": artifact_hash,
        "training_fingerprint": fingerprint,
        "dataset_sha256": dataset_hash,
        "deployment_config_sha256": hashlib.sha256(deployment_bytes).hexdigest(),
        "effective_training_config_sha256": training_config_hash,
        "training_scope": deployment["training"]["training_scope"],
        "training_rows": len(training_data.predictors),
        "split": split.summary,
        "validation": validation,
        "temporal_folds": rows,
        "required_predictors": project["predictive_pipeline"]["required_predictors"],
        "source_revision": _source_revision(),
        "generated_at": datetime.now(UTC).isoformat(),
        "training_device": training_device,
        "serving_device": "cpu",
        "threads": training["threads"],
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
        "selection": deployment.get("selection", {}),
        "notes": "Staging/demo deployment; feature timing and outcome maturity remain assumptions.",
    }
    profiles = build_reference_profiles(training_data.predictors, probability, project)
    _json(output / MANIFEST_FILE, manifest)
    _json(output / PROFILES_FILE, profiles)
    return manifest
