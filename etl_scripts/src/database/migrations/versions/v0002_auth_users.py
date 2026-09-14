"""Add database-backed users and prediction-request ownership."""

from pathlib import Path

from sqlalchemy import Connection, text


VERSION = "0002_auth_users"
SQL_PATH = Path(__file__).with_name("0002_auth_users.sql")


def upgrade(connection: Connection) -> None:
    for statement in SQL_PATH.read_text(encoding="utf-8").split("-- migrate:split"):
        if statement.strip():
            connection.execute(text(statement))
