"""Adaptive search respects fold-only objectives, budgets, and study identity."""

from __future__ import annotations

import json

import optuna
import pandas as pd
import pytest

from etl_scripts.src import adaptive_search
from etl_scripts.src.ft_engineering import (
    chronological_train_test_split, load_config, read_raw_data,
)
from etl_scripts.src.model_training_evaluation import (
    load_training_config, train_and_evaluate,
)


OPTIMIZER = {"seed": 123, "n_trials": 2, "timeout_seconds": 60, "startup_trials": 1}
SPACE = {"C": {"type": "float", "low": 0.01, "high": 10.0, "log": True}}


def test_training_fingerprint_ignores_holdout_changes():
    raw = read_raw_data()
    config = load_config()
    settings = load_training_config()
    settings["search"]["method"] = "tpe"
    settings["models"] = {"logistic_regression": {"C": [1.0]}, "dummy": {}}
    split = chronological_train_test_split(raw, config)
    first = adaptive_search.protocol_fingerprint(split.train, config, settings)
    changed = raw.copy()
    changed.loc[split.test.index, "Pago_atiempo"] = "0"
    changed.loc[split.test.index, "salario_cliente"] = "999999999999"
    second_split = chronological_train_test_split(changed, config)
    second = adaptive_search.protocol_fingerprint(second_split.train, config, settings)
    assert first == second
    settings["search"]["n_trials"] += 10
    assert adaptive_search.protocol_fingerprint(split.train, config, settings) == first
    settings["search_spaces"]["logistic_regression"]["C"]["high"] = 20
    assert adaptive_search.protocol_fingerprint(split.train, config, settings) != first


def test_parameter_sampling_is_reproducible_and_resolves_mlp_widths():
    space = {
        "hidden_sizes": {"type": "categorical", "choices": ["32,16", "64,32"]},
        **SPACE,
    }

    def sample():
        study = optuna.create_study(
            direction="maximize", sampler=optuna.samplers.TPESampler(seed=42)
        )
        parameters = []
        for index in range(4):
            trial = study.ask()
            parameters.append(adaptive_search.suggest_parameters(trial, space))
            study.tell(trial, float(index))
        return parameters

    first_sample = sample()
    second_sample = sample()
    assert first_sample == second_sample
    assert all(isinstance(item["hidden_sizes"], tuple) for item in sample())


def test_invalid_spaces_and_budget_accounting():
    for space in (
        {}, {"C": {"type": "float", "low": -1, "high": 1, "log": True}},
        {"C": {"type": "categorical", "choices": []}},
        {"C": {"type": "int", "low": 3, "high": 2}},
    ):
        with pytest.raises(ValueError):
            adaptive_search.validate_space(space, "logistic_regression")
    study = optuna.create_study(direction="maximize")
    for score in (0.1, 0.2):
        trial = study.ask()
        study.tell(trial, score)
    study.set_user_attr("search_elapsed_seconds", 7.5)
    assert adaptive_search.remaining_budget(study, 3, 10) == (1, 2.5)
    assert adaptive_search.remaining_budget(study, 2, 5) == (0, 0.0)


def test_failed_trials_are_recorded_and_resume_uses_total_cap(tmp_path):
    attempts = []

    def objective(parameters):
        attempts.append(parameters)
        if len(attempts) == 1:
            raise RuntimeError("deliberate fold failure")
        return [
            {"default_f1": 0.2, "fit_seconds": 0.01},
            {"default_f1": 0.4, "fit_seconds": 0.02},
        ]

    kwargs = {
        "storage_path": tmp_path / "study.sqlite3",
        "fingerprint": "a" * 64,
        "optimizer": OPTIMIZER,
    }
    parameters, trials, summary = adaptive_search.search_family(
        "logistic_regression", SPACE, objective, **kwargs
    )
    assert parameters["C"] > 0
    assert summary["attempted"] == 2
    assert summary["completed"] == 1
    assert summary["failed"] == 1
    assert summary["pruned"] == 0
    assert summary["trial_cap"] == 2
    assert "deliberate fold failure" in trials[0]["failure"]
    assert json.loads(trials[1]["fold_default_f1"]) == [0.2, 0.4]
    assert adaptive_search.search_family(
        "logistic_regression", SPACE, objective, **kwargs
    )[2]["attempted"] == 2
    assert len(attempts) == 2
    _, _, time_limited = adaptive_search.search_family(
        "logistic_regression", SPACE, objective,
        **{**kwargs, "optimizer": {**OPTIMIZER, "n_trials": 3,
                                "timeout_seconds": 0.001}},
    )
    assert time_limited["attempted"] == 2
    assert len(attempts) == 2
    with pytest.raises(RuntimeError, match="incompatible protocol_fingerprint"):
        adaptive_search.search_family(
            "logistic_regression", SPACE, objective,
            **{**kwargs, "fingerprint": "a" * 16 + "b" * 48},
        )


def test_all_failed_trials_fail_family_without_fake_winner(tmp_path):
    def objective(parameters):
        raise ValueError("invalid trial")

    with pytest.raises(RuntimeError, match="no adaptive trial completed"):
        adaptive_search.search_family(
            "logistic_regression", SPACE, objective,
            storage_path=tmp_path / "failed.sqlite3", fingerprint="f" * 64,
            optimizer={**OPTIMIZER, "n_trials": 1},
        )


def test_training_pipeline_uses_tpe_before_frozen_holdout(tmp_path):
    raw = read_raw_data().iloc[:240].copy().reset_index(drop=True)
    raw["fecha_prestamo"] = pd.date_range(
        "2025-01-01", periods=len(raw), freq="h"
    ).strftime("%d/%m/%Y %H:%M")
    raw["Pago_atiempo"] = ["0" if index % 5 == 0 else "1" for index in range(len(raw))]
    settings = load_training_config()
    settings["seeds"] = [42]
    settings["models"] = {"logistic_regression": {"C": [1.0]}, "dummy": {}}
    settings["benchmark_repeats"] = 1
    settings["search"].update({
        "method": "tpe", "n_trials": 1, "timeout_seconds": 60,
        "startup_trials": 1, "study_storage": str(tmp_path / "studies.sqlite3"),
    })
    result = train_and_evaluate(
        raw, output_dir=tmp_path / "run", training_config=settings
    )
    manifest = json.loads((tmp_path / "run" / "manifest.json").read_text())
    selection = json.loads((tmp_path / "run" / "selection.json").read_text())
    assert result.best_model.classes_.tolist() == [0, 1]
    assert manifest["search"][0]["attempted"] == 1
    assert manifest["protocol_fingerprint"] == selection["protocol_fingerprint"]
    assert (tmp_path / "run" / "search.csv").exists()
    assert manifest["search"][0]["search_elapsed_seconds"] > 0
