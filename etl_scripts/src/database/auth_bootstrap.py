"""One-time migration of configured credentials into PostgreSQL hashes."""

from __future__ import annotations

import os
from collections.abc import Mapping

from sqlalchemy.orm import Session, sessionmaker

from .passwords import hash_password, normalize_username
from .repositories import AuthUserRepository


BOOTSTRAP_ACCOUNTS = (
    ("CDP_AUTH_USERNAME", "CDP_AUTH_PASSWORD", "owner"),
    ("CDP_INFERENCE_USERNAME", "CDP_INFERENCE_PASSWORD", "inference"),
)


def bootstrap_auth_users(
    factory: sessionmaker[Session],
    environment: Mapping[str, str] | None = None,
) -> int:
    values = environment if environment is not None else os.environ
    configured_accounts = []
    for username_name, password_name, role in BOOTSTRAP_ACCOUNTS:
        username = values.get(username_name)
        password = values.get(password_name)
        if bool(username) != bool(password):
            raise RuntimeError(
                f"{username_name} and {password_name} must be supplied together"
            )
        if username and password:
            configured_accounts.append(
                (normalize_username(username), password, role)
            )
    usernames = [username for username, _password, _role in configured_accounts]
    if len(set(usernames)) != len(usernames):
        raise RuntimeError("Bootstrap account usernames must be different")

    inserted = 0
    with factory.begin() as session:
        repository = AuthUserRepository(session)
        for username, password, role in configured_accounts:
            existing = repository.by_username(username)
            if existing is not None:
                continue
            repository.create(username, hash_password(password), role)
            inserted += 1
        if repository.count() == 0:
            raise RuntimeError(
                "No auth users exist; supply bootstrap owner credentials once"
            )
        if repository.active_owner_count() == 0:
            raise RuntimeError("At least one active owner user is required")
    return inserted
