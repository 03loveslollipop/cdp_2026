"""Create the isolated model-serving and monitoring tables."""

from pathlib import Path

from sqlalchemy import Connection, text


VERSION = "0001_initial"
SQL_PATH = Path(__file__).with_name("0001_initial.sql")


def upgrade(connection: Connection) -> None:
    for statement in SQL_PATH.read_text(encoding="utf-8").split("-- migrate:split"):
        if statement.strip():
            connection.execute(text(statement))
