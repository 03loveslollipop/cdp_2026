"""Temporal training, threshold selection, evaluation, and portable model export.

Run with ``python -m mlops_pipeline.src.model_training_evaluation`` from the repo root.
Default (Pago_atiempo=0) is the operational positive class throughout reporting.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import platform
import time
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.special import logit
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, average_precision_score, confusion_matrix, f1_score,
    precision_recall_curve, precision_score, recall_score, roc_auc_score, roc_curve,
)
from sklearn.model_selection import ParameterGrid
from sklearn.naive_bayes import GaussianNB
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier
from sklearn.utils.validation import check_is_fitted
from threadpoolctl import threadpool_limits

from .ft_engineering import (
    build_data_preparation_pipeline, chronological_train_test_split,
    extract_dataset, load_config, read_raw_data,
)
from .heuristic_model import CreditRiskHeuristicClassifier
from .torch_classifier import TorchCreditClassifier


TRAINING_CONFIG_PATH = Path(__file__).with_name("model_training_config.json")
REFERENCE_MODELS = {"heuristic", "dummy"}


def load_training_config(path=TRAINING_CONFIG_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def numeric_columns(frame):
    """Exclude configured categorical fields even if their raw dtype is numeric."""
    return [name for name in frame if name not in categorical_columns(frame)]


def categorical_columns(frame):
    return [name for name in frame if name in (
        "tipo_credito", "tipo_laboral", "tendencia_ingresos"
    )]


class DefaultEventBooster(ClassifierMixin, BaseEstimator):
    """Translate original labels to positive-default boosting objectives."""

    def __init__(self, family="xgboost", balanced=False, parameters=None,
                 random_state=42, device="cpu", threads=2):
        self.family = family
        self.balanced = balanced
        self.parameters = parameters
        self.random_state = random_state
        self.device = device
        self.threads = threads

    def fit(self, X, y):
        if self.device != "cpu":
            raise ValueError("Tracked model training supports CPU only")
        y = np.asarray(y)
        require_both_classes(y, "boosting training")
        parameters = dict(self.parameters or {})
        parameters.update(random_state=self.random_state, n_jobs=self.threads)
        parameters["scale_pos_weight"] = (
            float((y == 1).sum() / (y == 0).sum()) if self.balanced else 1.0
        )
        if self.family == "xgboost":
            from xgboost import XGBClassifier

            self.estimator_ = XGBClassifier(
                tree_method="hist", device="cpu",
                eval_metric="logloss", **parameters,
            )
        elif self.family == "lightgbm":
            from lightgbm import LGBMClassifier

            self.estimator_ = LGBMClassifier(
                device_type="cpu", verbosity=-1, **parameters,
            )
        else:
            raise ValueError(f"Unknown booster: {self.family}")
        self.estimator_.fit(X, 1 - y)
        self.training_device_ = "cpu"
        self.classes_ = np.array([0, 1])
        self.n_features_in_ = X.shape[1]
        return self

    def predict_proba(self, X):
        check_is_fitted(self, "estimator_")
        return self.estimator_.predict_proba(X)[:, ::-1]

    def predict(self, X):
        return self.classes_[np.argmax(self.predict_proba(X), axis=1)]


def build_model(model_name, config=None, random_state=42, device="cpu", *,
                parameters=None, training_config=None):
    """Return an unfitted raw-record sklearn Pipeline for a model family."""
    if device != "cpu":
        raise ValueError("Tracked model training supports CPU only")
    cfg = config or load_config()
    settings = training_config or load_training_config()
    params = dict(parameters or {})
    threads = settings["threads"]
    constructors = {
        "logistic_regression": lambda: LogisticRegression(
            max_iter=2000, random_state=random_state, **params),
        "decision_tree": lambda: DecisionTreeClassifier(
            random_state=random_state, **params),
        "gaussian_nb": lambda: GaussianNB(**params),
        "random_forest": lambda: RandomForestClassifier(
            random_state=random_state, n_jobs=threads, **params),
        "extra_trees": lambda: ExtraTreesClassifier(
            random_state=random_state, n_jobs=threads, **params),
        # Explicit temporal sigmoid calibration below; no internal shuffled CV.
        "svm": lambda: SVC(kernel="rbf", **params),
        "pytorch_mlp": lambda: TorchCreditClassifier(
            random_state=random_state, device=device, **params),
        "heuristic": lambda: CreditRiskHeuristicClassifier(**params),
        "dummy": lambda: DummyClassifier(strategy="constant", constant=1),
    }
    if model_name in ("xgboost", "lightgbm"):
        balanced = params.pop("balanced", False)
        model = DefaultEventBooster(
            family=model_name, balanced=balanced, parameters=params,
            random_state=random_state, threads=threads,
            device="cpu",
        )
    elif model_name in constructors:
        model = constructors[model_name]()
    else:
        raise ValueError(f"Unknown model family: {model_name}")
    steps = [("prepare", build_data_preparation_pipeline(cfg))]
    if model_name != "heuristic":
        scale = model_name in {
            "logistic_regression", "svm", "gaussian_nb", "pytorch_mlp"
        }
        # Dense arrays are modest for this dataset and work with every estimator.
        encoding = ColumnTransformer([
            ("numeric", StandardScaler() if scale else "passthrough",
             numeric_columns),
            ("categorical", OneHotEncoder(handle_unknown="ignore",
                                          sparse_output=False),
             categorical_columns),
        ], sparse_threshold=0)
        steps.append(("encode", encoding))
    steps.append(("classifier", model))
    return Pipeline(steps)


def require_both_classes(y, context):
    if not np.array_equal(np.unique(y), [0, 1]):
        raise ValueError(f"{context} requires both Pago_atiempo classes [0, 1]")


def default_scores(model, X):
    """Continuous default-oriented score for temporal sigmoid calibration."""
    if hasattr(model, "decision_function"):
        return -np.asarray(model.decision_function(X), dtype=float)
    classes = list(model.classes_)
    probability = model.predict_proba(X)[:, classes.index(0)]
    return logit(np.clip(probability, 1e-7, 1 - 1e-7))


def fit_calibrator(scores, y):
    require_both_classes(y, "probability calibration")
    return LogisticRegression(C=1.0, max_iter=1000).fit(
        np.asarray(scores).reshape(-1, 1), (np.asarray(y) == 0).astype(int)
    )


def calibrated_probability(calibrator, scores):
    return calibrator.predict_proba(np.asarray(scores).reshape(-1, 1))[:, 1]


def choose_threshold(y, probability):
    """Maximize default F1; ties prefer the higher (smaller-queue) threshold."""
    require_both_classes(y, "threshold tuning")
    precision, recall, thresholds = precision_recall_curve(
        np.asarray(y) == 0, probability
    )
    f1 = np.divide(2 * precision[:-1] * recall[:-1],
                   precision[:-1] + recall[:-1],
                   out=np.zeros(len(thresholds)),
                   where=(precision[:-1] + recall[:-1]) > 0)
    return float(thresholds[np.flatnonzero(f1 == f1.max())[-1]])


class SelectedCreditModel(ClassifierMixin, BaseEstimator):
    """Fitted raw-record prediction object with frozen temporal calibration."""

    def __init__(self, pipeline, calibrator, threshold, model_name):
        self.pipeline = pipeline
        self.calibrator = calibrator
        self.threshold = threshold
        self.model_name = model_name
        self.classes_ = np.array([0, 1])

    def predict_proba(self, X):
        probability = calibrated_probability(
            self.calibrator, default_scores(self.pipeline, X)
        )
        return np.column_stack([probability, 1 - probability])

    def predict(self, X):
        return np.where(self.predict_proba(X)[:, 0] >= self.threshold, 0, 1)


def summarize_classification(y_true, y_pred, default_probability, *,
                             review_fraction=0.2):
    """Return JSON-compatible metrics; matrix order is actual/predicted [0, 1]."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    probability = np.asarray(default_probability, dtype=float)
    require_both_classes(y_true, "classification evaluation")
    if (y_true.shape != y_pred.shape or y_true.shape != probability.shape
            or not np.isin(y_pred, [0, 1]).all()
            or not np.isfinite(probability).all()
            or ((probability < 0) | (probability > 1)).any()
            or not 0 < review_fraction <= 1):
        raise ValueError("Invalid predictions, probabilities, or review fraction")
    event = y_true == 0
    count = max(1, int(np.ceil(len(y_true) * review_fraction)))
    top = np.argsort(-probability, kind="stable")[:count]
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "default_precision": float(precision_score(
            y_true, y_pred, pos_label=0, zero_division=0)),
        "default_recall": float(recall_score(y_true, y_pred, pos_label=0)),
        "default_f1": float(f1_score(y_true, y_pred, pos_label=0)),
        "average_precision": float(average_precision_score(event, probability)),
        "roc_auc": float(roc_auc_score(event, probability)),
        "recall_at_review_budget": float(event[top].sum() / event.sum()),
        "review_budget_rows": count,
        "predicted_default_fraction": float((y_pred == 0).mean()),
        "default_prevalence": float(event.mean()),
        "rows": len(y_true),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
    }


