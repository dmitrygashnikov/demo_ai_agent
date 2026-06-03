"""Progress Updater node — records a SUCCESS and updates mastery/streaks."""
from __future__ import annotations

import logging

from app.db.progress_repo import get_or_create_progress, update_progress
from app.graph.state import TutorState

logger = logging.getLogger(__name__)


def progress_updater(state: TutorState) -> dict:
    user_id = state.get("user_id", "")
    skill_id = state.get("current_skill", "")
    successes = state.get("consecutive_successes", 0) + 1

    if user_id and skill_id:
        prog = get_or_create_progress(user_id, skill_id)
        new_mastery = min(1.0, prog["mastery"] + 0.25)
        update_progress(
            user_id,
            skill_id,
            attempts=prog["attempts"] + 1,
            mastery=new_mastery,
            consecutive_successes=successes,
            consecutive_failures=0,
            state="practicing",
        )

    logger.info("Progress success skill=%s streak=%d", skill_id, successes)
    return {
        "consecutive_successes": successes,
        "consecutive_failures": 0,
        "next_action": "adapt",
    }
