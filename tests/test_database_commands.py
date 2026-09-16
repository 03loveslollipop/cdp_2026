"""Database CLI dispatch stays explicit and never accepts passwords as arguments."""

from __future__ import annotations

import json

import pytest

from mlops_pipeline.src.deployment.database import __main__ as commands


@pytest.fixture
def cli_services(monkeypatch):
    engine = object()
    factory = object()
    calls = []
    monkeypatch.setattr(commands, "create_database_engine", lambda: engine)
    monkeypatch.setattr(commands, "create_session_factory", lambda actual: factory)
    monkeypatch.setattr(commands, "run_migrations", lambda actual: calls.append("migrate") or [1])
    monkeypatch.setattr(commands, "bootstrap_auth_users", lambda actual: 2)
    monkeypatch.setattr(commands, "seed_sample_data", lambda *args, **kwargs: 3)
    monkeypatch.setattr(commands, "list_users", lambda actual: [{"username": "owner"}])
    monkeypatch.setattr(
        commands, "create_user",
        lambda *args: calls.append(("create", args[1:])) or {"username": args[1]},
    )
    monkeypatch.setattr(
        commands, "reset_password",
        lambda *args: calls.append(("reset", args[1:])) or {"username": args[1]},
    )
    monkeypatch.setattr(
        commands, "set_role",
        lambda *args: calls.append(("role", args[1:])) or {"username": args[1]},
    )
    monkeypatch.setattr(
        commands, "set_active",
        lambda *args: calls.append(("active", args[1:])) or {"username": args[1]},
    )
    monkeypatch.setattr(commands, "_password", lambda: "entered-interactively")
    return calls


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (["migrate"], {"applied": [1]}),
        (["release"], {"applied": [1], "auth_users_inserted": 2, "inserted_rows": 3}),
        (["seed-sample", "--input", "sample.csv"], {"inserted_rows": 3}),
        (["users", "list"], {"users": [{"username": "owner"}]}),
        (["users", "create", "--username", "analyst"], {"user": {"username": "analyst"}}),
        (["users", "reset-password", "--username", "analyst"], {"user": {"username": "analyst"}}),
        (["users", "set-role", "--username", "analyst", "--role", "owner"], {"user": {"username": "analyst"}}),
        (["users", "enable", "--username", "analyst"], {"user": {"username": "analyst"}}),
        (["users", "disable", "--username", "analyst"], {"user": {"username": "analyst"}}),
    ],
)
def test_database_cli_dispatch(cli_services, capsys, arguments, expected):
    commands.main(arguments)
    assert json.loads(capsys.readouterr().out) == expected
    assert cli_services[0] == "migrate"
    if arguments[:2] == ["users", "create"]:
        assert cli_services[-1] == (
            "create", ("analyst", "entered-interactively", "inference")
        )
    if arguments[:2] == ["users", "disable"]:
        assert cli_services[-1] == ("active", ("analyst", False))


def test_password_confirmation_rejects_mismatch(monkeypatch):
    values = iter(["first", "second"])
    monkeypatch.setattr(commands.getpass, "getpass", lambda prompt: next(values))
    with pytest.raises(ValueError, match="Passwords do not match"):
        commands._password()
