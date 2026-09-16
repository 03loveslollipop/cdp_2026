"""Migration runner locks and checks checksums before applying schema changes."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from mlops_pipeline.src.deployment.database.migrations import runner
from mlops_pipeline.src.deployment.database.migrations.versions import v0001_initial


class Connection:
    def __init__(self, existing):
        self.existing = existing
        self.commands = []

    def execute(self, statement, parameters=None):
        self.commands.append((str(statement), parameters))
        if "SELECT version, checksum" in str(statement):
            return SimpleNamespace(all=lambda: list(self.existing.items()))
        return SimpleNamespace(all=lambda: [])


def test_migrations_apply_once_under_advisory_lock(monkeypatch):
    upgraded = []
    migrations = [
        SimpleNamespace(VERSION="v1", upgrade=lambda connection: upgraded.append("v1")),
        SimpleNamespace(VERSION="v2", upgrade=lambda connection: upgraded.append("v2")),
    ]
    monkeypatch.setattr(runner, "MIGRATIONS", migrations)
    monkeypatch.setattr(runner, "_checksum", lambda migration: migration.VERSION)
    connection = Connection({})
    engine = SimpleNamespace(begin=lambda: nullcontext(connection))
    assert runner.run_migrations(engine) == ["v1", "v2"]
    assert upgraded == ["v1", "v2"]
    assert "pg_advisory_xact_lock" in connection.commands[0][0]
    assert all(
        "cdp_2026" in sql for sql, _ in connection.commands[1:]
    )
    connection.existing = {"v1": "v1", "v2": "v2"}
    assert runner.run_migrations(engine) == []
    assert upgraded == ["v1", "v2"]


def test_migration_checksum_mismatch_stops_release(monkeypatch):
    migration = SimpleNamespace(VERSION="v1", upgrade=lambda connection: None)
    monkeypatch.setattr(runner, "MIGRATIONS", [migration])
    monkeypatch.setattr(runner, "_checksum", lambda candidate: "new")
    connection = Connection({"v1": "old"})
    with pytest.raises(RuntimeError, match="Applied migration changed"):
        runner.run_migrations(SimpleNamespace(begin=lambda: nullcontext(connection)))


def test_frozen_migration_checksum_is_stable():
    assert len(runner._checksum(v0001_initial)) == 64
