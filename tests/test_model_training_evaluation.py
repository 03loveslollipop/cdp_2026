"""Behavioral tests for temporal model selection and deployable estimators."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.base import clone

from etl_scripts.src.ft_engineering import (
    chronological_train_test_split, extract_dataset, load_config, read_raw_data,
)
from etl_scripts.src.model_training_evaluation import (
    DefaultEventBooster, build_model, choose_threshold, load_training_config,
    publish_comparison, select_best_model,
    summarize_classification, temporal_folds, train_and_evaluate,
)
from etl_scripts.src.torch_classifier import TorchCreditClassifier


@pytest.fixture
def raw():
    frame = read_raw_data().iloc[:240].copy().reset_index(drop=True)
    frame["fecha_prestamo"] = pd.date_range(
        "2025-01-01", periods=len(frame), freq="h"
    ).strftime("%d/%m/%Y %H:%M")
    frame["Pago_atiempo"] = np.where(np.arange(len(frame)) % 5 == 0, "0", "1")
    return frame


@pytest.fixture
def settings():
    config = load_training_config()
    config["seeds"] = [42]
    config["models"] = {"logistic_regression": {"C": [0.1]}, "dummy": {}}
    config["benchmark_repeats"] = 1
    return config


def test_metric_semantics_and_threshold():
    target = np.array([0, 0, 1, 1, 1])
    probability = np.array([0.8, 0.4, 0.7, 0.2, 0.1])
    predicted = np.where(probability >= 0.5, 0, 1)
    metrics = summarize_classification(target, predicted, probability)
    assert metrics["confusion_matrix"] == [[1, 1], [1, 2]]
    assert metrics["default_f1"] == pytest.approx(0.5)
    assert metrics["accuracy"] == pytest.approx(0.6)
    assert metrics["recall_at_review_budget"] == pytest.approx(0.5)
    assert choose_threshold(target, probability) == 0.4
    with pytest.raises(ValueError, match="both"):
        summarize_classification([1, 1], [1, 1], [0.1, 0.1])
    with pytest.raises(ValueError, match="Invalid"):
        summarize_classification(target, predicted, [np.nan] * len(target))


@pytest.mark.parametrize("family", list(load_training_config()["models"]))
def test_factory_fit_clone_and_unknown_categories(family, raw):
    if family == "pytorch_mlp":
        pytest.importorskip("torch")
    if family in ("xgboost", "lightgbm"):
        pytest.importorskip(family)
    params = {"epochs": 2} if family == "pytorch_mlp" else {}
    if family in ("random_forest", "extra_trees", "xgboost", "lightgbm"):
        params["n_estimators"] = 5
    model = clone(build_model(family, parameters=params))
    dataset = extract_dataset(raw, require_target=True)
    model.fit(dataset.predictors, dataset.target)
    fresh = raw.iloc[:5].drop(columns="Pago_atiempo").copy()
    fresh["tipo_credito"] = "99999"
    if family == "svm":
        assert np.isfinite(model.decision_function(fresh)).all()
    else:
        probabilities = model.predict_proba(fresh)
        assert probabilities.shape == (5, 2)
        np.testing.assert_allclose(probabilities.sum(axis=1), 1, atol=1e-6)
        assert (probabilities >= 0).all()
    assert model.classes_.tolist() == [0, 1]
    assert model.predict(fresh).shape == (5,)
    if family != "heuristic":
        names = model.named_steps["prepare"].get_feature_names_out()
        assert "puntaje" not in names and "Pago_atiempo" not in names


def test_torch_direction_serialization_and_reproducibility(tmp_path):
    pytest.importorskip("torch")
    X = np.tile([[-2.0], [-1.0], [1.0], [2.0]], (20, 1))
    y = np.tile([1, 1, 0, 0], 20)
    estimator = TorchCreditClassifier(
        hidden_sizes=(8, 4), epochs=60, learning_rate=0.03, dropout=0,
    )
    model = clone(estimator).fit(X, y)
    probabilities = model.predict_proba([[-2], [2]])
    assert probabilities[1, 0] > probabilities[0, 0]
    assert model.predict([[-2], [2]]).tolist() == [1, 0]
    another = clone(estimator).fit(X, y)
    np.testing.assert_allclose(another.predict_proba(X), model.predict_proba(X))
    # Simulate an artifact trained on CUDA: no tensors or GPU context are persisted.
    model.device = "cuda"
    artifact = tmp_path / "nn.joblib"
    joblib.dump(model, artifact)
    np.testing.assert_allclose(joblib.load(artifact).predict_proba(X),
                               model.predict_proba(X))
    with pytest.raises(ValueError, match="both"):
        clone(estimator).fit(X, np.ones(len(X)))


def test_temporal_folds_preserve_groups_and_fail_single_class(raw):
    raw.loc[raw.index[1::2], "fecha_prestamo"] = (
        raw.loc[raw.index[::2], "fecha_prestamo"].to_numpy()
    )
    for train, valid in temporal_folds(raw, load_config()):
        train_dates = pd.to_datetime(train.fecha_prestamo, dayfirst=True)
        valid_dates = pd.to_datetime(valid.fecha_prestamo, dayfirst=True)
        assert train_dates.max() < valid_dates.min()
        assert set(train.index).isdisjoint(valid.index)
    raw["Pago_atiempo"] = "1"
    with pytest.raises(ValueError, match="both"):
        list(temporal_folds(raw, load_config()))


def test_selection_tolerance_and_tiebreaks():
    frame = pd.DataFrame([
        ["highest", 0.20, 0.08, 0.02, 5, 100],
        ["stable", 0.195, 0.01, 0.01, 6, 200],
        ["outside", 0.18, 0, 0, 1, 10],
        ["dummy", 0.99, 0, 0, 0, 0],
    ], columns=["model", "mean_f1", "temporal_f1_std", "seed_f1_std",
                "cpu_batch_ms", "artifact_bytes"])
    assert select_best_model(frame) == "stable"
    assert select_best_model(frame, tolerance=0) == "highest"
    frame.loc[0, ["mean_f1", "temporal_f1_std", "seed_f1_std"]] = [0.195, 0.01, 0.01]
    assert select_best_model(frame) == "highest"
    frame.loc[0, "cpu_batch_ms"] = 6
    assert select_best_model(frame) == "highest"  # Smaller artifact.


@pytest.mark.parametrize("family", ["xgboost", "lightgbm"])
def test_boosting_positive_weight_and_probability_mapping(family):
    pytest.importorskip(family)
    X = np.concatenate([np.full((20, 1), -1.0), np.full((80, 1), 1.0)])
    y = np.concatenate([np.zeros(20), np.ones(80)])
    model = DefaultEventBooster(family=family, balanced=True,
                                parameters={"n_estimators": 10}).fit(X, y)
    assert model.estimator_.get_params()["scale_pos_weight"] == 4
    probabilities = model.predict_proba(np.array([[-1.0], [1.0]]))
    assert probabilities[0, 0] > probabilities[1, 0]
    assert model.predict(np.array([[-1.0], [1.0]])).tolist() == [0, 1]


def test_holdout_cannot_change_training_selection_or_artifact(raw, settings, tmp_path):
    first = train_and_evaluate(raw, output_dir=tmp_path / "first",
                               training_config=settings)
    changed = raw.copy()
    split = chronological_train_test_split(changed)
    changed.loc[split.test.index, "Pago_atiempo"] = (
        1 - changed.loc[split.test.index, "Pago_atiempo"].astype(int)
    ).astype(str)
    changed.loc[split.test.index, "salario_cliente"] = "999999999999"
    second = train_and_evaluate(changed, output_dir=tmp_path / "second",
                                training_config=settings)
    assert first.best_model.model_name == second.best_model.model_name
    assert first.best_model.threshold == second.best_model.threshold
    np.testing.assert_allclose(first.best_model.predict_proba(raw),
                               second.best_model.predict_proba(raw))
    assert Path(first.artifact_paths["model"]).read_bytes() == (
        Path(second.artifact_paths["model"]).read_bytes()
    )
    # Leakage and metadata are ignored at inference, target is not required.
    augmented = raw.drop(columns="Pago_atiempo").assign(
        puntaje="100000", fecha_prestamo="invalid", outcome_copy="0"
    )
    np.testing.assert_allclose(first.best_model.predict_proba(raw),
                               first.best_model.predict_proba(augmented))
    restored = joblib.load(first.artifact_paths["model"])
    np.testing.assert_allclose(restored.predict_proba(raw),
                               first.best_model.predict_proba(raw))
    assert json.loads(Path(first.artifact_paths["manifest"]).read_text())["folds"]
    assert all(Path(path).exists() for path in first.artifact_paths.values())
    published = publish_comparison(tmp_path / "first", tmp_path / "published")
    assert "logistic_regression" in published.read_text()
    assert not list(published.parent.rglob("*.csv"))
    assert not list(published.parent.rglob("*.joblib"))
    with pytest.raises(FileExistsError):
        train_and_evaluate(raw, output_dir=tmp_path / "first",
                           training_config=settings)


def test_inner_preparation_is_fitted_before_calibration_and_validation(
    raw, settings, monkeypatch,
):
    import etl_scripts.src.model_training_evaluation as training

    original = training.build_model
    observed = []

    def recording_factory(*args, **kwargs):
        pipeline = original(*args, **kwargs)
        original_fit = pipeline.fit

        def fit(X, y, **fit_params):
            observed.append(X.index.tolist())
            return original_fit(X, y, **fit_params)

        pipeline.fit = fit
        return pipeline

    monkeypatch.setattr(training, "build_model", recording_factory)
    training.evaluate_candidate(raw, load_config(), settings,
                                "logistic_regression", {}, 42, "cpu")
    for actual, (train, valid) in zip(observed, temporal_folds(raw, load_config())):
        inner = chronological_train_test_split(train, train_fraction=0.8)
        assert actual == inner.train.index.tolist()
        assert set(actual).isdisjoint(valid.index)
        assert set(actual).isdisjoint(inner.test.index)


def test_cli_artifact_loads_in_separate_process(raw, settings, tmp_path):
    raw.to_csv(tmp_path / "input.csv", sep=";", index=False)
    (tmp_path / "config.json").write_text(json.dumps(settings))
    output = tmp_path / "cli"
    subprocess.run([
        sys.executable, "-m", "etl_scripts.src.model_training_evaluation",
        "--input", str(tmp_path / "input.csv"),
        "--training-config", str(tmp_path / "config.json"),
        "--output-dir", str(output),
    ], check=True, capture_output=True, text=True)
    loaded = joblib.load(output / "best_model.joblib")
    assert loaded.predict(raw).shape == (len(raw),)


def test_invalid_family_and_configuration(raw, settings, tmp_path):
    with pytest.raises(ValueError, match="Unknown"):
        build_model("regression")
    invalid = copy.deepcopy(settings)
    invalid["models"] = {"logistic_regression": {"C": list(range(9))}}
    with pytest.raises(ValueError, match="eight"):
        train_and_evaluate(raw, output_dir=tmp_path, training_config=invalid)


def test_failed_run_records_status(raw, settings, tmp_path):
    raw["Pago_atiempo"] = "1"
    with pytest.raises(ValueError, match="both"):
        train_and_evaluate(raw, output_dir=tmp_path, training_config=settings)
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["state"] == "failed"
    assert status["error_type"] == "ValueError"
    assert not (tmp_path / "best_model.joblib").exists()


def test_cuda_training_portability():
    torch = pytest.importorskip("torch")

    if not torch.cuda.is_available():
        pytest.skip("CUDA GPU unavailable")
    X = np.tile([[-1.0], [1.0]], (20, 1))
    y = np.tile([0, 1], 20)
    model = TorchCreditClassifier(epochs=2, device="cuda").fit(X, y)
    assert model.training_device_ == "cuda"
    assert all(isinstance(value, np.ndarray) for value in model.weights_.values())
    assert model.predict_proba(X).shape == (len(X), 2)
