"""Load the approved CSV sample into its isolated table idempotently."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from .repositories import SampleRepository


DEFAULT_CONFIG_PATH = Path(__file__).parents[1] / "config.json"


def _timestamp(value: str) -> datetime:
    cleaned = value.strip()
    for pattern in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(cleaned, pattern).replace(tzinfo=UTC)
        except ValueError:
            pass
    raise ValueError(f"Unsupported sample timestamp: {cleaned!r}")


def seed_sample_data(
    factory: sessionmaker,
    *,
    input_path: Path | None = None,
    config_path: Path | None = None,
) -> int:
    resolved_config = config_path or DEFAULT_CONFIG_PATH
    config = json.loads(resolved_config.read_text(encoding="utf-8"))
    if input_path is None:
        input_path = (resolved_config.parent / config["paths"]["raw_data"]).resolve()
    required = config["predictive_pipeline"]["required_predictors"]
    target_name = config["schema"]["target"]
    timestamp_name = config["predictive_pipeline"]["train_test_split"]["timestamp_column"]
    null_tokens = {str(value).strip() for value in config["null_tokens"]}
    with input_path.open("r", encoding=config["read_csv"]["encoding"], newline="") as stream:
        reader = csv.DictReader(stream, delimiter=config["read_csv"]["sep"])
        source_rows = list(reader)
        canonical = io.StringIO(newline="")
        writer = csv.DictWriter(
            canonical,
            fieldnames=reader.fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(source_rows)
    # Match ``read_raw_data(...).to_csv(index=False)`` so the release seeder is
    # idempotent with artifacts and sample rows produced by the training runtime.
    dataset_hash = hashlib.sha256(canonical.getvalue().encode("utf-8")).hexdigest()
    rows = []
    for index, source in enumerate(source_rows):
        missing = [column for column in required if column not in source]
        if missing:
            raise ValueError(f"Sample CSV is missing predictor columns: {missing}")
        target = int(source[target_name].strip())
        if target not in (0, 1):
            raise ValueError(f"Invalid sample target at row {index}")
        predictors = {
            column: (
                None if source[column].strip() in null_tokens
                else source[column].strip()
            )
            for column in required
        }
        rows.append({
            "source_row_hash": hashlib.sha256(
                f"{dataset_hash}:{index}".encode("utf-8")
            ).hexdigest(),
            "predictors": predictors,
            "target": target,
            "loan_timestamp": _timestamp(source[timestamp_name]),
        })
    with factory.begin() as session:
        return SampleRepository(session).insert_missing(rows)
