"""Repository helpers for user profile and skill progress."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Attempt, SkillProgress, User
from app.db.session import get_session


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