def temporal_folds(raw, config, blocks=5):
    """Expanding folds partition unique timestamps, never individual ties."""
    column = config["predictive_pipeline"]["train_test_split"]["timestamp_column"]
    dates = pd.to_datetime(raw[column], dayfirst=config["read_csv"]["date_dayfirst"])
    if dates.isna().any() or blocks < 4:
        raise ValueError("Valid timestamps and at least four temporal blocks required")
    groups = np.sort(dates.unique())
    if len(groups) < blocks:
        raise ValueError("Not enough distinct timestamps for temporal folds")
    chunks = np.array_split(groups, blocks)
    for index in range(2, blocks):
        train = raw.loc[dates < chunks[index][0]]
        valid = raw.loc[dates.isin(chunks[index])]
        for name, frame in (("fold training", train), ("fold validation", valid)):
            require_both_classes(
                extract_dataset(frame, config, require_target=True).target, name
            )
        yield train, valid


def evaluate_candidate(raw, config, settings, name, parameters, seed, device):
    rows, predictions = [], []
    for fold, (train, valid) in enumerate(temporal_folds(
        raw, config, settings["temporal_blocks"]
    )):
        # Earlier fit rows -> later calibration rows -> untouched outer validation.
        inner = chronological_train_test_split(
            train, config, train_fraction=settings["inner_train_fraction"]
        )
        fit_data = extract_dataset(inner.train, config, require_target=True)
        calibration = extract_dataset(inner.test, config, require_target=True)
        evaluation = extract_dataset(valid, config, require_target=True)
        for label, data in (
            ("inner fit", fit_data), ("inner calibration", calibration)
        ):
            require_both_classes(data.target, label)
        model = build_model(name, config, seed, device, parameters=parameters,
                            training_config=settings)
        start = time.perf_counter()
        model.fit(fit_data.predictors, fit_data.target)
        calibrator = fit_calibrator(
            default_scores(model, calibration.predictors), calibration.target
        )
        threshold = choose_threshold(
            calibration.target, calibrated_probability(
                calibrator, default_scores(model, calibration.predictors)
            )
        )
        elapsed = time.perf_counter() - start
        score = default_scores(model, evaluation.predictors)
        probability = calibrated_probability(calibrator, score)
        if name in REFERENCE_MODELS:
            # Preserve the original heuristic operating point and dummy behavior.
            predicted = model.predict(evaluation.predictors)
            probability = model.predict_proba(evaluation.predictors)[:, 0]
        else:
            predicted = np.where(probability >= threshold, 0, 1)
        metrics = summarize_classification(
            evaluation.target, predicted, probability,
            review_fraction=settings["review_fraction"],
        )
        rows.append(dict(model=name, seed=seed, fold=fold,
                         threshold=threshold if name not in REFERENCE_MODELS else None,
                         train_rows=len(inner.train), calibration_rows=len(inner.test),
                         fit_seconds=elapsed, **metrics))
        predictions.append(pd.DataFrame({
            "row_id": valid.index, "fold": fold, "seed": seed,
            "target": evaluation.target.to_numpy(), "raw_score": score,
            "default_probability": probability, "prediction": predicted,
        }))
    return rows, pd.concat(predictions, ignore_index=True)


