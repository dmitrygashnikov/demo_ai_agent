"""Intent Router node — classifies the student's input.

Categories:
  * goal      — set or change a learning goal
  * code      — the student submitted code for validation
  * question  — a theory/explanation question
  * clarify   — ambiguous; ask the student to clarify (low confidence)

Uses the LLM for semantic classification, with a heuristic fallback when the
LLM is unavailable. If confidence is low we route to clarification rather than
guessing (edge case: ambiguous request).
"""
from __future__ import annotations

import logging

from app.graph.state import TutorState
from app.llm.client import LLMUnavailable, chat_json

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You classify a programming-tutor user's message into one intent. "
    "Return JSON: {\"intent\": one of [goal, code, question, clarify], "
    "\"confidence\": 0..1, \"language\": python|javascript|unknown}. "
    "intent=goal if they state what they want to learn. "
    "intent=code only if the message is actual source code to be tested. "
    "intent=question for theory/explanation requests. "
    "intent=clarify if too vague to act on."
)


def _heuristic(message: str, submitted_code: str | None) -> dict:
    if submitted_code:
        return {"intent": "code", "confidence": 0.9, "language": "unknown"}
    lower = message.lower()
    if any(k in lower for k in ["want to learn", "хочу", "learn ", "goal", "научиться"]):
        return {"intent": "goal", "confidence": 0.6, "language": "unknown"}
    if any(k in lower for k in ["def ", "function ", "for ", "while ", "return ", "console.log", "print("]):
        return {"intent": "code", "confidence": 0.55, "language": "unknown"}
    if len(message.split()) < 3:
        return {"intent": "clarify", "confidence": 0.5, "language": "unknown"}
    return {"intent": "question", "confidence": 0.5, "language": "unknown"}


def intent_router(state: TutorState) -> dict:
    message = state.get("user_message", "") or ""
    submitted_code = state.get("submitted_code")

    # Code submissions are unambiguous — route directly.
    if submitted_code:
        return {"intent": "code", "next_action": "code"}

    try:
        result = chat_json(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": message},
            ],
            temperature=0,
        )
        if "intent" not in result:
            result = _heuristic(message, submitted_code)
    except LLMUnavailable:
        result = _heuristic(message, submitted_code)

    intent = result.get("intent", "question")
    confidence = float(result.get("confidence", 0.5) or 0.5)

    # Low-confidence → ask for clarification instead of guessing.
    if confidence < 0.45 and intent != "goal":
        intent = "clarify"

    updates: dict = {"intent": intent, "next_action": intent}

    lang = result.get("language")
    if lang in ("python", "javascript") and not state.get("language"):
        updates["language"] = lang

    logger.info("Intent=%s confidence=%.2f", intent, confidence)
    return updates
