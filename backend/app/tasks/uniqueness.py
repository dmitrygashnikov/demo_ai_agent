"""Task uniqueness with a solve-count cooldown (req. 5).

Rule: a task may not be served to a student more than once per
``COOLDOWN_SOLVES`` (default 500) of that student's solves. We track each serve
in ``task_serve_history`` with the student's solve_count at serve time, and
filter candidates whose last serve is within the cooldown window.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.config import settings
from app.db.models import TaskServeHistory
from app.db.session import get_session

logger = logging.getLogger(__name__)

COOLDOWN_SOLVES = settings.COOLDOWN_SOLVES


def _serve_history(user_id: str) -> dict[str, int]:
    """Map task_id -> latest served_at_solve_count for the user."""
    history: dict[str, int] = {}
    with get_session() as session:
        rows = session.execute(
            select(
                TaskServeHistory.task_id, TaskServeHistory.served_at_solve_count
            ).where(TaskServeHistory.user_id == user_id)
        ).all()
    for task_id, solve_count in rows:
        if task_id not in history or solve_count > history[task_id]:
            history[task_id] = solve_count
    return history


def filter_unique_tasks(user_id, candidates, current_solve_count, history=None):
    """Return candidate tasks not served within the last COOLDOWN_SOLVES solves.

    ``candidates`` is a list of objects with an ``.id`` attribute.
    ``history`` maps task_id -> last served_at_solve_count (fetched if omitted).
    """
    if history is None:
        history = _serve_history(user_id)

    allowed = []
    for task in candidates:
        last = history.get(task.id)
        if last is None or (current_solve_count - last) >= COOLDOWN_SOLVES:
            allowed.append(task)

    # If everything is on cooldown, fall back to the least-recently-served ones.
    if not allowed and candidates:
        allowed = sorted(candidates, key=lambda t: history.get(t.id, -1))[:5]
    return allowed


def record_serve(user_id: str, task_id: str, current_solve_count: int) -> None:
    """Persist that a task was served at the current solve count."""
    with get_session() as session:
        session.add(
            TaskServeHistory(
                user_id=user_id,
                task_id=task_id,
                served_at_solve_count=current_solve_count,
            )
        )
    logger.debug(
        "Recorded serve user=%s task=%s at solve_count=%d",
        user_id,
        task_id,
        current_solve_count,
    )


def violates_cooldown(user_id: str, task_id: str, current_solve_count: int) -> bool:
    """True if serving task_id now would violate the cooldown (for auditing)."""
    history = _serve_history(user_id)
    last = history.get(task_id)
    if last is None:
        return False
    return (current_solve_count - last) < COOLDOWN_SOLVES
