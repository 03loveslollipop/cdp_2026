"""Resumable, budgeted Optuna TPE search over training-period fold scores only."""

from __future__ import annotations

import fcntl
import hashlib
import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

import numpy as np


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def protocol_fingerprint(training_raw, data_config: dict, settings: dict) -> str:
    """Exclude the untouched holdout and mutable trial/time budgets from study identity."""
    search = settings["search"]
    code_hashes = {
        name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in (
            "adaptive_search.py", "ft_engineering.py", "heuristic_model.py",
            "model_training_evaluation.py", "torch_classifier.py",
        )
    }
    training_settings = {
        key: value for key, value in settings.items()
        if key not in {"models", "search", "search_spaces", "smoke_run"}
    }
    payload = {
        "training_data_sha256": hashlib.sha256(
            training_raw.to_csv(index=False).encode("utf-8")
        ).hexdigest(),
        "data_config": data_config,
        "training_settings": training_settings,
        "optimizer": {
            key: value for key, value in search.items()
            if key not in {"n_trials", "timeout_seconds", "study_storage"}
        },
        "search_spaces": {
            name: settings["search_spaces"][name]
            for name in settings["models"] if name in settings["search_spaces"]
        },
        "label_order": [0, 1],
        "objective": "mean_outer_temporal_default_f1_base_seed",
        "code_sha256": code_hashes,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def validate_space(space: dict, family: str) -> None:
    if not space:
        raise ValueError(f"{family}: adaptive search space is empty")
    for name, spec in space.items():
        kind = spec.get("type")
        if kind == "categorical":
            if not isinstance(spec.get("choices"), list) or not spec["choices"]:
                raise ValueError(f"{family}.{name}: categorical choices are required")
        elif kind in {"float", "int"}:
            low, high = spec.get("low"), spec.get("high")
            if not isinstance(low, (float, int)) or not isinstance(high, (float, int)):
                raise ValueError(f"{family}.{name}: numeric bounds are required")
            if not low < high or spec.get("log", False) and low <= 0:
                raise ValueError(f"{family}.{name}: invalid numeric bounds")
            if kind == "int" and not all(isinstance(value, int) for value in (low, high)):
                raise ValueError(f"{family}.{name}: integer bounds are required")
            step = spec.get("step")
            if step is not None and step <= 0:
                raise ValueError(f"{family}.{name}: step must be positive")
            if kind == "float" and spec.get("log", False) and step is not None:
                raise ValueError(f"{family}.{name}: log sampling cannot use a step")
        else:
            raise ValueError(f"{family}.{name}: unsupported adaptive search type")


def suggest_parameters(trial, space: dict) -> dict:
    parameters = {}
    for name, spec in space.items():
        kind = spec["type"]
        if kind == "float":
            value = trial.suggest_float(
                name, spec["low"], spec["high"],
                log=spec.get("log", False), step=spec.get("step"),
            )
        elif kind == "int":
            value = trial.suggest_int(
                name, spec["low"], spec["high"],
                log=spec.get("log", False), step=spec.get("step", 1),
            )
        else:
            value = trial.suggest_categorical(name, spec["choices"])
        parameters[name] = value
    if isinstance(parameters.get("hidden_sizes"), str):
        parameters["hidden_sizes"] = tuple(
            int(width) for width in parameters["hidden_sizes"].split(",")
        )
    return parameters


def _family_seed(seed: int, family: str) -> int:
    digest = hashlib.sha256(f"{seed}:{family}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


@contextmanager
def _exclusive_study_lock(storage_path: Path):
    lock_path = storage_path.with_suffix(storage_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another training process owns this study storage") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _study_storage(storage_path: Path):
    import optuna

    storage = optuna.storages.RDBStorage(
        url=f"sqlite:///{storage_path}", heartbeat_interval=60, grace_period=180
    )
    try:
        yield storage
    finally:
        storage.remove_session()
        storage.engine.dispose()


def _elapsed_seconds(study) -> float:
    finished = sum(
        trial.duration.total_seconds() for trial in study.trials
        if trial.state.is_finished() and trial.duration is not None
    )
    return max(float(study.user_attrs.get("search_elapsed_seconds", 0.0)), finished)


def remaining_budget(study, trial_cap: int, timeout_seconds: float) -> tuple[int, float]:
    elapsed = _elapsed_seconds(study)
    return max(0, trial_cap - len(study.trials)), max(0.0, timeout_seconds - elapsed)


def search_family(
    family: str,
    space: dict,
    objective: Callable[[dict], list[dict]],
    *,
    storage_path: Path,
    fingerprint: str,
    optimizer: dict,
    smoke_parameters: dict | None = None,
) -> tuple[dict, list[dict], dict]:
    """Return the best parameters, every trial, and total study accounting."""
    import optuna
    from optuna.trial import TrialState

    validate_space(space, family)
    trial_cap = int(optimizer["n_trials"])
    timeout_seconds = float(optimizer["timeout_seconds"])
    if trial_cap < 1 or timeout_seconds <= 0 or optimizer["startup_trials"] < 1:
        raise ValueError("Adaptive trial and time budgets must be positive")
    storage_path = Path(storage_path).resolve()
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_study_lock(storage_path), _study_storage(storage_path) as storage:
        study = optuna.create_study(
            study_name=(
                f"cdp_tpe_{family}_{fingerprint[:16]}"
                + ("_smoke" if smoke_parameters is not None else "")
            ),
            direction="maximize",
            sampler=optuna.samplers.TPESampler(
                seed=_family_seed(optimizer["seed"], family),
                n_startup_trials=min(optimizer["startup_trials"], trial_cap),
            ),
            pruner=optuna.pruners.NopPruner(),
            storage=storage,
            load_if_exists=True,
        )
        optuna.storages.fail_stale_trials(study)
        expected = {
            "protocol_fingerprint": fingerprint,
            "family": family,
            "optimizer_seed": optimizer["seed"],
            "smoke_run": smoke_parameters is not None,
        }
        for key, value in expected.items():
            old = study.user_attrs.get(key)
            if old is not None and old != value:
                raise RuntimeError(f"Study has incompatible {key}")
            study.set_user_attr(key, value)
        study.set_user_attr("latest_trial_cap", trial_cap)
        study.set_user_attr("latest_timeout_seconds", timeout_seconds)
        elapsed_before = _elapsed_seconds(study)
        remaining_trials, remaining_time = remaining_budget(
            study, trial_cap, timeout_seconds
        )

        def evaluate(trial):
            try:
                parameters = (
                    dict(smoke_parameters) if smoke_parameters is not None
                    else suggest_parameters(trial, space)
                )
                trial.set_user_attr("resolved_parameters", parameters)
                rows = objective(parameters)
                scores = [float(row["default_f1"]) for row in rows]
                if not scores or not np.isfinite(scores).all():
                    raise ValueError("Temporal F1 scores must be finite and nonempty")
                trial.set_user_attr("fold_default_f1", scores)
                trial.set_user_attr(
                    "fold_fit_seconds", [float(row["fit_seconds"]) for row in rows]
                )
                return float(np.mean(scores))
            except Exception as error:
                trial.set_user_attr("failure_type", type(error).__name__)
                trial.set_user_attr("failure", str(error)[:2000])
                raise

        if remaining_trials and remaining_time > 0:
            started = time.perf_counter()
            try:
                study.optimize(
                    evaluate, n_trials=remaining_trials, timeout=remaining_time,
                    n_jobs=1, catch=(Exception,), gc_after_trial=True,
                )
            finally:
                study.set_user_attr(
                    "search_elapsed_seconds",
                    elapsed_before + (time.perf_counter() - started),
                )
        completed = [
            trial for trial in study.trials
            if trial.state == TrialState.COMPLETE and trial.value is not None
            and np.isfinite(trial.value)
        ]
        if not completed:
            raise RuntimeError(f"{family}: no adaptive trial completed successfully")
        best = max(completed, key=lambda trial: (trial.value, -trial.number))
        trial_rows = [{
            "model": family,
            "candidate": trial.number,
            "state": trial.state.name,
            "mean_f1": trial.value if trial.value is not None else np.nan,
            "parameters": _canonical_json(
                trial.user_attrs.get("resolved_parameters", trial.params)
            ),
            "fold_default_f1": _canonical_json(
                trial.user_attrs.get("fold_default_f1", [])
            ),
            "fold_fit_seconds": _canonical_json(
                trial.user_attrs.get("fold_fit_seconds", [])
            ),
            "duration_seconds": (
                trial.duration.total_seconds() if trial.duration else np.nan
            ),
            "failure_type": trial.user_attrs.get("failure_type"),
            "failure": trial.user_attrs.get("failure"),
        } for trial in study.trials]
        summary = {
            "model": family,
            "method": "tpe",
            "study_name": study.study_name,
            "attempted": len(study.trials),
            "completed": sum(t.state == TrialState.COMPLETE for t in study.trials),
            "pruned": sum(t.state == TrialState.PRUNED for t in study.trials),
            "failed": sum(t.state == TrialState.FAIL for t in study.trials),
            "running": sum(t.state == TrialState.RUNNING for t in study.trials),
            "best_trial": best.number,
            "best_mean_f1": float(best.value),
            "search_elapsed_seconds": _elapsed_seconds(study),
            "trial_cap": trial_cap,
            "timeout_seconds": timeout_seconds,
            "optimizer_seed": optimizer["seed"],
        }
        best_parameters = dict(best.user_attrs["resolved_parameters"])
        if isinstance(best_parameters.get("hidden_sizes"), list):
            best_parameters["hidden_sizes"] = tuple(best_parameters["hidden_sizes"])
        return best_parameters, trial_rows, summary
