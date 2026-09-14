"""Deployment packaging freezes the configured family before any holdout inspection."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from etl_scripts.src.model_deploy.services import model_trainer


def deployment_config():
    return {
        "stage": "staging", "model_family": "logistic_regression",
        "hyperparameters": {"C": 1.0},
        "training": {
            "device": "cpu", "threads": 1, "random_state": 42,
            "training_scope": "chronological_training_partition",
        },
        "runtime": {"class_order": [0, 1]},
    }


def test_deployment_config_rejects_invalid_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(model_trainer, "PROJECT_ROOT", tmp_path)
    config_path = tmp_path / "deployment_model_config.json"
    for change, reason in (
        ({"runtime": {"class_order": [1, 0]}}, "class_order"),
        ({"model_family": "dummy"}, "Reference models"),
        ({"training": None}, "missing"),
    ):
        config = deployment_config() | change
        if change == {"training": None}:
            config.pop("training")
        config_path.write_text(json.dumps(config), encoding="utf-8")
        with pytest.raises(ValueError, match=reason):
            model_trainer.load_deployment_config(config_path)


def test_reference_profiles_preserve_missingness_and_class_scores():
    predictors = pd.DataFrame({"amount": [1.0, np.nan, 3.0], "kind": ["a", None, "b"]})
    config = {"predictive_pipeline": {
        "categorical_predictors": ["kind"],
        "required_predictors": ["amount", "kind"],
    }}
    profiles = model_trainer.build_reference_profiles(
        predictors, np.array([0.1, 0.2, 0.3]), config
    )
    assert profiles["amount"]["type"] == "numeric"
    assert profiles["amount"]["missing_rate"] == pytest.approx(1 / 3)
    assert profiles["kind"]["proportions"] == {"a": 0.5, "b": 0.5}
    assert profiles["__default_probability__"]["rows"] == 3
    assert model_trainer._numeric_profile(pd.Series([None, None]))["proportions"] == [1.0]


def test_training_writes_manifest_from_training_partition_only(monkeypatch, tmp_path):
    monkeypatch.setattr(model_trainer, "PROJECT_ROOT", tmp_path)
    artifact_root = tmp_path / "deployment_artifacts"
    monkeypatch.setattr(model_trainer, "ARTIFACT_ROOT", artifact_root)
    config_path = tmp_path / "deployment_model_config.json"
    config_path.write_text(json.dumps(deployment_config()), encoding="utf-8")
    project = {"predictive_pipeline": {
        "categorical_predictors": [], "required_predictors": ["amount"],
    }}
    training = {"seeds": [42], "review_fraction": 0.2, "threads": 1}
    raw = pd.DataFrame({"amount": [1.0, 2.0, 3.0], "target": [0, 1, 0]})
    calls = []
    monkeypatch.setattr(model_trainer, "load_config", lambda: project)
    monkeypatch.setattr(model_trainer, "load_training_config", lambda: training.copy())
    monkeypatch.setattr(model_trainer, "read_raw_data", lambda config, path, **kwargs: raw)
    monkeypatch.setattr(
        model_trainer, "chronological_train_test_split",
        lambda data, config: SimpleNamespace(train=data.iloc[:2], summary={"train_rows": 2}),
    )
    monkeypatch.setattr(
        model_trainer, "extract_dataset",
        lambda data, config, require_target: SimpleNamespace(
            predictors=data[["amount"]], target=data["target"]
        ),
    )

    def evaluate(data, config, settings, family, parameters, seed, device):
        calls.append((len(data), family, parameters, seed, device))
        return [{"fold": 1, "default_f1": 0.5}], SimpleNamespace(
            raw_score=np.array([0.8, 0.2]), target=np.array([0, 1])
        )

    class Pipeline:
        def fit(self, predictors, target):
            calls.append(("fit", len(predictors)))

    class Selected:
        def __init__(self, pipeline, calibrator, threshold, family):
            self.pipeline = pipeline

        def predict_proba(self, predictors):
            return np.tile([0.7, 0.3], (len(predictors), 1))

    monkeypatch.setattr(model_trainer, "evaluate_candidate", evaluate)
    monkeypatch.setattr(model_trainer, "build_model", lambda *args, **kwargs: Pipeline())
    monkeypatch.setattr(model_trainer, "fit_calibrator", lambda scores, target: object())
    monkeypatch.setattr(model_trainer, "choose_threshold", lambda target, scores: 0.4)
    monkeypatch.setattr(model_trainer, "calibrated_probability", lambda calibrator, scores: scores)
    monkeypatch.setattr(model_trainer, "SelectedCreditModel", Selected)
    monkeypatch.setattr(model_trainer.joblib, "dump", lambda model, path: Path(path).write_bytes(b"model"))
    monkeypatch.setattr(model_trainer, "summarize_classification", lambda *args, **kwargs: {"default_f1": 0.5})
    monkeypatch.setattr(model_trainer, "_source_revision", lambda: "test-revision")

    output = artifact_root / "test-run"
    manifest = model_trainer.train_deployment_artifact(
        output, deployment_config_path=config_path
    )
    assert calls[:2] == [
        (2, "logistic_regression", {"C": 1.0}, 42, "cpu"), ("fit", 2),
    ]
    assert manifest["model_family"] == "logistic_regression"
    assert manifest["training_rows"] == 2
    assert manifest["class_order"] == [0, 1]
    assert manifest["source_revision"] == "test-revision"
    assert (output / "best_model.joblib").read_bytes() == b"model"
    assert json.loads((output / "deployment_manifest.json").read_text())["training_rows"] == 2
    assert "amount" in json.loads((output / "reference_profiles.json").read_text())
    with pytest.raises(FileExistsError, match="must be empty"):
        model_trainer.train_deployment_artifact(output, deployment_config_path=config_path)
