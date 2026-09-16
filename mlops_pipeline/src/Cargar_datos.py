"""Inspect the configured raw credit dataset without fitting a model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ft_engineering import DEFAULT_CONFIG_PATH, load_config, read_raw_data


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--input", type=Path)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    data_path = args.input or (args.config.parent / config["paths"]["raw_data"])
    raw_data = read_raw_data(config, data_path)
    print(json.dumps({"rows": len(raw_data), "columns": list(raw_data.columns)}, indent=2))


if __name__ == "__main__":
    main()
