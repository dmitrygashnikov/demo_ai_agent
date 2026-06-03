"""Skill Path Builder node.

Builds the personal trajectory from the Skill Graph for the chosen language,
reusing concepts the student already mastered in another language (cross-language
reuse). Sets the current skill to the first not-yet-mastered skill.
"""
from __future__ import annotations

import logging

from app.db.progress_repo import get_or_create_progress, mastered_concepts, update_progress
from app.db.skill_graph import concept_of, skills_for_language
from app.graph.state import TutorState

logger = logging.getLogger(__name__)


def skill_path_builder(state: TutorState) -> dict:
    language = state.get("language", "python")
    user_id = state.get("user_id", "")

    skills = sorted(skills_for_language(language), key=lambda s: s.order_index)
    already = mastered_concepts(user_id) if user_id else set()

    current_skill = None
    for s in skills:
        # Reuse cross-language mastery: if concept already mastered, mark it here too.
        if s.concept in already:
            if user_id:
                update_progress(user_id, s.id, state="mastered", mastery=0.8)
            continue
        prog = get_or_create_progress(user_id, s.id) if user_id else {"state": "introducing"}
        if prog["state"] not in ("mastered", "advanced"):
            current_skill = s.id
            break

    if current_skill is None:
        current_skill = skills[0].id

    logger.info("Skill path built; current_skill=%s (reused concepts=%s)", current_skill, already)
    return {
        "current_skill": current_skill,
        "skill_state": "introducing",
        "difficulty_level": 1,
        "next_action": "select_task",
    }
