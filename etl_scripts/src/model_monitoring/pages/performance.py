"""Matured outcome performance page."""

from dash import dash_table, dcc, html
import pandas as pd
import plotly.express as px

from .common import empty_state


PERFORMANCE_METRICS = {
    "default_f1", "default_precision", "default_recall", "average_precision",
    "roc_auc", "accuracy", "brier_score", "log_loss", "expected_calibration_error",
}


def layout(rows: list[dict]):
    selected = [row for row in rows if row["metric_name"] in PERFORMANCE_METRICS]
    available = [row for row in selected if row["metric_value"] is not None]
    if not available:
        return empty_state("Matured outcomes from both classes are required for performance metrics.")
    frame = pd.DataFrame(available).sort_values("window_end")
    figure = px.line(
        frame, x="window_end", y="metric_value", color="metric_name", markers=True,
        title="Matured model performance and calibration",
    )
    latest_end = frame.window_end.max()
    latest = frame.loc[frame.window_end == latest_end, ["metric_name", "metric_value", "status"]]
    latest["metric_value"] = latest.metric_value.round(5)
    return html.Div([
        dcc.Graph(figure=figure),
        dash_table.DataTable(
            data=latest.to_dict("records"),
            columns=[{"name": name.replace("_", " ").title(), "id": name} for name in latest.columns],
        ),
    ])
