import pytest

from mlops_pipeline.src.deployment.database.connectors.postgres import (
    SCHEMA_NAME,
    database_url,
)
from mlops_pipeline.src.deployment.database.migrations.versions import v0001_initial, v0002_auth_users
from mlops_pipeline.src.deployment.database.models import Base


def test_all_application_tables_and_foreign_keys_are_schema_qualified():
    assert SCHEMA_NAME == "cdp_2026"
    assert Base.metadata.tables
    for table in Base.metadata.tables.values():
        assert table.schema == SCHEMA_NAME
        for foreign_key in table.foreign_keys:
            assert foreign_key.target_fullname.startswith(f"{SCHEMA_NAME}.")


def test_migrations_are_frozen_schema_qualified_snapshots():
    initial_source = v0001_initial.SQL_PATH.read_text(encoding="utf-8")
    auth_source = v0002_auth_users.SQL_PATH.read_text(encoding="utf-8")
    migration_source = initial_source + auth_source
    assert "Base.metadata" not in v0001_initial.upgrade.__code__.co_names
    assert "Base.metadata" not in v0002_auth_users.upgrade.__code__.co_names
    for table in Base.metadata.tables.values():
        assert f"CREATE TABLE {SCHEMA_NAME}.{table.name}" in migration_source
    assert f"CREATE TABLE {SCHEMA_NAME}.auth_users" not in initial_source
    assert "CREATE TABLE public." not in migration_source


def test_database_url_accepts_only_explicit_postgres(monkeypatch):
    monkeypatch.delenv("CDP_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="CDP_DATABASE_URL"):
        database_url()
    assert database_url("postgres://host/db") == "postgresql+psycopg://host/db"
    assert database_url("postgresql://host/db") == "postgresql+psycopg://host/db"
    with pytest.raises(ValueError, match="PostgreSQL"):
        database_url("sqlite:///tmp.db")
