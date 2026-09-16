"""Argon2id password hashing policy shared by bootstrap and login."""

from __future__ import annotations

import re

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .models import AUTH_ROLES


MINIMUM_PASSWORD_LENGTH = 12
MAXIMUM_PASSWORD_LENGTH = 512
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._@+-]{2,127}$")
PASSWORD_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19 * 1024,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def normalize_username(username: str) -> str:
    normalized = username.strip().casefold()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Username must be 3-128 lower-case letters, digits, or . _ @ + -"
        )
    return normalized


def validate_role(role: str) -> str:
    if role not in AUTH_ROLES:
        raise ValueError(f"Role must be one of {AUTH_ROLES}")
    return role


def validate_password(password: str) -> None:
    if not MINIMUM_PASSWORD_LENGTH <= len(password) <= MAXIMUM_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must contain {MINIMUM_PASSWORD_LENGTH}-"
            f"{MAXIMUM_PASSWORD_LENGTH} characters"
        )


def hash_password(password: str) -> str:
    validate_password(password)
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> tuple[bool, bool]:
    try:
        valid = PASSWORD_HASHER.verify(password_hash, password)
    except VerifyMismatchError:
        return False, False
    except (InvalidHashError, VerificationError) as error:
        raise RuntimeError("Stored password hash is invalid") from error
    return bool(valid), PASSWORD_HASHER.check_needs_rehash(password_hash)
