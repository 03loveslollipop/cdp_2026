from contextlib import nullcontext

import numpy as np
import pytest

from etl_scripts.src.model_monitoring.services.drift_service import (
    calculate_drift,
    population_stability_index,
)
from etl_scripts.src.model_monitoring.services.performance_service import (
    calculate_performance,
    expected_calibration_error,
)
from etl_scripts.src.model_monitoring.services.dashboard_service import DashboardService
from etl_scripts.src.model_monitoring.settings import MonitoringSettings


SETTINGS = MonitoringSettings(minimum_rows=4)


def test_population_stability_index_and_alert_levels():
    assert population_stability_index([0.5, 0.5], [0.5, 0.5]) == pytest.approx(0)
    profiles = {
        "amount": {
            "type": "numeric", "bins": [5.0], "proportions": [0.5, 0.5],
            "missing_rate": 0.0,
        },
        "kind": {
            "type": "categorical", "proportions": {"a": 0.5, "b": 0.5},
            "missing_rate": 0.0,
        },
        "__default_probability__": {
            "type": "numeric", "bins": [0.5], "proportions": [0.5, 0.5],
            "missing_rate": 0.0,
        },
    }
    rows = [{
        "predictors": {"amount": value, "kind": "new"},
        "default_probability": 0.9,
        "predicted_label": 0,
    } for value in [10, 11, 12, 13]]
    metrics = calculate_drift(rows, profiles, SETTINGS)
    amount_psi = next(metric for metric in metrics if (
        metric.metric_name == "population_psi" and metric.feature_name == "amount"
    ))
    unknown = next(metric for metric in metrics if metric.metric_name == "unknown_category_rate")
    assert amount_psi.status == "alert"
    assert unknown.metric_value == 1.0
    assert unknown.status == "warning"


def test_monitoring_reports_insufficient_data_explicitly():
    metrics = calculate_drift([], {}, SETTINGS)
    assert metrics[0].status == "insufficient_data"
    metrics = calculate_performance([], SETTINGS)
    assert metrics[0].status == "insufficient_data"


def test_all_missing_categorical_values_do_not_report_false_drift():
    profiles = {
        "kind": {
            "type": "categorical",
            "proportions": {"a": 0.5, "b": 0.5},
            "missing_rate": 0.0,
        },
    }
    rows = [{
        "predictors": {"kind": None},
        "default_probability": 0.5,
        "predicted_label": 1,
    } for _ in range(4)]
    metrics = calculate_drift(rows, profiles, SETTINGS)
    psi = next(metric for metric in metrics if metric.metric_name == "population_psi")
    assert psi.metric_value is None
    assert psi.status == "insufficient_data"


def test_dashboard_requests_aggregates_for_only_the_active_model(monkeypatch):
    requested = {}

    class Repository:
        def __init__(self, _session):
            pass

        def recent_metrics(self, model_version_id, limit):
            requested.update(model_version_id=model_version_id, limit=limit)
            return [{"metric_name": "prediction_rows"}]

    monkeypatch.setattr(
        "etl_scripts.src.model_monitoring.services.dashboard_service.MonitoringRepository",
        Repository,
    )
    service = DashboardService(lambda: nullcontext(object()))
    assert service.snapshot("active-model", limit=25) == [
        {"metric_name": "prediction_rows"}
    ]
    assert requested == {"model_version_id": "active-model", "limit": 25}


def test_matured_performance_includes_discrimination_and_calibration():
    rows = [
        {"actual_label": 0, "predicted_label": 0, "default_probability": 0.9},
        {"actual_label": 0, "predicted_label": 0, "default_probability": 0.8},
        {"actual_label": 1, "predicted_label": 1, "default_probability": 0.2},
        {"actual_label": 1, "predicted_label": 1, "default_probability": 0.1},
    ]
    metrics = calculate_performance(rows, SETTINGS)
    names = {metric.metric_name for metric in metrics}
    assert {"default_f1", "average_precision", "roc_auc", "brier_score",
            "log_loss", "expected_calibration_error"} <= names
    assert expected_calibration_error(np.array([1, 0]), np.array([0.9, 0.1])) < 0.11
