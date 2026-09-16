"""Dash pages render only aggregate metrics and explicit empty states."""

from __future__ import annotations

from dash import dash_table, html

from mlops_pipeline.src.deployment.model_monitoring.pages import (
    feature_drift_layout,
    operations_layout,
    overview_layout,
    performance_layout,
    predictions_layout,
)
from mlops_pipeline.src.deployment.model_monitoring.pages.common import card, latest_rows, metric


ROWS = [
    {
        "window_start": "2026-09-10", "window_end": "2026-09-11",
        "run_status": "complete", "metric_name": "prediction_rows",
        "feature_name": None, "metric_value": 7, "status": "ok",
    },
    {
        "window_start": "2026-09-11", "window_end": "2026-09-12",
        "run_status": "complete", "metric_name": "prediction_rows",
        "feature_name": None, "metric_value": 10, "status": "ok",
    },
    {
        "window_start": "2026-09-11", "window_end": "2026-09-12",
        "run_status": "complete", "metric_name": "matured_rows",
        "feature_name": None, "metric_value": 5, "status": "warning",
    },
    {
        "window_start": "2026-09-11", "window_end": "2026-09-12",
        "run_status": "complete", "metric_name": "population_psi",
        "feature_name": "amount", "metric_value": 0.256789, "status": "alert",
    },
    {
        "window_start": "2026-09-11", "window_end": "2026-09-12",
        "run_status": "complete", "metric_name": "population_psi",
        "feature_name": "__default_probability__", "metric_value": 0.12,
        "status": "warning",
    },
    {
        "window_start": "2026-09-11", "window_end": "2026-09-12",
        "run_status": "complete", "metric_name": "predicted_default_fraction",
        "feature_name": None, "metric_value": 0.2, "status": "ok",
    },
    {
        "window_start": "2026-09-11", "window_end": "2026-09-12",
        "run_status": "complete", "metric_name": "default_f1",
        "feature_name": None, "metric_value": 0.4, "status": "ok",
    },
]


def test_shared_page_helpers_use_latest_window_and_safe_fallback():
    assert latest_rows([]) == []
    assert len(latest_rows(ROWS)) == len(ROWS) - 1
    assert metric(ROWS, "prediction_rows") == 7
    assert metric(ROWS, "missing") is None
    assert isinstance(card("Alert", 1, "alert"), html.Div)
    assert isinstance(card("Unknown", 1, "unrecognized"), html.Div)


def test_all_pages_render_explicit_empty_state():
    for layout in (
        overview_layout, feature_drift_layout, predictions_layout,
        performance_layout, operations_layout,
    ):
        assert isinstance(layout([]), html.Div)


def test_feature_drift_and_operations_tables_use_aggregate_rows():
    drift = feature_drift_layout(ROWS)
    table = next(child for child in drift.children if isinstance(child, dash_table.DataTable))
    assert table.data == [{
        "feature": "amount", "metric": "population_psi", "value": 0.25679,
        "status": "alert",
    }]
    operations = operations_layout(ROWS)
    assert isinstance(operations, dash_table.DataTable)
    assert operations.data[0]["window_end"] == "2026-09-12"
    assert operations.data[0]["alerts"] == 1
    assert operations.data[0]["warnings"] == 2


def test_overview_performance_and_prediction_pages_show_latest_aggregates():
    assert isinstance(overview_layout(ROWS), html.Div)
    performance = performance_layout(ROWS)
    table = next(child for child in performance.children if isinstance(child, dash_table.DataTable))
    assert table.data[0]["metric_value"] == 0.4
    predictions = predictions_layout(ROWS)
    assert isinstance(predictions, html.Div)
    assert len(predictions.children) == 2
