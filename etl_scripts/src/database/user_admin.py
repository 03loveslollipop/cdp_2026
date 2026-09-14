"""Transactional administration for database-backed application users."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from .passwords import hash_password, normalize_username, validate_role
from .repositories import AuthUserRepository


ADMIN_LOCK_NAME = "cdp_2026_auth_user_admin"


def _lock(session: Session) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:name))"),
        {"name": ADMIN_LOCK_NAME},
    )


def _summary(user) -> dict:
    def timestamp(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "active": user.active,
        "token_version": user.token_version,
        "last_login_at": timestamp(user.last_login_at),
        "created_at": timestamp(user.created_at),
        "updated_at": timestamp(user.updated_at),
    }


def list_users(factory: sessionmaker[Session]) -> list[dict]:
    with factory() as session:
        return [_summary(user) for user in AuthUserRepository(session).list_all()]


def create_user(
    factory: sessionmaker[Session],
    username: str,
    password: str,
    role: str,
) -> dict:
    normalized = normalize_username(username)
    validated_role = validate_role(role)
    password_hash = hash_password(password)
    with factory.begin() as session:
        _lock(session)
        repository = AuthUserRepository(session)
        if repository.by_username(normalized) is not None:
            raise ValueError(f"User already exists: {normalized}")
        return _summary(repository.create(normalized, password_hash, validated_role))


def reset_password(
    factory: sessionmaker[Session], username: str, password: str
) -> dict:
    normalized = normalize_username(username)
    password_hash = hash_password(password)
    with factory.begin() as session:
        _lock(session)
        repository = AuthUserRepository(session)
        user = repository.by_username(normalized)
        if user is None:
            raise ValueError(f"User does not exist: {normalized}")
        repository.set_password(user, password_hash)
        return _summary(user)


def set_role(factory: sessionmaker[Session], username: str, role: str) -> dict:
    normalized = normalize_username(username)
    validated_role = validate_role(role)
    with factory.begin() as session:
        _lock(session)
        repository = AuthUserRepository(session)
        user = repository.by_username(normalized)
        if user is None:
            raise ValueError(f"User does not exist: {normalized}")
        if (
            user.active
            and user.role == "owner"
            and validated_role != "owner"
            and repository.active_owner_count() == 1
        ):
            raise ValueError("Cannot demote the last active owner")
        repository.set_role(user, validated_role)
        return _summary(user)


def set_active(
    factory: sessionmaker[Session], username: str, active: bool
) -> dict:
    normalized = normalize_username(username)
    with factory.begin() as session:
        _lock(session)
        repository = AuthUserRepository(session)
        user = repository.by_username(normalized)
        if user is None:
            raise ValueError(f"User does not exist: {normalized}")
        if (
            user.active
            and not active
            and user.role == "owner"
            and repository.active_owner_count() == 1
        ):
            raise ValueError("Cannot disable the last active owner")
        repository.set_active(user, active)
        return _summary(user)
