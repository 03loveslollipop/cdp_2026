"""Dash application mounted under the FastAPI process."""

from __future__ import annotations

from collections.abc import Callable

from dash import Dash, Input, Output, dcc, html

from .pages import (
    feature_drift_layout,
    operations_layout,
    overview_layout,
    performance_layout,
    predictions_layout,
)
from .services.dashboard_service import DashboardService


PAGES = {
    "overview": overview_layout,
    "features": feature_drift_layout,
    "predictions": predictions_layout,
    "performance": performance_layout,
    "operations": operations_layout,
}


def create_dashboard(runtime_getter: Callable[[], object | None]) -> Dash:
    dashboard = Dash(
        __name__,
        requests_pathname_prefix="/monitor/",
        routes_pathname_prefix="/",
        title="CDP 2026 monitoring",
    )
    dashboard.layout = html.Div([
        html.Div([
            html.Div([html.H1("Model monitoring"), html.P("Aggregate-only operational view")]),
            html.A("Batch predictions", href="/"),
        ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"}),
        dcc.Tabs(id="monitor-tab", value="overview", children=[
            dcc.Tab(label="Overview", value="overview"),
            dcc.Tab(label="Feature drift", value="features"),
            dcc.Tab(label="Predictions", value="predictions"),
            dcc.Tab(label="Performance", value="performance"),
            dcc.Tab(label="Operations", value="operations"),
        ]),
        dcc.Interval(id="monitor-refresh", interval=60_000, n_intervals=0),
        html.Div(id="monitor-content", style={"paddingTop": "1.5rem"}),
    ], style={
        "fontFamily": "system-ui, sans-serif", "maxWidth": "1200px",
        "margin": "2rem auto", "padding": "0 1rem", "color": "#172033",
    })

    @dashboard.callback(
        Output("monitor-content", "children"),
        Input("monitor-tab", "value"),
        Input("monitor-refresh", "n_intervals"),
    )
    def render(tab: str, _interval: int):
        runtime = runtime_getter()
        if runtime is None:
            return html.Div("Application is starting.")
        try:
            rows = DashboardService(runtime.session_factory).snapshot()
            return PAGES.get(tab, overview_layout)(rows)
        except Exception:
            return html.Div("Monitoring aggregates are temporarily unavailable.")

    return dashboard
