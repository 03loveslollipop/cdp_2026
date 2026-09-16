"""The approved sample importer preserves nulls and stable row identities."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import UTC, datetime

import pytest

from mlops_pipeline.src.deployment.database import seed


def write_source(tmp_path, csv_text):
    config = {
        "paths": {"raw_data": "sample.csv"},
        "predictive_pipeline": {
            "required_predictors": ["amount", "kind"],
            "train_test_split": {"timestamp_column": "created"},
        },
        "schema": {"target": "Pago_atiempo"},
        "null_tokens": ["", "NA"],
        "read_csv": {"encoding": "utf-8", "sep": ","},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / "sample.csv").write_text(csv_text, encoding="utf-8")
    return config_path


def test_sample_seed_preserves_nulls_and_stable_hashes(monkeypatch, tmp_path):
    config_path = write_source(
        tmp_path,
        "amount,kind,created,Pago_atiempo\n"
        "10,NA,12/09/2026 18:30,0\n"
        "20,retail,2026-09-13T10:00:00,1\n",
    )
    captured = []

    class Repository:
        def __init__(self, _session):
            pass

        def insert_missing(self, rows):
            captured.append(rows)
            return len(rows)

    class Factory:
        def begin(self):
            return nullcontext(object())

    monkeypatch.setattr(seed, "SampleRepository", Repository)
    assert seed.seed_sample_data(Factory(), config_path=config_path) == 2
    assert seed.seed_sample_data(Factory(), config_path=config_path) == 2
    assert captured[0] == captured[1]
    assert captured[0][0]["predictors"] == {"amount": "10", "kind": None}
    assert captured[0][0]["target"] == 0
    assert captured[0][0]["loan_timestamp"] == datetime(
        2026, 9, 12, 18, 30, tzinfo=UTC
    )
    assert captured[0][0]["source_row_hash"] != captured[0][1]["source_row_hash"]


@pytest.mark.parametrize(
    "csv_text,reason",
    [
        ("kind,created,Pago_atiempo\nretail,12/09/2026,0\n", "missing predictor"),
        ("amount,kind,created,Pago_atiempo\n10,retail,12/09/2026,2\n", "Invalid sample target"),
        ("amount,kind,created,Pago_atiempo\n10,retail,bad-date,0\n", "Unsupported sample timestamp"),
    ],
)
def test_sample_seed_rejects_invalid_source(tmp_path, csv_text, reason):
    config_path = write_source(tmp_path, csv_text)
    with pytest.raises(ValueError, match=reason):
        seed.seed_sample_data(None, config_path=config_path)


def test_supported_sample_timestamp_forms():
    assert seed._timestamp("13/09/2026") == datetime(2026, 9, 13, tzinfo=UTC)
    assert seed._timestamp("2026-09-13T09:15:20") == datetime(
        2026, 9, 13, 9, 15, 20, tzinfo=UTC
    )
