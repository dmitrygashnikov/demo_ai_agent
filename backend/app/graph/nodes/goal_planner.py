"""Goal Planner node — extracts goal parameters; human-in-the-loop clarification.

Extracts (language, domain, level, pace) from the natural-language goal. If
critical info is missing (e.g. no language and can't be inferred), it uses
LangGraph's ``interrupt`` to ask the student a clarifying question rather than
guessing (edge case: incomplete goal data).
"""
from __future__ import annotations

import logging

from langgraph.types import interrupt

from app.db.progress_repo import get_or_create_user
from app.graph.state import TutorState
from app.llm.client import LLMUnavailable, chat_json

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Extract a structured learning goal profile from the student's message. "
    "Return JSON with keys: language (python|javascript|unknown), domain (e.g. "
    "web, automation, games, algorithms, data, general), level (beginner|"
    "intermediate|advanced|unknown), pace (slow|normal|fast|unknown), "
    "needs_clarification (true|false), clarifying_question (string)."
)


def goal_planner(state: TutorState) -> dict:
    message = state.get("user_message", "") or state.get("learning_goal", "")

    try:
        profile = chat_json(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": message},
            ],
            temperature=0,
        )
    except LLMUnavailable:
        profile = {"language": "unknown", "level": "beginner", "domain": "general"}

    language = profile.get("language", "unknown")
    if language not in ("python", "javascript"):
        language = state.get("language") or "unknown"

    # Human-in-the-loop: if we still don't know the language, ask.
    if language == "unknown":
        question = profile.get("clarifying_question") or (
            "Which language would you like to learn — Python or JavaScript? "
            "And what's your goal (e.g. automation, web, games, algorithms)?"
        )
        # interrupt pauses the graph; the resume value becomes the answer.
        answer = interrupt({"question": question, "type": "goal_clarification"})
        # On resume, re-extract from the combined answer.
        try:
            profile = chat_json(
                [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": f"{message}\n{answer}"},
                ],
                temperature=0,
            )
        except LLMUnavailable:
            profile = {}
        language = profile.get("language", "unknown")
        if language not in ("python", "javascript"):
            # Default to python if still unknown after one clarification round.
            language = "python"

    goal_profile = {
        "language": language,
        "domain": profile.get("domain", "general"),
        "level": profile.get("level", "beginner"),
        "pace": profile.get("pace", "normal"),
    }

    user_id = state.get("user_id", "")
    if user_id:
        get_or_create_user(user_id, language)

    logger.info("Goal profile: %s", goal_profile)
    return {
        "language": language,
        "goal_profile": goal_profile,
        "learning_goal": message,
        "next_action": "plan",
    }
