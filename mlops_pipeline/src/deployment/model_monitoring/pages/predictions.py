"""Prediction distribution page."""

from dash import dcc, html
import pandas as pd
import plotly.express as px

from .common import card, empty_state, latest_rows, metric


def layout(rows: list[dict]):
    selected = [row for row in rows if row["metric_name"] == "predicted_default_fraction"]
    if not selected:
        return empty_state("Prediction-distribution metrics are not available yet.")
    frame = pd.DataFrame(selected).sort_values("window_end")
    figure = px.line(
        frame, x="window_end", y="metric_value", markers=True,
        title="Predicted default fraction by monitoring window",
    )
    latest = latest_rows(rows)
    score_psi = next((row for row in latest if row["metric_name"] == "population_psi"
                      and row.get("feature_name") == "__default_probability__"), None)
    return html.Div([
        html.Div([
            card("Latest predicted-default fraction", f"{100 * (metric(latest, 'predicted_default_fraction') or 0):.2f}%"),
            card("Latest score PSI", "n/a" if score_psi is None or score_psi["metric_value"] is None
                 else f"{score_psi['metric_value']:.4f}", score_psi["status"] if score_psi else "neutral"),
        ], style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit,minmax(220px,1fr))", "gap": "1rem"}),
        dcc.Graph(figure=figure),
    ])
