"""Run monitoring windows and retention from scheduled one-off dynos."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, time, timedelta

from ..database.connectors.postgres import create_database_engine, create_session_factory
from .services.monitoring_runner import MonitoringRunner
from .services.retention_service import retain_recent_predictions
from .settings import MonitoringSettings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["compute", "retention"])
    parser.add_argument("--catch-up", action="store_true")
    parser.add_argument("--include-retention", action="store_true")
    args = parser.parse_args(argv)
    settings = MonitoringSettings.from_env()
    settings.validate()
    engine = create_database_engine()
    factory = create_session_factory(engine)
    if args.command == "retention":
        result = {"deleted_batches": retain_recent_predictions(
            factory, settings.retention_days
        )}
    else:
        runner = MonitoringRunner(factory, settings)
        if args.catch_up:
            windows = runner.run_catchup()
        else:
            end = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
            windows = [runner.run_window(
                end - timedelta(days=settings.window_days), end
            )]
        result = {"windows": windows}
        if args.include_retention:
            result["deleted_batches"] = retain_recent_predictions(
                factory, settings.retention_days
            )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
