"""Seed the default APPLICATION user at startup (idempotent).

If no user with ``APP_DEFAULT_USER_EMAIL`` exists, create one with a hashed
password and an initialised learning profile. This provides a ready-to-use
login AND guarantees at least one valid ``users`` row exists, acting as an extra
safeguard against dangling ``skill_progress`` foreign keys.

This is the application's own user — entirely separate from the Langfuse admin
account (which has its own provisioning in docker-compose).
"""
from __future__ import annotations

import logging

from app.auth.security import hash_password
from app.config import settings
from app.db.progress_repo import (
    create_user,
    ensure_user_profile,
    get_user_by_email,
)

logger = logging.getLogger(__name__)


def seed_default_user() -> None:
    email = settings.APP_DEFAULT_USER_EMAIL
    if not email:
        return
    existing = get_user_by_email(email)
    if existing is not None:
        # Still make sure its learning profile is seeded (FK safeguard).
        ensure_user_profile(existing["id"], existing.get("preferred_language"))
        logger.info("Default app user already present: %s", email)
        return

    user = create_user(
        email=email,
        password_hash=hash_password(settings.APP_DEFAULT_USER_PASSWORD),
        name=settings.APP_DEFAULT_USER_NAME,
        language=settings.APP_DEFAULT_USER_LANGUAGE,
    )
    if user is None:  # race / created concurrently
        existing = get_user_by_email(email)
        if existing:
            ensure_user_profile(existing["id"], existing.get("preferred_language"))
        return
    ensure_user_profile(user["id"], settings.APP_DEFAULT_USER_LANGUAGE)
    logger.info("Seeded default app user: %s", email)
