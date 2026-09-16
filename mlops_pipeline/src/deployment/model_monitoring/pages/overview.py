"""Operational monitoring overview page."""

from dash import html

from .common import card, empty_state, latest_rows, metric


def layout(rows: list[dict]):
    latest = latest_rows(rows)
    if not latest:
        return empty_state()
    prediction_rows = metric(latest, "prediction_rows")
    matured_rows = metric(latest, "matured_rows")
    alerts = sum(row["status"] == "alert" for row in latest)
    warnings = sum(row["status"] == "warning" for row in latest)
    return html.Div([
        html.Div([
            card("Predictions in window", int(prediction_rows or 0)),
            card("Matured outcomes", int(matured_rows or 0)),
            card("Alerts", alerts, "alert" if alerts else "ok"),
            card("Warnings", warnings, "warning" if warnings else "ok"),
        ], style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit,minmax(170px,1fr))", "gap": "1rem"}),
        html.P(
            f"Latest aggregate window: {latest[0]['window_start']} to {latest[0]['window_end']}",
            style={"marginTop": "1.5rem"},
        ),
    ])