def select_best_model(summary, tolerance=0.01):
    eligible = summary.loc[~summary.model.isin(REFERENCE_MODELS)].copy()
    if eligible.empty or not np.isfinite(eligible.mean_f1).all():
        raise ValueError("Selection requires finite results for a learned model")
    eligible = eligible.loc[eligible.mean_f1 >= eligible.mean_f1.max() - tolerance]
    return eligible.sort_values([
        "temporal_f1_std", "seed_f1_std", "cpu_batch_ms", "artifact_bytes", "model"
    ], kind="stable").iloc[0]["model"]


def benchmark_model(model, X, settings):
    batch = X.iloc[:settings["benchmark_batch_size"]]
    with threadpool_limits(limits=settings["threads"]):
        model.predict_proba(batch)
        timings = []
        for _ in range(settings["benchmark_repeats"]):
            start = time.perf_counter()
            model.predict_proba(batch)
            timings.append(1000 * (time.perf_counter() - start))
    buffer = io.BytesIO()
    joblib.dump(model, buffer)
    return float(np.median(timings)), buffer.tell()


@dataclass
class TrainingResult:
    best_model: SelectedCreditModel
    comparison: pd.DataFrame
    holdout: pd.DataFrame
    artifact_paths: dict[str, str]


def _json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def _markdown(frame):
    """Small dependency-free Markdown table exporter."""
    def cell(value):
        return f"{value:.4f}" if isinstance(value, float) else str(value)

    return "\n".join([
        "| " + " | ".join(frame.columns) + " |",
        "| " + " | ".join(["---"] * len(frame.columns)) + " |",
        *("| " + " | ".join(cell(v) for v in row) + " |"
          for row in frame.itertuples(index=False, name=None)),
    ])


