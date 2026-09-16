"""Population, missingness, unknown-category, and score drift metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..models import MetricResult
from ..settings import MonitoringSettings


EPSILON = 1e-6


def population_stability_index(expected: np.ndarray, actual: np.ndarray) -> float:
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    if expected.shape != actual.shape or expected.ndim != 1:
        raise ValueError("PSI distributions must have the same one-dimensional shape")
    expected = np.clip(expected, EPSILON, None)
    actual = np.clip(actual, EPSILON, None)
    expected /= expected.sum()
    actual /= actual.sum()
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def _status(value: float, settings: MonitoringSettings) -> str:
    if value >= settings.psi_alert:
        return "alert"
    if value >= settings.psi_warning:
        return "warning"
    return "ok"


def _numeric_metrics(
    feature: str,
    values: pd.Series,
    profile: dict,
    settings: MonitoringSettings,
) -> list[MetricResult]:
    numeric = pd.to_numeric(values, errors="coerce")
    present = numeric.dropna().to_numpy(dtype=float)
    boundaries = np.asarray(profile.get("bins", []), dtype=float)
    bucket_count = len(boundaries) + 1
    if len(present):
        counts = np.bincount(np.digitize(present, boundaries), minlength=bucket_count)
        actual = counts / counts.sum()
        psi = population_stability_index(profile["proportions"], actual)
    else:
        psi = None
    missing_rate = float(numeric.isna().mean())
    missing_delta = missing_rate - float(profile.get("missing_rate", 0.0))
    return [
        MetricResult(
            "population_psi",
            psi,
            "insufficient_data" if psi is None else _status(psi, settings),
            feature,
            {"rows": len(values), "non_missing_rows": len(present)},
        ),
        MetricResult(
            "missing_rate_delta",
            missing_delta,
            "warning" if abs(missing_delta) >= 0.10 else "ok",
            feature,
            {"actual_rate": missing_rate, "reference_rate": profile.get("missing_rate", 0.0)},
        ),
    ]


def _categorical_metrics(
    feature: str,
    values: pd.Series,
    profile: dict,
    settings: MonitoringSettings,
) -> list[MetricResult]:
    normalized = values.astype("string")
    reference = profile.get("proportions", {})
    categories = sorted(reference)
    present = normalized.dropna()
    if len(present):
        actual_known = np.asarray([
            (present == category).sum() / len(present) for category in categories
        ])
        unknown = float((~present.isin(categories)).sum() / len(present))
        expected = np.asarray([reference[category] for category in categories] + [EPSILON])
        actual = np.append(actual_known, unknown)
        psi = population_stability_index(expected, actual)
    else:
        unknown = 0.0
        psi = None
    missing_rate = float(normalized.isna().mean())
    missing_delta = missing_rate - float(profile.get("missing_rate", 0.0))
    return [
        MetricResult(
            "population_psi",
            psi,
            "insufficient_data" if psi is None else _status(psi, settings),
            feature,
            {
                "rows": len(values),
                "non_missing_rows": len(present),
                "categories": len(categories),
            },
        ),
        MetricResult(
            "unknown_category_rate",
            unknown,
            "warning" if unknown >= 0.05 else "ok",
            feature,
            {"known_categories": categories},
        ),
        MetricResult(
            "missing_rate_delta",
            missing_delta,
            "warning" if abs(missing_delta) >= 0.10 else "ok",
            feature,
            {"actual_rate": missing_rate, "reference_rate": profile.get("missing_rate", 0.0)},
        ),
    ]


def calculate_drift(
    prediction_rows: list[dict],
    reference_profiles: dict[str, dict],
    settings: MonitoringSettings,
) -> list[MetricResult]:
    if len(prediction_rows) < settings.minimum_rows:
        return [MetricResult(
            "prediction_rows",
            float(len(prediction_rows)),
            "insufficient_data",
            details={"minimum_rows": settings.minimum_rows},
        )]
    predictors = pd.DataFrame([row["predictors"] for row in prediction_rows])
    metrics = [MetricResult("prediction_rows", float(len(predictors)), "ok")]
    for feature, profile in reference_profiles.items():
        if feature == "__default_probability__":
            values = pd.Series([row["default_probability"] for row in prediction_rows])
            metrics.extend(_numeric_metrics(feature, values, profile, settings))
        elif feature not in predictors:
            metrics.append(MetricResult(
                "population_psi", None, "insufficient_data", feature,
                {"reason": "feature_not_logged"},
            ))
        elif profile["type"] == "categorical":
            metrics.extend(_categorical_metrics(feature, predictors[feature], profile, settings))
        else:
            metrics.extend(_numeric_metrics(feature, predictors[feature], profile, settings))
    predicted_default_fraction = float(np.mean([
        row["predicted_label"] == 0 for row in prediction_rows
    ]))
    metrics.append(MetricResult(
        "predicted_default_fraction", predicted_default_fraction, "ok"
    ))
    return metrics
