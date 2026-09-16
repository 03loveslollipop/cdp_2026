"""Persistence operations for database-backed login identities."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AuthUser


class AuthUserRepository:
    def __init__(self, session: Session):
        self.session = session

    def by_id(self, user_id: str) -> AuthUser | None:
        return self.session.get(AuthUser, user_id)

    def by_username(self, username: str) -> AuthUser | None:
        return self.session.scalar(
            select(AuthUser).where(AuthUser.username == username)
        )

    def list_all(self) -> list[AuthUser]:
        return list(self.session.scalars(select(AuthUser).order_by(AuthUser.username)))

    def count(self) -> int:
        return int(self.session.scalar(select(func.count()).select_from(AuthUser)) or 0)

    def active_owner_count(self) -> int:
        return int(
            self.session.scalar(
                select(func.count()).select_from(AuthUser).where(
                    AuthUser.role == "owner",
                    AuthUser.active.is_(True),
                )
            )
            or 0
        )

    def create(self, username: str, password_hash: str, role: str) -> AuthUser:
        user = AuthUser(
            id=str(uuid4()),
            username=username,
            password_hash=password_hash,
            role=role,
            active=True,
            token_version=0,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def record_login(self, user: AuthUser, password_hash: str | None = None) -> None:
        if password_hash is not None:
            user.password_hash = password_hash
        now = datetime.now(UTC)
        user.last_login_at = now
        user.updated_at = now
        self.session.flush()

    def set_password(self, user: AuthUser, password_hash: str) -> None:
        user.password_hash = password_hash
        self._invalidate_tokens(user)

    def set_role(self, user: AuthUser, role: str) -> None:
        if user.role != role:
            user.role = role
            self._invalidate_tokens(user)

    def set_active(self, user: AuthUser, active: bool) -> None:
        if user.active != active:
            user.active = active
            self._invalidate_tokens(user)

    def _invalidate_tokens(self, user: AuthUser) -> None:
        user.token_version += 1
        user.updated_at = datetime.now(UTC)
        self.session.flush()
