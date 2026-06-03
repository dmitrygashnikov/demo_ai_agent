"""Application authentication endpoints: register, login, me.

Registration is OPEN to everyone — there is NO email verification step. On
registration the user's learning profile is initialised immediately
(``ensure_user_profile``) so that downstream LangGraph nodes never hit a
``skill_progress`` foreign-key error.

This is the APPLICATION's own auth, completely separate from Langfuse.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.auth.deps import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.config import settings
from app.db.progress_repo import (
    create_user,
    ensure_user_profile,
    get_user_by_email,
)

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None
    preferred_language: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


def _issue_token(user: dict) -> TokenResponse:
    token = create_access_token(
        subject=user["id"], extra_claims={"email": user.get("email")}
    )
    return TokenResponse(access_token=token, user=user)


@auth_router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest):
    """Open registration (no email verification). Initialises learning profile."""
    if len(req.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters",
        )
    language = req.preferred_language or settings.APP_DEFAULT_USER_LANGUAGE
    user = create_user(
        email=str(req.email),
        password_hash=hash_password(req.password),
        name=req.name,
        language=language,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    # CRITICAL: seed the learning profile right away so the very first chat/code
    # turn cannot trigger a skill_progress FK error.
    ensure_user_profile(user["id"], language)
    logger.info("Registered user %s (%s)", user["id"], user["email"])
    return _issue_token(user)


@auth_router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """Authenticate by email + password, returning a JWT and the user record."""
    record = get_user_by_email(str(req.email))
    if record is None or not verify_password(req.password, record.get("password_hash") or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    # Defensive: ensure the profile exists (older rows / safety against FK).
    ensure_user_profile(record["id"], record.get("preferred_language"))
    public = {k: v for k, v in record.items() if k != "password_hash"}
    return _issue_token(public)


@auth_router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return current_user
