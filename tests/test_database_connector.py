"""Database connectors use bounded pools and close sessions on either outcome."""

from __future__ import annotations

import pytest

from etl_scripts.src.database.connectors import postgres


def test_engine_configuration_uses_only_explicit_project_connection(monkeypatch):
    captured = {}

    def fake_create_engine(url, **options):
        captured.update(url=url, **options)
        return object()

    monkeypatch.setenv("CDP_DB_POOL_SIZE", "3")
    monkeypatch.setenv("CDP_DB_MAX_OVERFLOW", "1")
    monkeypatch.setattr(postgres, "create_engine", fake_create_engine)
    engine = postgres.create_database_engine("postgres://host/project")
    assert engine is not None
    assert captured["url"] == "postgresql+psycopg://host/project"
    assert captured["pool_size"] == 3
    assert captured["max_overflow"] == 1
    assert captured["connect_args"] == {"application_name": "cdp_2026"}
    assert postgres.create_session_factory(engine).kw["bind"] is engine


def test_session_scope_commits_or_rolls_back_then_always_closes():
    class Session:
        def __init__(self):
            self.calls = []

        def commit(self):
            self.calls.append("commit")

        def rollback(self):
            self.calls.append("rollback")

        def close(self):
            self.calls.append("close")

    successful = Session()
    with postgres.session_scope(lambda: successful) as session:
        assert session is successful
    assert successful.calls == ["commit", "close"]

    failing = Session()
    with pytest.raises(ValueError, match="failed"):
        with postgres.session_scope(lambda: failing):
            raise ValueError("failed")
    assert failing.calls == ["rollback", "close"]
