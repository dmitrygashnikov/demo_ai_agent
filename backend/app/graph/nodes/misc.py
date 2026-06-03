"""Small terminal/utility nodes: clarify and respond."""
from __future__ import annotations

import logging

from app.graph.state import TutorState

logger = logging.getLogger(__name__)


def clarify(state: TutorState) -> dict:
    """Ambiguous input → ask for clarification instead of guessing."""
    question = (
        "I want to help precisely. Could you clarify what you'd like to do?\n"
        "- Set or change a learning goal (e.g. 'learn Python for automation')\n"
        "- Ask a theory question\n"
        "- Submit code for a task to be checked"
    )
    return {
        "agent_response": question,
        "pending_question": question,
        "next_action": "respond",
    }


def respond(state: TutorState) -> dict:
    """Terminal node: finalise the response into the message history."""
    answer = state.get("agent_response", "") or "Done."
    return {
        "messages": [{"role": "assistant", "content": answer}],
        "next_action": "end",
    }
