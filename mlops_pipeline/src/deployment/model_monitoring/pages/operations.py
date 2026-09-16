"""Monitoring-job and data-quality status page."""

from dash import dash_table

from .common import empty_state


def layout(rows: list[dict]):
    if not rows:
        return empty_state()
    grouped = {}
    for row in rows:
        key = (row["window_start"], row["window_end"], row["run_status"])
        aggregate = grouped.setdefault(key, {
            "window_start": row["window_start"], "window_end": row["window_end"],
            "run_status": row["run_status"], "metrics": 0,
            "alerts": 0, "warnings": 0, "insufficient": 0,
        })
        aggregate["metrics"] += 1
        aggregate["alerts"] += row["status"] == "alert"
        aggregate["warnings"] += row["status"] == "warning"
        aggregate["insufficient"] += row["status"] == "insufficient_data"
    data = sorted(grouped.values(), key=lambda row: row["window_end"], reverse=True)
    return dash_table.DataTable(
        data=data,
        columns=[{"name": name.replace("_", " ").title(), "id": name} for name in data[0]],
        page_size=15,
        style_table={"overflowX": "auto"},
    )
