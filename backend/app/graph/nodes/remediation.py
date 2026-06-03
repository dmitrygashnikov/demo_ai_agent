"""Remediation Planner node — video review → similar tasks.

On a failed attempt, retrieves a targeted video review for the error type, then
sets the skill into remediation so the Task Selector serves similar practice
tasks. Updates failure streak and progress state.
"""
from __future__ import annotations

import logging

from app.db.progress_repo import get_or_create_progress, update_progress
from app.db.skill_graph import concept_of
from app.graph.state import TutorState
from app.rag.retriever import retrieve_video_for_error

logger = logging.getLogger(__name__)


def remediation_planner(state: TutorState) -> dict:
    language = state.get("language", "python")
    skill_id = state.get("current_skill", "")
    concept = concept_of(skill_id) or ""
    error_type = state.get("last_error_type", "logic")
    user_id = state.get("user_id", "")
    exec_result = state.get("execution_result", {}) or {}

    # Targeted video review for this error.
    videos = retrieve_video_for_error(language, concept, error_type)

    # Update progress: increment failures, reset success streak, enter remediation.
    failures = state.get("consecutive_failures", 0) + 1
    if user_id:
        prog = get_or_create_progress(user_id, skill_id)
        update_progress(
            user_id,
            skill_id,
            state="remediation",
            attempts=prog["attempts"] + 1,
            consecutive_failures=failures,
            consecutive_successes=0,
        )

    # Build the response: feedback + video + announce similar tasks.
    parts = [
        f"Not quite — you passed {exec_result.get('passed_tests', 0)}/"
        f"{exec_result.get('total_tests', 0)} tests.",
        f"Diagnosed issue: **{error_type.replace('_', ' ')}**.",
    ]
    if exec_result.get("timed_out"):
        parts.append("Your code timed out — likely an infinite loop. Check your loop's exit condition.")
    if videos:
        v = videos[0]
        parts.append(
            f"\n📺 Watch this targeted review: **{v['title']}** "
            f"({v.get('url','')}) — {v.get('timecode','')}."
        )
    parts.append("\nLet's reinforce with a similar task next. Submit your new attempt when ready.")

    response = "\n".join(parts)
    logger.info("Remediation for skill=%s error=%s (failures=%d)", skill_id, error_type, failures)

    return {
        "skill_state": "remediation",
        "consecutive_failures": failures,
        "consecutive_successes": 0,
        "agent_response": response,
        "retrieved_context": videos,
        "next_action": "select_task",
    }