def publish_comparison(run_dir, destination):
    """Publish aggregate tables/graphs from a completed run, without record data."""
    source, target = Path(run_dir), Path(destination)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    status = json.loads((source / "status.json").read_text(encoding="utf-8"))
    if status["state"] != "complete":
        raise ValueError("Only a completed run can be published")
    summary = pd.read_csv(source / "validation_summary.csv")
    holdout = pd.read_csv(source / "holdout_summary.csv")
    holdout["confusion_matrix"] = holdout.confusion_matrix.map(json.loads)
    folds = pd.read_csv(source / "validation_folds.csv")
    predictions = pd.read_csv(source / "holdout_predictions.csv")
    graphs = write_comparison_graphs(target / "figures", folds, summary,
                                      predictions, holdout)
    selection = json.loads((source / "selection.json").read_text(encoding="utf-8"))
    content = (
        "# Model comparison benchmark\n\n"
        f"Selected by temporal validation: **{manifest['selection']}**. "
        "Default is `Pago_atiempo=0`. The newest 30% is evaluated after selection.\n\n"
        f"Training device: `{manifest['requested_device']}`; Python "
        f"`{manifest['python']}`. Tracked training and inference are CPU-only.\n\n"
        "## Temporal validation\n\n"
        + _markdown(summary[[
            "model", "mean_f1", "temporal_f1_std", "seed_f1_std",
            "cpu_batch_ms", "artifact_bytes",
        ] + (["search_seconds", "finalization_seconds"]
             if "search_seconds" in summary else [])])
        + "\n\nWithin 0.01 F1 of the leader, prefer lower temporal variation, "
        "then seed variation, CPU latency, and artifact size. Heuristic/dummy "
        "are references and retain their original prediction rules.\n\n"
        "## Frozen holdout\n\n"
        + _markdown(holdout[[
            "model", "accuracy", "default_precision", "default_recall",
            "default_f1", "average_precision", "roc_auc",
            "recall_at_review_budget",
        ]])
        + "\n\n## Selected configuration\n\n```json\n"
        + json.dumps(selection, indent=2) + "\n```\n\n"
        "## Comparative graphs\n\n"
        + "\n\n".join(
            f"![{Path(path).stem.replace('_', ' ')}](figures/{Path(path).name})"
            for path in graphs
        )
        + "\n\n## Reproducibility and limits\n\n"
        f"Dataset SHA-256: `{manifest['dataset_sha256']}`. "
        f"Seeds: `{manifest['training_configuration']['seeds']}`. "
        f"Platform: `{manifest['platform']}`.\n\n"
        + _markdown(pd.DataFrame(manifest["packages"].items(),
                                  columns=["Package", "Version"]))
        + "\n\nThe holdout was previously examined during EDA and baseline work; "
        "it is not a fresh external validation set. Feature availability at "
        "decision time and outcome maturity remain assumptions. CPU timings "
        "include preparation and are local measurements, not deployment SLAs. "
        "See [workflow documentation](../model_training.md) for the protocol, "
        "configuration, and regeneration commands.\n"
    )
    (target / "README.md").write_text(content, encoding="utf-8")
    return target / "README.md"


