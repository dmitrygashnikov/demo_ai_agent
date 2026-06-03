"""Task Selector node — picks a task for current skill with uniqueness filter.

Applies the cooldown filter (req. 5): a task is not re-served within
``COOLDOWN_SOLVES`` of the student's solves. Records the serve in history.
"""
from __future__ import annotations

import logging
import random

from app.db.progress_repo import get_solve_count
from app.graph.state import TutorState
from app.tasks.repository import tasks_for_skill
from app.tasks.uniqueness import filter_unique_tasks, record_serve

logger = logging.getLogger(__name__)


def task_selector(state: TutorState) -> dict:
    skill_id = state.get("current_skill", "")
    user_id = state.get("user_id", "")
    difficulty = state.get("difficulty_level", 2)
    skill_state = state.get("skill_state", "practicing")

    # Choose task kind based on adaptive state.
    if skill_state == "advanced":
        kind = "real_case"
    elif skill_state == "remediation":
        kind = "similar"
    else:
        kind = None  # any practice/similar

    # Allow tasks up to the current adaptive difficulty (with a little headroom),
    # capped at the maximum band of 5. Using max(difficulty, 5) previously made
    # the ceiling always 5, defeating the adaptive ramp.
    max_diff = min(difficulty + 1, 5)
    candidates = tasks_for_skill(skill_id, kind=kind, max_difficulty=max_diff)
    if not candidates:
        candidates = tasks_for_skill(skill_id)

    if not candidates:
        return {
            "current_task_id": None,
            "agent_response": "No tasks available for this skill yet.",
            "next_action": "respond",
        }

    solve_count = get_solve_count(user_id) if user_id else 0
    allowed = filter_unique_tasks(user_id, candidates, solve_count)
    if not allowed:
        allowed = candidates

    task = random.choice(allowed)

    if user_id:
        record_serve(user_id, task.id, solve_count)

    prompt = (
        f"**Task ({task.language}, difficulty {task.difficulty})**\n\n{task.prompt}\n\n"
        f"Define a function named `{task.entry_point}`. "
        f"Submit your code and I'll run it against the tests."
    )
    logger.info("Selected task=%s for skill=%s kind=%s", task.id, skill_id, task.kind)
    return {
        "current_task_id": task.id,
        "agent_response": prompt,
        "next_action": "respond",
    }
