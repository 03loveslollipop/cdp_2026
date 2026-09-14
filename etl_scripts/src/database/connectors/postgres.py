"""PostgreSQL engine and transaction helpers.

The shared Essential-tier credential can access unrelated schemas. Application code
therefore uses ORM tables whose schema is fixed to ``cdp_2026`` and never changes the
connection search path.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


SCHEMA_NAME = "cdp_2026"


def database_url(explicit_url: str | None = None) -> str:
    value = explicit_url or os.getenv("CDP_DATABASE_URL")
    if not value:
        raise RuntimeError("CDP_DATABASE_URL is required")
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    if not value.startswith("postgresql+psycopg://"):
        raise ValueError("CDP_DATABASE_URL must be a PostgreSQL URL")
    return value


def create_database_engine(explicit_url: str | None = None) -> Engine:
    return create_engine(
        database_url(explicit_url),
        pool_pre_ping=True,
        pool_size=int(os.getenv("CDP_DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("CDP_DB_MAX_OVERFLOW", "2")),
        pool_recycle=300,
        connect_args={"application_name": "cdp_2026"},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
