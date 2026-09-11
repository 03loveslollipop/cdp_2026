"""Credential validation and asymmetric, short-lived JWT issuance."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ..settings import Settings


ALGORITHM = "EdDSA"
TOKEN_TTL_SECONDS = 2 * 60 * 60
TOKEN_COOKIE_NAME = "cdp_access_token"


class AuthRole(StrEnum):
    INFERENCE = "inference"
    OWNER = "owner"


@dataclass(frozen=True)
class Principal:
    username: str
    role: AuthRole
    expires_at: datetime


@dataclass(frozen=True)
class TokenGrant:
    token: str
    principal: Principal


class AuthenticationError(ValueError):
    """Raised for invalid credentials or tokens without leaking which check failed."""


class AuthService:
    def __init__(self, settings: Settings):
        settings.validate()
        self.settings = settings
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
        self.private_key = private_key
        self.public_key = public_key
        self.public_key_bytes = public_bytes
        self.key_id = hashlib.sha256(public_bytes).hexdigest()[:16]

    def login(self, username: str, password: str) -> TokenGrant:
        accounts = (
            (
                self.settings.auth_username or "",
                self.settings.auth_password or "",
                AuthRole.OWNER,
            ),
            (
                self.settings.inference_username or "",
                self.settings.inference_password or "",
                AuthRole.INFERENCE,
            ),
        )
        matched_role = None
        for expected_username, expected_password, role in accounts:
            username_valid = secrets.compare_digest(username, expected_username)
            password_valid = secrets.compare_digest(password, expected_password)
            if username_valid and password_valid:
                matched_role = role
        if matched_role is None:
            raise AuthenticationError("Invalid username or password")

        issued_at = datetime.now(UTC).replace(microsecond=0)
        expires_at = issued_at + timedelta(seconds=TOKEN_TTL_SECONDS)
        claims = {
            "sub": username,
            "role": matched_role.value,
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
            principal=Principal(username, matched_role, expires_at),
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
                    "require": ["sub", "role", "iss", "aud", "iat", "nbf", "exp", "jti"]
                },
            )
            role = AuthRole(claims["role"])
            expires_at = datetime.fromtimestamp(claims["exp"], tz=UTC)
            return Principal(str(claims["sub"]), role, expires_at)
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
            raise AuthenticationError("Invalid or expired access token") from error

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


def get_auth_service(application, settings: Settings) -> AuthService:
    service = getattr(application.state, "auth_service", None)
    if service is None:
        service = AuthService(settings)
        application.state.auth_service = service
    return service
