"""Repository helpers for user profile and skill progress."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Attempt, SkillProgress, User
from app.db.session import get_session

logger = logging.getLogger(__name__)


def get_or_create_user(user_id: str, language: str | None = None) -> dict:
    with get_session() as session:
        user = session.get(User, user_id)
        if user is None:
            user = User(id=user_id, preferred_language=language)
            session.add(user)
            session.flush()
        if language:
            user.preferred_language = language
        return {
            "id": user.id,
            "solve_count": user.solve_count,
            "preferred_language": user.preferred_language,
        }


def _ensure_user_row(session: Session, user_id: str, language: str | None = None) -> User:
    """Get-or-create the ``users`` row inside an existing session.

    This is the cornerstone of the skill_progress FK fix: any code path that is
    about to write a row referencing ``users.id`` calls this first, guaranteeing
    the parent row exists. Idempotent.
    """
    user = session.get(User, user_id)
    if user is None:
        user = User(id=user_id, preferred_language=language)
        session.add(user)
        session.flush()
    elif language and not user.preferred_language:
        user.preferred_language = language
    return user


def ensure_user_profile(user_id: str, language: str | None = None) -> dict:
    """Idempotently ensure a user exists AND has a seeded learning profile.

    Creates the ``users`` row if missing and lazily seeds initial
    ``skill_progress`` rows (state ``introducing``) for the first few skills of
    the chosen language. Safe to call repeatedly (register/login, graph start)
    — existing rows are left untouched. This is what prevents the
    ``skill_progress`` foreign-key error from ever occurring, even if a chat
    turn happens before ``/api/goal``.
    """
    from app.db.skill_graph import skills_for_language

    lang = language or "python"
    with get_session() as session:
        user = _ensure_user_row(session, user_id, lang)

        # Seed initial skill_progress rows for the first skills of the language
        # so downstream graph nodes always find a parent user + can update.
        skills = sorted(
            skills_for_language(lang), key=lambda s: s.order_index
        )[:3]
        existing = {
            sp.skill_id
            for sp in session.execute(
                select(SkillProgress).where(SkillProgress.user_id == user_id)
            ).scalars()
        }
        for sd in skills:
            if sd.id not in existing:
                session.add(
                    SkillProgress(
                        user_id=user_id, skill_id=sd.id, state="introducing"
                    )
                )
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "solve_count": user.solve_count,
            "preferred_language": user.preferred_language,
        }


def create_user(
    email: str,
    password_hash: str,
    name: str | None = None,
    language: str | None = None,
    user_id: str | None = None,
) -> dict | None:
    """Create a new authenticated user. Returns the user dict, or None if the
    email is already taken (caller should surface a 409)."""
    import uuid as _uuid

    with get_session() as session:
        existing = session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        if existing is not None:
            return None
        user = User(
            id=user_id or str(_uuid.uuid4()),
            email=email,
            password_hash=password_hash,
            name=name,
            preferred_language=language,
        )
        session.add(user)
        session.flush()
        return _user_public(user)


def get_user_by_email(email: str) -> dict | None:
    """Return the full user record (incl. password_hash) by email, or None."""
    with get_session() as session:
        user = session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        if user is None:
            return None
        data = _user_public(user)
        data["password_hash"] = user.password_hash
        return data


def get_user_by_id(user_id: str) -> dict | None:
    """Return the public user record by id, or None."""
    with get_session() as session:
        user = session.get(User, user_id)
        return _user_public(user) if user else None


def _user_public(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "solve_count": user.solve_count,
        "preferred_language": user.preferred_language,
    }


def increment_solve_count(user_id: str) -> int:
    with get_session() as session:
        user = session.get(User, user_id)
        if user is None:
            user = User(id=user_id, solve_count=0)
            session.add(user)
            session.flush()
        user.solve_count += 1
        return user.solve_count


def get_solve_count(user_id: str) -> int:
    with get_session() as session:
        user = session.get(User, user_id)
        return user.solve_count if user else 0


def get_or_create_progress(user_id: str, skill_id: str) -> dict:
    with get_session() as session:
        # FK safety: ensure the parent users row exists before inserting a
        # skill_progress row that references it.
        _ensure_user_row(session, user_id)
        row = session.execute(
            select(SkillProgress).where(
                SkillProgress.user_id == user_id, SkillProgress.skill_id == skill_id
            )
        ).scalar_one_or_none()
        if row is None:
            row = SkillProgress(user_id=user_id, skill_id=skill_id, state="introducing")
            session.add(row)
            session.flush()
        return _progress_dict(row)


def update_progress(user_id: str, skill_id: str, **fields) -> dict:
    with get_session() as session:
        # FK safety: ensure the parent users row exists first.
        _ensure_user_row(session, user_id)
        row = session.execute(
            select(SkillProgress).where(
                SkillProgress.user_id == user_id, SkillProgress.skill_id == skill_id
            )
        ).scalar_one_or_none()
        if row is None:
            row = SkillProgress(user_id=user_id, skill_id=skill_id)
            session.add(row)
            session.flush()
        for k, v in fields.items():
            setattr(row, k, v)
        return _progress_dict(row)


def record_attempt(
    user_id: str,
    session_id: str,
    skill_id: str | None,
    task_id: str | None,
    submitted_code: str,
    test_results: dict,
    error_type: str | None,
    success: bool,
) -> None:
    with get_session() as session:
        # FK safety: ensure the parent users row exists before inserting.
        _ensure_user_row(session, user_id)
        session.add(
            Attempt(
                user_id=user_id,
                session_id=session_id,
                skill_id=skill_id,
                task_id=task_id,
                submitted_code=submitted_code,
                test_results=test_results,
                error_type=error_type,
                success=success,
            )
        )


def mastered_concepts(user_id: str) -> set[str]:
    """Concepts the user has mastered in ANY language (for cross-language reuse)."""
    from app.db.skill_graph import concept_of

    concepts: set[str] = set()
    with get_session() as session:
        rows = session.execute(
            select(SkillProgress.skill_id).where(
                SkillProgress.user_id == user_id,
                SkillProgress.state.in_(["mastered", "advanced"]),
            )
        ).all()
    for (skill_id,) in rows:
        c = concept_of(skill_id)
        if c:
            concepts.add(c)
    return concepts


def _progress_dict(row: SkillProgress) -> dict:
    return {
        "skill_id": row.skill_id,
        "mastery": row.mastery,
        "attempts": row.attempts,
        "state": row.state,
        "consecutive_successes": row.consecutive_successes,
        "consecutive_failures": row.consecutive_failures,
    }
