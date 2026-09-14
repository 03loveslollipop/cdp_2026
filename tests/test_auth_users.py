from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from etl_scripts.src.database.auth_bootstrap import bootstrap_auth_users
from etl_scripts.src.database.passwords import (
    hash_password,
    normalize_username,
    verify_password,
)
from etl_scripts.src.database.user_admin import reset_password, set_active


class FakeSessionContext:
    def __init__(self, users):
        self.session = SimpleNamespace(users=users, execute=lambda *_args, **_kwargs: None)

    def __enter__(self):
        return self.session

    def __exit__(self, *_args):
        return False


class FakeSessionFactory:
    def __init__(self):
        self.users = {}

    def __call__(self):
        return FakeSessionContext(self.users)

    def begin(self):
        return FakeSessionContext(self.users)


class FakeAuthUserRepository:
    def __init__(self, session):
        self.users = session.users

    def by_id(self, user_id):
        return next((user for user in self.users.values() if user.id == user_id), None)

    def by_username(self, username):
        return self.users.get(username)

    def list_all(self):
        return list(self.users.values())

    def count(self):
        return len(self.users)

    def active_owner_count(self):
        return sum(
            user.active and user.role == "owner" for user in self.users.values()
        )

    def create(self, username, password_hash, role):
        now = datetime.now(UTC)
        user = SimpleNamespace(
            id=str(uuid4()),
            username=username,
            password_hash=password_hash,
            role=role,
            active=True,
            token_version=0,
            last_login_at=None,
            created_at=now,
            updated_at=now,
        )
        self.users[username] = user
        return user

    def set_password(self, user, password_hash):
        user.password_hash = password_hash
        user.token_version += 1

    def set_active(self, user, active):
        if user.active != active:
            user.active = active
            user.token_version += 1


@pytest.fixture
def fake_database(monkeypatch):
    monkeypatch.setattr(
        "etl_scripts.src.database.auth_bootstrap.AuthUserRepository",
        FakeAuthUserRepository,
    )
    monkeypatch.setattr(
        "etl_scripts.src.database.user_admin.AuthUserRepository",
        FakeAuthUserRepository,
    )
    return FakeSessionFactory()


def test_passwords_are_argon2id_hashes_and_usernames_are_canonical():
    password_hash = hash_password("a-secure-password")
    assert password_hash.startswith("$argon2id$")
    assert "a-secure-password" not in password_hash
    assert verify_password(password_hash, "a-secure-password")[0]
    assert not verify_password(password_hash, "wrong-password")[0]
    assert normalize_username("  OWNER.User  ") == "owner.user"
    with pytest.raises(ValueError, match="Password"):
        hash_password("too-short")


def test_release_bootstrap_is_idempotent_and_never_stores_plaintext(fake_database):
    environment = {
        "CDP_AUTH_USERNAME": "Owner.User",
        "CDP_AUTH_PASSWORD": "owner-password",
        "CDP_INFERENCE_USERNAME": "Inference.User",
        "CDP_INFERENCE_PASSWORD": "inference-password",
    }
    assert bootstrap_auth_users(fake_database, environment) == 2
    assert bootstrap_auth_users(fake_database, environment) == 0
    owner = fake_database.users["owner.user"]
    assert owner.role == "owner"
    assert owner.password_hash != environment["CDP_AUTH_PASSWORD"]
    assert verify_password(owner.password_hash, environment["CDP_AUTH_PASSWORD"])[0]


def test_password_reset_invalidates_tokens_and_last_owner_is_protected(fake_database):
    bootstrap_auth_users(
        fake_database,
        {
            "CDP_AUTH_USERNAME": "owner-user",
            "CDP_AUTH_PASSWORD": "owner-password",
        },
    )
    summary = reset_password(fake_database, "owner-user", "replacement-password")
    assert summary["token_version"] == 1
    assert verify_password(
        fake_database.users["owner-user"].password_hash,
        "replacement-password",
    )[0]
    with pytest.raises(ValueError, match="last active owner"):
        set_active(fake_database, "owner-user", False)


def test_bootstrap_rejects_partial_or_duplicate_accounts(fake_database):
    with pytest.raises(RuntimeError, match="supplied together"):
        bootstrap_auth_users(fake_database, {"CDP_AUTH_USERNAME": "owner-user"})
    with pytest.raises(RuntimeError, match="must be different"):
        bootstrap_auth_users(
            fake_database,
            {
                "CDP_AUTH_USERNAME": "same-user",
                "CDP_AUTH_PASSWORD": "owner-password",
                "CDP_INFERENCE_USERNAME": "SAME-USER",
                "CDP_INFERENCE_PASSWORD": "inference-password",
            },
        )
