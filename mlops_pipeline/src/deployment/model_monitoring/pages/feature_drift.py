"""Feature-level population drift page."""

from dash import dash_table, dcc, html
import plotly.express as px

from .common import empty_state, latest_rows


def layout(rows: list[dict]):
    selected = [row for row in latest_rows(rows) if (
        row["metric_name"] in {"population_psi", "missing_rate_delta", "unknown_category_rate"}
        and row.get("feature_name") not in {None, "__default_probability__"}
    )]
    if not selected:
        return empty_state("Feature drift needs a completed window with enough predictions.")
    table_rows = [{
        "feature": row["feature_name"],
        "metric": row["metric_name"],
        "value": None if row["metric_value"] is None else round(row["metric_value"], 5),
        "status": row["status"],
    } for row in selected]
    psi = [row for row in table_rows if row["metric"] == "population_psi" and row["value"] is not None]
    figure = px.bar(psi, x="feature", y="value", color="status", title="Latest feature PSI")
    figure.add_hline(y=0.10, line_dash="dot", line_color="#a26000")
    figure.add_hline(y=0.25, line_dash="dash", line_color="#ae2525")
    return html.Div([
        dcc.Graph(figure=figure),
        dash_table.DataTable(
            data=table_rows,
            columns=[{"name": name.replace("_", " ").title(), "id": name} for name in table_rows[0]],
            sort_action="native",
            page_size=20,
            style_table={"overflowX": "auto"},
        ),
    ])
