"""Password hashing and JWT helpers for application authentication.

Uses passlib[bcrypt] for password hashing and PyJWT for signing/verifying
short-lived access tokens. Secret and TTL come from ``app.config.settings``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

from app.config import settings

# bcrypt has a 72-byte input limit; passlib raises on longer inputs. We rely on
# the default scheme and let passlib handle truncation semantics consistently.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return a bcrypt hash for the given plaintext password."""
    # bcrypt only considers the first 72 bytes; truncate defensively so very
    # long passwords don't raise inside the backend.
    return _pwd_context.hash(password[:72])


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    if not password_hash:
        return False
    try:
        return _pwd_context.verify(password[:72], password_hash)
    except Exception:  # noqa: BLE001 — malformed hash, etc.
        return False


def create_access_token(
    subject: str, extra_claims: dict[str, Any] | None = None
) -> str:
    """Create a signed JWT access token for the given subject (user id).

    ``subject`` becomes the ``sub`` claim. Additional claims (e.g. email) may be
    attached via ``extra_claims``.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode + verify a JWT. Returns the claims dict, or None if invalid."""
    try:
        return jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError:
        return None
