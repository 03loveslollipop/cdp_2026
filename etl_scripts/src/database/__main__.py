"""Database management commands used by release automation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .connectors.postgres import create_database_engine, create_session_factory
from .migrations import run_migrations
from .seed import seed_sample_data


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate")
    subparsers.add_parser("release")
    seed = subparsers.add_parser("seed-sample")
    seed.add_argument("--input", type=Path)
    seed.add_argument("--config", type=Path)
    args = parser.parse_args(argv)

    engine = create_database_engine()
    if args.command == "migrate":
        result = {"applied": run_migrations(engine)}
    else:
        applied = run_migrations(engine)
        factory = create_session_factory(engine)
        result = {
            "applied": applied,
            "inserted_rows": seed_sample_data(
                factory,
                input_path=getattr(args, "input", None),
                config_path=getattr(args, "config", None),
            ),
        }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
