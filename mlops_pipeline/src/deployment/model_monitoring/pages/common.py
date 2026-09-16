"""Shared aggregate-only Dash components."""

from __future__ import annotations

from dash import html


def latest_rows(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    latest = max(row["window_end"] for row in rows)
    return [row for row in rows if row["window_end"] == latest]


def metric(rows: list[dict], name: str) -> float | None:
    for row in rows:
        if row["metric_name"] == name and row.get("feature_name") is None:
            return row.get("metric_value")
    return None


def card(label: str, value: object, status: str = "neutral"):
    colors = {"ok": "#19784b", "warning": "#a26000", "alert": "#ae2525", "neutral": "#3157c8"}
    return html.Div([
        html.Small(label),
        html.Div(value, style={"fontSize": "1.8rem", "fontWeight": "700"}),
    ], style={
        "borderTop": f"4px solid {colors.get(status, colors['neutral'])}",
        "padding": "1rem", "background": "white", "borderRadius": "8px",
        "boxShadow": "0 3px 12px #17203312",
    })


def empty_state(message: str = "No monitoring run has completed yet."):
    return html.Div(message, style={"padding": "2rem", "background": "white", "borderRadius": "8px"})
