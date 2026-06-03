"""Adaptivity Engine node (architecture 6.2).

Decides the next move based on success streaks:
  * >= MASTERY_SUCCESS_STREAK consecutive successes → mark skill mastered, advance
    to the next skill.
  * On a mastered skill with >= ADVANCED_SUCCESS_STREAK → escalate to advanced
    (real-world cases) at higher difficulty.
  * Otherwise → continue practicing at (optionally raised) difficulty.
Always routes to Task Selector to serve the next appropriate task.
"""
from __future__ import annotations

import logging

from app.db.progress_repo import update_progress
from app.db.skill_graph import next_skill
from app.graph.state import TutorState
from app.settings_store import get_runtime_settings

logger = logging.getLogger(__name__)


def adaptivity_engine(state: TutorState) -> dict:
    user_id = state.get("user_id", "")
    skill_id = state.get("current_skill", "")
    successes = state.get("consecutive_successes", 0)
    skill_state = state.get("skill_state", "practicing")
    difficulty = state.get("difficulty_level", 2)

    rt = get_runtime_settings()
    mastery_streak = rt["MASTERY_SUCCESS_STREAK"]
    advanced_streak = rt["ADVANCED_SUCCESS_STREAK"]

    exec_result = state.get("execution_result", {}) or {}
    base_msg = (
        f"✅ Correct! Passed {exec_result.get('passed_tests', 0)}/"
        f"{exec_result.get('total_tests', 0)} tests."
    )

    # Already mastered + sustained success → escalate to real-world cases.
    if skill_state in ("mastered", "advanced") and successes >= advanced_streak:
        if user_id:
            update_progress(user_id, skill_id, state="advanced")
        logger.info("Escalating skill=%s to advanced real-world cases", skill_id)
        return {
            "skill_state": "advanced",
            "difficulty_level": min(5, difficulty + 1),
            "agent_response": base_msg + "\n\n🚀 You're on a roll — here's a real-world case to stretch you.",
            "next_action": "select_task",
        }

    # Mastery reached → advance to next skill.
    if successes >= mastery_streak:
        if user_id:
            update_progress(user_id, skill_id, state="mastered", mastery=1.0)
        nxt = next_skill(skill_id)
        if nxt is None:
            return {
                "skill_state": "mastered",
                "agent_response": base_msg + "\n\n🎓 You've completed the whole track for this language. Outstanding!",
                "next_action": "respond",
            }
        logger.info("Skill=%s mastered → next=%s", skill_id, nxt.id)
        return {
            "current_skill": nxt.id,
            "skill_state": "introducing",
            "difficulty_level": 1,
            "consecutive_successes": 0,
            "agent_response": base_msg + f"\n\n🎉 Skill mastered! Moving on to **{nxt.name}**.",
            "next_action": "select_task",
        }

    # Keep practicing, nudge difficulty up slightly.
    logger.info("Continue practicing skill=%s (streak=%d)", skill_id, successes)
    return {
        "skill_state": "practicing",
        "difficulty_level": min(5, difficulty + 1),
        "agent_response": base_msg + "\n\nNice — let's keep the momentum with another task.",
        "next_action": "select_task",
    }