def write_comparison_graphs(output, folds, summary, predictions, holdout):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for metric in ("pr", "roc"):
        fig, ax = plt.subplots(figsize=(9, 6))
        for name, data in predictions.groupby("model", sort=True):
            event = data.target.to_numpy() == 0
            probability = data.default_probability.to_numpy()
            if metric == "pr":
                precision, recall, _ = precision_recall_curve(event, probability)
                ax.plot(recall, precision, label=name)
            else:
                fpr, tpr, _ = roc_curve(event, probability)
                ax.plot(fpr, tpr, label=name)
        if metric == "pr":
            ax.axhline(event.mean(), color="gray", linestyle="--", label="prevalence")
        else:
            ax.plot([0, 1], [0, 1], "k--", linewidth=0.7)
        ax.set(xlabel="Recall" if metric == "pr" else "False positive rate",
               ylabel="Precision" if metric == "pr" else "True positive rate",
               title="Holdout default-class " + ("precision–recall" if metric == "pr"
                                                else "ROC"))
        ax.legend(fontsize=8, loc="best")
        fig.tight_layout()
        path = output / f"holdout_{metric}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(str(path))
    fig, ax = plt.subplots(figsize=(9, 6))
    for name, data in folds.groupby("model", sort=True):
        grouped = data.groupby("fold").default_f1
        ax.errorbar(grouped.mean().index + 1, grouped.mean(),
                    yerr=grouped.std().fillna(0), marker="o", label=name)
    ax.set(xlabel="Forward validation fold", ylabel="Default F1",
           title="Temporal consistency (error bars: seed standard deviation)",
           xticks=sorted(folds.fold.unique() + 1))
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = output / "temporal_f1.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(str(path))
    fig, ax = plt.subplots(figsize=(9, 6))
    for row in summary.itertuples():
        ax.scatter(row.cpu_batch_ms, row.mean_f1)
        ax.annotate(row.model, (row.cpu_batch_ms, row.mean_f1), fontsize=8,
                    xytext=(4, 5), textcoords="offset points")
    ax.margins(x=0.25, y=0.12)
    ax.set(xscale="log", xlabel="CPU batch inference (ms, including preparation)",
           ylabel="Mean temporal default F1", title="Performance and inference cost")
    fig.tight_layout()
    path = output / "f1_inference_cost.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(str(path))
    if "search_seconds" in summary:
        fig, ax = plt.subplots(figsize=(9, 6))
        ordered = summary.sort_values("search_seconds")
        ax.barh(ordered.model, ordered.search_seconds)
        ax.set(xlabel="Search elapsed seconds", title="Per-family search cost")
        fig.tight_layout()
        path = output / "search_cost.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(str(path))
    columns = 3
    rows = int(np.ceil(len(holdout) / columns))
    fig, axes = plt.subplots(rows, columns, figsize=(12, rows * 3.5), squeeze=False)
    for ax, row in zip(axes.flat, holdout.itertuples()):
        matrix = np.asarray(row.confusion_matrix)
        ax.imshow(matrix, cmap="Blues")
        for (i, j), value in np.ndenumerate(matrix):
            ax.text(j, i, str(value), ha="center", va="center", color="darkred")
        ax.set(title=row.model, xlabel="Predicted", ylabel="Actual",
               xticks=[0, 1], yticks=[0, 1],
               xticklabels=["Default", "On time"], yticklabels=["Default", "On time"])
    for ax in list(axes.flat)[len(holdout):]:
        ax.set_visible(False)
    fig.suptitle("Holdout confusion matrices; thresholds frozen before evaluation")
    fig.tight_layout()
    path = output / "holdout_confusion_matrices.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(str(path))
    return paths


def train_and_evaluate(raw_data, config=None, output_dir="runs/model_comparison", *,
                       training_config=None, device=None):
    """Return the fitted winner and reports; protect prior runs and record failures."""
    settings = copy.deepcopy(training_config or load_training_config())
    resolved_device = device or settings["device"]
    _validate_settings(settings, resolved_device)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Use a new output directory; run artifacts already exist")
    output.mkdir(parents=True, exist_ok=True)
    _json(output / "status.json", {"state": "running", "device": resolved_device})
    try:
        return _train_and_evaluate(
            raw_data, config, output, training_config=settings, device=resolved_device
        )
    except Exception as error:
        _json(output / "status.json", {
            "state": "failed", "error_type": type(error).__name__,
            "error": str(error),
        })
        raise


