"""PostgreSQL credentials, asymmetric JWT issuance, and token validation."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from sqlalchemy.orm import Session, sessionmaker

from ...database.passwords import hash_password, normalize_username, verify_password
from ...database.repositories import AuthUserRepository
from ...service_clients.contracts import (
    AuthRole,
    AuthenticationError,
    Principal,
    TOKEN_TTL_SECONDS,
)
from ..settings import AuthSettings


ALGORITHM = "EdDSA"


@dataclass(frozen=True)
class TokenGrant:
    token: str
    principal: Principal


class AuthService:
    def __init__(
        self,
        settings: AuthSettings,
        session_factory: sessionmaker[Session],
    ):
        settings.validate()
        self.settings = settings
        self.session_factory = session_factory
        try:
            private_key = serialization.load_pem_private_key(
                (settings.jwt_private_key or "").encode("utf-8"), password=None
            )
            public_key = serialization.load_pem_public_key(
                (settings.jwt_public_key or "").encode("utf-8")
            )
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                "JWT keys must be valid unencrypted PEM values"
            ) from error
        if not isinstance(private_key, Ed25519PrivateKey) or not isinstance(
            public_key, Ed25519PublicKey
        ):
            raise RuntimeError("JWT keys must be an Ed25519 key pair")
        private_public = private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        public_bytes = public_key.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        if not secrets.compare_digest(private_public, public_bytes):
            raise RuntimeError("JWT private and public keys do not match")
        with session_factory() as session:
            if AuthUserRepository(session).active_owner_count() == 0:
                raise RuntimeError("At least one active owner user is required")
        self.private_key = private_key
        self.public_key = public_key
        self.public_key_bytes = public_bytes
        self.key_id = hashlib.sha256(public_bytes).hexdigest()[:16]
        self._dummy_password_hash = hash_password(secrets.token_urlsafe(32))

    def login(self, username: str, password: str) -> TokenGrant:
        try:
            normalized_username = normalize_username(username)
        except ValueError:
            normalized_username = None

        with self.session_factory.begin() as session:
            repository = AuthUserRepository(session)
            user = (
                repository.by_username(normalized_username)
                if normalized_username is not None
                else None
            )
            candidate_hash = (
                user.password_hash if user is not None else self._dummy_password_hash
            )
            valid, needs_rehash = verify_password(candidate_hash, password)
            if user is None or not user.active or not valid:
                raise AuthenticationError("Invalid username or password")
            replacement_hash = hash_password(password) if needs_rehash else None
            repository.record_login(user, replacement_hash)
            user_id = user.id
            stored_username = user.username
            role = AuthRole(user.role)
            token_version = user.token_version

        issued_at = datetime.now(UTC).replace(microsecond=0)
        expires_at = issued_at + timedelta(seconds=TOKEN_TTL_SECONDS)
        claims = {
            "sub": user_id,
            "username": stored_username,
            "role": role.value,
            "ver": token_version,
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
            "iat": issued_at,
            "nbf": issued_at,
            "exp": expires_at,
            "jti": str(uuid4()),
        }
        token = jwt.encode(
            claims,
            self.private_key,
            algorithm=ALGORITHM,
            headers={"kid": self.key_id, "typ": "JWT"},
        )
        return TokenGrant(
            token=token,
            principal=Principal(
                user_id,
                stored_username,
                role,
                token_version,
                expires_at,
            ),
        )

    def authenticate_token(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != ALGORITHM or header.get("kid") != self.key_id:
                raise AuthenticationError("Invalid access token")
            claims = jwt.decode(
                token,
                self.public_key,
                algorithms=[ALGORITHM],
                audience=self.settings.jwt_audience,
                issuer=self.settings.jwt_issuer,
                options={
                    "require": [
                        "sub",
                        "username",
                        "role",
                        "ver",
                        "iss",
                        "aud",
                        "iat",
                        "nbf",
                        "exp",
                        "jti",
                    ]
                },
            )
            role = AuthRole(claims["role"])
            token_version = claims["ver"]
            if (
                not isinstance(token_version, int)
                or isinstance(token_version, bool)
                or token_version < 0
            ):
                raise AuthenticationError("Invalid access token")
            expires_at = datetime.fromtimestamp(claims["exp"], tz=UTC)
            user_id = str(claims["sub"])
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
            raise AuthenticationError("Invalid or expired access token") from error

        with self.session_factory() as session:
            user = AuthUserRepository(session).by_id(user_id)
            if (
                user is None
                or not user.active
                or user.token_version != token_version
                or user.role != role.value
            ):
                raise AuthenticationError("Invalid or expired access token")
            return Principal(
                user.id,
                user.username,
                AuthRole(user.role),
                user.token_version,
                expires_at,
            )

    def jwks(self) -> dict:
        encoded_key = base64.urlsafe_b64encode(self.public_key_bytes).rstrip(b"=")
        return {
            "keys": [
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": encoded_key.decode("ascii"),
                    "use": "sig",
                    "alg": ALGORITHM,
                    "kid": self.key_id,
                }
            ]
        }
