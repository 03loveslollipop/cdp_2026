"""Matured-outcome performance and calibration metrics."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import brier_score_loss, log_loss

from ....model_training_evaluation import summarize_classification
from ..models import MetricResult
from ..settings import MonitoringSettings


def expected_calibration_error(
    actual_default: np.ndarray,
    probability: np.ndarray,
    bins: int = 10,
) -> float:
    edges = np.linspace(0, 1, bins + 1)
    bucket = np.clip(np.digitize(probability, edges[1:-1]), 0, bins - 1)
    result = 0.0
    for index in range(bins):
        selected = bucket == index
        if selected.any():
            result += float(selected.mean()) * abs(
                float(actual_default[selected].mean()) - float(probability[selected].mean())
            )
    return float(result)


def calculate_performance(
    rows: list[dict], settings: MonitoringSettings
) -> list[MetricResult]:
    if len(rows) < settings.minimum_rows:
        return [MetricResult(
            "matured_rows", float(len(rows)), "insufficient_data",
            details={"minimum_rows": settings.minimum_rows},
        )]
    target = np.asarray([row["actual_label"] for row in rows], dtype=int)
    predicted = np.asarray([row["predicted_label"] for row in rows], dtype=int)
    probability = np.asarray([row["default_probability"] for row in rows], dtype=float)
    metrics = [MetricResult("matured_rows", float(len(rows)), "ok")]
    if not np.array_equal(np.unique(target), [0, 1]):
        metrics.append(MetricResult(
            "default_f1", None, "insufficient_data",
            details={"reason": "both outcome classes are required"},
        ))
        return metrics
    summary = summarize_classification(target, predicted, probability)
    for name in (
        "default_f1",
        "default_precision",
        "default_recall",
        "average_precision",
        "roc_auc",
        "accuracy",
    ):
        metrics.append(MetricResult(name, float(summary[name]), "ok"))
    actual_default = (target == 0).astype(int)
    metrics.extend([
        MetricResult("brier_score", float(brier_score_loss(actual_default, probability)), "ok"),
        MetricResult("log_loss", float(log_loss(actual_default, probability, labels=[0, 1])), "ok"),
        MetricResult(
            "expected_calibration_error",
            expected_calibration_error(actual_default, probability),
            "ok",
        ),
    ])
    return metrics
