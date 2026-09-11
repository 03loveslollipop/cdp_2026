"""Database management commands used by release automation."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

from .connectors.postgres import create_database_engine, create_session_factory
from .auth_bootstrap import bootstrap_auth_users
from .migrations import run_migrations
from .seed import seed_sample_data
from .user_admin import create_user, list_users, reset_password, set_active, set_role


def _password() -> str:
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise ValueError("Passwords do not match")
    return first


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate")
    subparsers.add_parser("release")
    seed = subparsers.add_parser("seed-sample")
    seed.add_argument("--input", type=Path)
    seed.add_argument("--config", type=Path)
    users = subparsers.add_parser("users")
    user_commands = users.add_subparsers(dest="user_command", required=True)
    user_commands.add_parser("list")
    create = user_commands.add_parser("create")
    create.add_argument("--username", required=True)
    create.add_argument("--role", choices=("inference", "owner"), default="inference")
    reset = user_commands.add_parser("reset-password")
    reset.add_argument("--username", required=True)
    role = user_commands.add_parser("set-role")
    role.add_argument("--username", required=True)
    role.add_argument("--role", choices=("inference", "owner"), required=True)
    for command in ("enable", "disable"):
        user = user_commands.add_parser(command)
        user.add_argument("--username", required=True)
    args = parser.parse_args(argv)

    engine = create_database_engine()
    factory = create_session_factory(engine)
    if args.command == "migrate":
        result = {"applied": run_migrations(engine)}
    elif args.command == "release":
        applied = run_migrations(engine)
        result = {
            "applied": applied,
            "auth_users_inserted": bootstrap_auth_users(factory),
            "inserted_rows": seed_sample_data(
                factory,
            ),
        }
    elif args.command == "seed-sample":
        run_migrations(engine)
        result = {
            "inserted_rows": seed_sample_data(
                factory,
                input_path=args.input,
                config_path=args.config,
            )
        }
    else:
        run_migrations(engine)
        if args.user_command == "list":
            result = {"users": list_users(factory)}
        elif args.user_command == "create":
            result = {
                "user": create_user(factory, args.username, _password(), args.role)
            }
        elif args.user_command == "reset-password":
            result = {"user": reset_password(factory, args.username, _password())}
        elif args.user_command == "set-role":
            result = {"user": set_role(factory, args.username, args.role)}
        else:
            result = {
                "user": set_active(
                    factory, args.username, args.user_command == "enable"
                )
            }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
