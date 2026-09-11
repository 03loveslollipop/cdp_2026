"""Checksum-verified, advisory-locked PostgreSQL migrations."""

from __future__ import annotations

import hashlib
import inspect

from sqlalchemy import Engine, text

from ..connectors.postgres import SCHEMA_NAME
from .versions import v0001_initial


MIGRATIONS = (v0001_initial,)
LOCK_NAME = "cdp_2026_schema_migrations"


def _checksum(module: object) -> str:
    digest = hashlib.sha256(inspect.getsource(module).encode("utf-8"))
    sql_path = getattr(module, "SQL_PATH", None)
    if sql_path is not None:
        digest.update(sql_path.read_bytes())
    return digest.hexdigest()


def run_migrations(engine: Engine) -> list[str]:
    applied_now: list[str] = []
    with engine.begin() as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:name))"),
            {"name": LOCK_NAME},
        )
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA_NAME}"'))
        connection.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.schema_migrations (
                version VARCHAR(128) PRIMARY KEY,
                checksum VARCHAR(64) NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        existing = dict(connection.execute(text(
            f"SELECT version, checksum FROM {SCHEMA_NAME}.schema_migrations"
        )).all())
        for migration in MIGRATIONS:
            checksum = _checksum(migration)
            old_checksum = existing.get(migration.VERSION)
            if old_checksum is not None:
                if old_checksum != checksum:
                    raise RuntimeError(
                        f"Applied migration changed: {migration.VERSION}"
                    )
                continue
            migration.upgrade(connection)
            connection.execute(text(f"""
                INSERT INTO {SCHEMA_NAME}.schema_migrations (version, checksum)
                VALUES (:version, :checksum)
            """), {"version": migration.VERSION, "checksum": checksum})
            applied_now.append(migration.VERSION)
    return applied_now
