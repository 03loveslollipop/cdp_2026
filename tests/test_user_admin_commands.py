"""User administration preserves the final active owner and token invalidation."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from etl_scripts.src.database import user_admin


def user(username="owner", role="owner", active=True):
    return SimpleNamespace(
        id="user-1", username=username, role=role, active=active,
        token_version=0, last_login_at=None,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
        updated_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def services(monkeypatch, existing=None, owner_count=1):
    state = {"user": existing, "owner_count": owner_count, "locks": 0}

    class Session:
        def execute(self, statement, parameters):
            assert parameters == {"name": user_admin.ADMIN_LOCK_NAME}
            state["locks"] += 1

    class Factory:
        def __call__(self):
            return nullcontext(Session())

        def begin(self):
            return nullcontext(Session())

    class Repository:
        def __init__(self, session):
            pass

        def list_all(self):
            return [state["user"]] if state["user"] else []

        def by_username(self, username):
            return state["user"]

        def create(self, username, password_hash, role):
            state["user"] = user(username, role)
            return state["user"]

        def set_password(self, value, password_hash):
            value.token_version += 1

        def active_owner_count(self):
            return state["owner_count"]

        def set_role(self, value, role):
            value.role = role
            value.token_version += 1

        def set_active(self, value, active):
            value.active = active
            value.token_version += 1

    monkeypatch.setattr(user_admin, "AuthUserRepository", Repository)
    monkeypatch.setattr(user_admin, "hash_password", lambda password: "hashed")
    return Factory(), state


def test_create_list_and_reset_password(monkeypatch):
    factory, state = services(monkeypatch)
    created = user_admin.create_user(factory, "Analyst", "safe-password", "inference")
    assert created["username"] == "analyst"
    assert created["role"] == "inference"
    assert created["created_at"].startswith("2026-09-01")
    assert user_admin.list_users(factory)[0]["id"] == "user-1"
    with pytest.raises(ValueError, match="already exists"):
        user_admin.create_user(factory, "Analyst", "safe-password", "inference")
    assert user_admin.reset_password(factory, "Analyst", "new-password")["token_version"] == 1
    assert state["locks"] == 3


def test_missing_users_and_final_owner_are_protected(monkeypatch):
    factory, _ = services(monkeypatch)
    with pytest.raises(ValueError, match="does not exist"):
        user_admin.reset_password(factory, "missing", "password")
    with pytest.raises(ValueError, match="does not exist"):
        user_admin.set_role(factory, "missing", "owner")
    with pytest.raises(ValueError, match="does not exist"):
        user_admin.set_active(factory, "missing", False)

    factory, state = services(monkeypatch, existing=user())
    with pytest.raises(ValueError, match="last active owner"):
        user_admin.set_role(factory, "owner", "inference")
    with pytest.raises(ValueError, match="last active owner"):
        user_admin.set_active(factory, "owner", False)
    assert state["user"].role == "owner"
    assert state["user"].active


def test_role_and_active_changes_work_with_another_owner(monkeypatch):
    factory, state = services(monkeypatch, existing=user(), owner_count=2)
    assert user_admin.set_role(factory, "owner", "inference")["role"] == "inference"
    assert user_admin.set_active(factory, "owner", False)["active"] is False
    assert state["user"].token_version == 2
