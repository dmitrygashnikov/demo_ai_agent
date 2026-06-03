"""FastAPI authentication dependencies.

``get_current_user`` extracts and validates the Bearer JWT from the
Authorization header and returns the corresponding user record. WebSocket
connections cannot use this dependency (no header parsing on accept), so they
use ``authenticate_token`` directly with a token from a query param / first
message.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.security import decode_access_token
from app.db.progress_repo import get_user_by_id

_bearer = HTTPBearer(auto_error=False)


def authenticate_token(token: str | None) -> dict | None:
    """Validate a raw JWT string and return the user dict, or None."""
    if not token:
        return None
    claims = decode_access_token(token)
    if not claims:
        return None
    user_id = claims.get("sub")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Resolve the authenticated user from the Bearer token, or raise 401."""
    token = credentials.credentials if credentials else None
    user = authenticate_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