def _train_and_evaluate(raw_data, config=None, output_dir="runs/model_comparison", *,
                        training_config=None, device=None):
    """Select using training-period validation, then report the frozen holdout.

    Each model's final calibrator and threshold use base-seed outer out-of-fold
    scores only. Its estimator is subsequently refitted on the entire 70% train.
    This standard cross-fit/refit step can shift score distributions; report the
    final holdout as an audit, never as a new selection opportunity.
    """
    cfg = copy.deepcopy(config or load_config())
    settings = copy.deepcopy(training_config or load_training_config())
    device = device or settings["device"]
    _validate_settings(settings, device)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists():
        raise FileExistsError("Use a new output directory; a completed run exists")
    _json(output / "status.json", {"state": "running", "device": device})
    raw = raw_data.reset_index(drop=True)
    split = chronological_train_test_split(raw, cfg)
    training = extract_dataset(split.train, cfg, require_target=True)
    require_both_classes(training.target, "training partition")
    all_folds, search_rows, summaries, models, params_by_model = [], [], [], {}, {}
    search_summaries = []
    use_tpe = settings.get("search", {}).get("method", "grid") == "tpe"
    if use_tpe:
        from .adaptive_search import protocol_fingerprint, search_family

        fingerprint = protocol_fingerprint(split.train, cfg, settings)
    else:
        fingerprint = None
    base_seed = settings["seeds"][0]
    # No test labels or predictions are inspected until selection.json is written.
    with threadpool_limits(limits=settings["threads"]):
        for name, space in settings["models"].items():
            print(f"Searching {name}", flush=True)
            started_search = time.perf_counter()
            if use_tpe and name not in REFERENCE_MODELS:
                def objective(parameters):
                    fold_rows, _ = evaluate_candidate(
                        split.train, cfg, settings, name, parameters,
                        base_seed, device,
                    )
                    return fold_rows

                smoke_parameters = None
                if settings.get("smoke_run"):
                    smoke_parameters = dict(next(iter(ParameterGrid(space))))
                params, trial_rows, search_summary = search_family(
                    name, settings["search_spaces"][name], objective,
                    storage_path=Path(settings["search"]["study_storage"]),
                    fingerprint=fingerprint,
                    optimizer=settings["search"],
                    smoke_parameters=smoke_parameters,
                )
                search_rows.extend(trial_rows)
                search_summaries.append(search_summary)
                started_finalization = time.perf_counter()
                rows, oof = evaluate_candidate(
                    split.train, cfg, settings, name, params, base_seed, device
                )
                print(
                    f"  best trial {search_summary['best_trial']}: "
                    f"temporal F1={search_summary['best_mean_f1']:.4f}", flush=True,
                )
            else:
                winner = None
                for index, params in enumerate(ParameterGrid(space)):
                    rows, oof = evaluate_candidate(
                        split.train, cfg, settings, name, params, base_seed, device
                    )
                    mean = float(np.mean([row["default_f1"] for row in rows]))
                    search_rows.append(dict(model=name, candidate=index, mean_f1=mean,
                                            parameters=json.dumps(params, sort_keys=True)))
                    if winner is None or mean > winner[0]:
                        winner = (mean, params, rows, oof)
                    print(f"  candidate {index + 1}: temporal F1={mean:.4f}", flush=True)
                _, params, rows, oof = winner
                search_summaries.append({
                    "model": name, "method": "grid", "attempted": index + 1,
                    "completed": index + 1, "failed": 0, "pruned": 0,
                    "search_elapsed_seconds": time.perf_counter() - started_search,
                })
                started_finalization = time.perf_counter()
            params_by_model[name] = params
            for seed in settings["seeds"][1:]:
                extra_rows, _ = evaluate_candidate(
                    split.train, cfg, settings, name, params, seed, device
                )
                rows.extend(extra_rows)
            all_folds.extend(rows)
            model = build_model(name, cfg, base_seed, device, parameters=params,
                                training_config=settings)
            started = time.perf_counter()
            model.fit(training.predictors, training.target)
            calibrator = fit_calibrator(oof.raw_score, oof.target)
            threshold = choose_threshold(
                oof.target, calibrated_probability(calibrator, oof.raw_score)
            )
            selected = SelectedCreditModel(model, calibrator, threshold, name)
            fit_seconds = time.perf_counter() - started
            models[name] = selected
            latency, size = benchmark_model(selected, training.predictors, settings)
            frame = pd.DataFrame(rows)
            summaries.append(dict(
                model=name, mean_f1=float(frame.default_f1.mean()),
                temporal_f1_std=float(
                    frame.groupby("fold").default_f1.mean().std(ddof=0)
                ),
                seed_f1_std=float(frame.groupby("seed").default_f1.mean().std(ddof=0)),
                mean_precision=float(frame.default_precision.mean()),
                mean_recall=float(frame.default_recall.mean()),
                mean_average_precision=float(frame.average_precision.mean()),
                mean_roc_auc=float(frame.roc_auc.mean()),
                threshold=threshold if name not in REFERENCE_MODELS else None,
                fit_seconds=fit_seconds,
                finalization_seconds=time.perf_counter() - started_finalization,
                search_seconds=search_summaries[-1]["search_elapsed_seconds"],
                cpu_batch_ms=latency, artifact_bytes=size,
                training_device=(device if name in {"pytorch_mlp", "xgboost"}
                                 else settings["lightgbm_device"]
                                 if name == "lightgbm" else "cpu"),
            ))
            oof.to_csv(output / f"{name}_oof.csv", index=False)
            pd.DataFrame(search_rows).to_csv(output / "search.csv", index=False)
        summary = pd.DataFrame(summaries)
        best_name = select_best_model(summary, settings["f1_tolerance"])
        _json(output / "selection.json", {
            "model": best_name, "parameters": params_by_model[best_name],
            "threshold": models[best_name].threshold,
            "rule": "within tolerance of best mean F1; temporal std, seed std, "
                    "CPU batch ms, bytes, name ascending",
            "f1_tolerance": settings["f1_tolerance"],
            "protocol_fingerprint": fingerprint,
        })
        joblib.dump(models[best_name], output / "best_model.joblib")
        print(f"Selected {best_name}; evaluating frozen holdout", flush=True)
        evaluation = extract_dataset(split.test, cfg, require_target=True)
        require_both_classes(evaluation.target, "holdout partition")
        holdout_rows, predictions = [], []
        for name, selected in models.items():
            model = selected.pipeline if name in REFERENCE_MODELS else selected
            probability = model.predict_proba(evaluation.predictors)[:, 0]
            predicted = model.predict(evaluation.predictors)
            metrics = summarize_classification(
                evaluation.target, predicted, probability,
                review_fraction=settings["review_fraction"],
            )
            holdout_rows.append(dict(model=name, **metrics))
            predictions.append(pd.DataFrame({
                "model": name, "row_id": split.test.index,
                "target": evaluation.target.to_numpy(), "prediction": predicted,
                "default_probability": probability,
            }))
    folds = pd.DataFrame(all_folds)
    holdout = pd.DataFrame(holdout_rows)
    predictions = pd.concat(predictions, ignore_index=True)
    folds.to_csv(output / "validation_folds.csv", index=False)
    summary.to_csv(output / "validation_summary.csv", index=False)
    holdout.to_csv(output / "holdout_summary.csv", index=False)
    predictions.to_csv(output / "holdout_predictions.csv", index=False)
    _json(output / "holdout_metrics.json", holdout_rows)
    charts = write_comparison_graphs(output / "figures", folds, summary,
                                     predictions, holdout)
    report = (
        "# Model comparison\n\n"
        f"Selected using temporal validation: **{best_name}**.\n\n"
        "Default is Pago_atiempo=0. References retain their original operating points "
        "and are not selection candidates.\n\n## Training-period validation\n\n"
        + _markdown(summary.fillna("reference policy"))
        + "\n\n## Search accounting\n\n"
        + _markdown(pd.DataFrame(search_summaries))
        + "\n\n## Frozen chronological holdout\n\n"
        + _markdown(holdout.drop(columns="confusion_matrix"))
        + "\n\nThresholds and sigmoid calibration were learned on training data. "
        "Validation scores also guide hyperparameter selection and are therefore "
        "optimistic; the holdout audits the frozen choice. The holdout was previously "
        "examined during EDA/baseline work and is not a fresh external validation set. "
        "Feature availability at decision time remains an assumption. "
        "Refitting on more history can shift calibrated score distributions.\n"
    )
    (output / "report.md").write_text(report, encoding="utf-8")
    packages = {}
    for package in ("numpy", "pandas", "scikit-learn", "torch", "xgboost",
                    "lightgbm", "optuna", "joblib", "matplotlib"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = "not installed"
    manifest = {
        "configuration": cfg, "training_configuration": settings,
        "requested_device": device, "split": split.summary,
        "dataset_sha256": hashlib.sha256(
            raw.to_csv(index=False).encode("utf-8")
        ).hexdigest(),
        "platform": platform.platform(), "processor": platform.processor(),
        "python": platform.python_version(), "packages": packages,
        "selection": best_name, "search": search_summaries,
        "protocol_fingerprint": fingerprint,
        "actual_devices": {
            row["model"]: row["training_device"] for row in summaries
        },
        "benchmark_batch_rows": min(
            len(training.predictors), settings["benchmark_batch_size"]),
        "folds": _fold_manifest(split.train, cfg, settings),
    }
    _json(output / "manifest.json", manifest)
    _json(output / "status.json", {"state": "complete", "selected_model": best_name})
    return TrainingResult(models[best_name], summary, holdout, {
        "model": str(output / "best_model.joblib"),
        "report": str(output / "report.md"),
        "manifest": str(output / "manifest.json"),
        **{Path(path).stem: path for path in charts},
    })


def _fold_manifest(raw, config, settings):
    column = config["predictive_pipeline"]["train_test_split"]["timestamp_column"]
    result = []
    for train, valid in temporal_folds(raw, config, settings["temporal_blocks"]):
        inner = chronological_train_test_split(
            train, config, train_fraction=settings["inner_train_fraction"]
        )
        result.append({
            "inner_split": inner.summary,
            "validation_start": str(valid[column].iloc[0]),
            "validation_end": str(valid[column].iloc[-1]),
            "validation_rows": len(valid),
        })
    return result


def _validate_settings(settings, device):
    if device != "cpu" or settings["lightgbm_device"] != "cpu":
        raise ValueError("Tracked model training supports CPU only")
    if (not settings["seeds"] or len(set(settings["seeds"])) != len(settings["seeds"])
            or not 0 < settings["inner_train_fraction"] < 1
            or not 0 <= settings["f1_tolerance"] <= 1
            or not 0 < settings["review_fraction"] <= 1
            or settings["threads"] < 1
            or settings["benchmark_repeats"] < 1
            or settings["benchmark_batch_size"] < 1
            or not (set(settings["models"]) - REFERENCE_MODELS)):
        raise ValueError("Invalid training configuration")
    for name, space in settings["models"].items():
        if not 1 <= len(ParameterGrid(space)) <= 8:
            raise ValueError(f"{name}: configure between one and eight candidates")
        if name not in {
            "logistic_regression", "decision_tree", "gaussian_nb", "random_forest",
            "extra_trees", "svm", "xgboost", "lightgbm", "pytorch_mlp",
            "heuristic", "dummy",
        }:
            raise ValueError(f"Unknown model family: {name}")
        dependency = "torch" if name == "pytorch_mlp" else name
        if dependency in {"torch", "lightgbm", "xgboost"}:
            if importlib.util.find_spec(dependency) is None:
                raise ImportError(
                    f"{name} requires {dependency}; install mlops_pipeline/requirements-training.txt"
                )
    search = settings.get("search", {"method": "grid"})
    if search.get("method") not in {"grid", "tpe"}:
        raise ValueError("search method must be grid or tpe")
    if search["method"] == "tpe":
        from .adaptive_search import validate_space

        if (not isinstance(search.get("seed"), int)
                or not isinstance(search.get("n_trials"), int)
                or search["n_trials"] < 1
                or search.get("timeout_seconds", 0) <= 0
                or not isinstance(search.get("startup_trials"), int)
                or search["startup_trials"] < 1
                or not search.get("study_storage")):
            raise ValueError("Invalid TPE search configuration")
        if importlib.util.find_spec("optuna") is None:
            raise ImportError("TPE search requires optuna; install mlops_pipeline/requirements-training.txt")
        for name in settings["models"]:
            if name not in REFERENCE_MODELS:
                if name not in settings.get("search_spaces", {}):
                    raise ValueError(f"{name}: missing adaptive search space")
                validate_space(settings["search_spaces"][name], name)
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--training-config", type=Path, default=TRAINING_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu"])
    parser.add_argument("--search-method", choices=["grid", "tpe"])
    parser.add_argument("--n-trials", type=int,
                        help="Total TPE trial cap per learned family, including resumed trials")
    parser.add_argument("--timeout-seconds", type=float,
                        help="Total TPE search seconds per family; in-flight trials may finish")
    parser.add_argument("--study-storage", type=Path,
                        help="Ignored SQLite study path for resumable TPE search")
    parser.add_argument("--smoke", action="store_true",
                        help="One small candidate/seed per family; not a benchmark")
    args = parser.parse_args(argv)
    config = load_config(args.config) if args.config else load_config()
    settings = load_training_config(args.training_config)
    settings.setdefault("search", {"method": "grid"})
    if args.search_method:
        settings["search"]["method"] = args.search_method
    if args.n_trials is not None:
        settings["search"]["n_trials"] = args.n_trials
    if args.timeout_seconds is not None:
        settings["search"]["timeout_seconds"] = args.timeout_seconds
    if args.study_storage is not None:
        settings["search"]["study_storage"] = str(args.study_storage)
    if args.smoke:
        settings["seeds"] = [settings["seeds"][0]]
        settings["models"] = {
            name: {key: values[:1] for key, values in space.items()}
            for name, space in settings["models"].items()
        }
        for space in settings["models"].values():
            if "n_estimators" in space:
                space["n_estimators"] = [10]
            if "epochs" in space:
                space["epochs"] = [2]
        settings["smoke_run"] = True
        if settings["search"]["method"] == "tpe":
            settings["search"]["n_trials"] = 1
            settings["search"]["timeout_seconds"] = min(
                float(settings["search"]["timeout_seconds"]), 300.0
            )
    read_options = {"config_dir": args.config.parent} if args.config else {}
    raw = read_raw_data(config, args.input, **read_options)
    result = train_and_evaluate(raw, config, args.output_dir,
                                training_config=settings, device=args.device)
    print(json.dumps(result.artifact_paths, indent=2))


if __name__ == "__main__":
    # Keep persisted class/function paths importable outside this CLI process.
    from mlops_pipeline.src.model_training_evaluation import main as run_main

    run_main()
