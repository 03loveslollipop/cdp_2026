"""Clients and contracts shared between independently deployed services."""

from .contracts import (
    AuthRole,
    AuthenticationError,
    AuthServiceUnavailable,
    Principal,
)

__all__ = [
    "AuthRole",
    "AuthenticationError",
    "AuthServiceUnavailable",
    "Principal",
]
