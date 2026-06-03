"""Answer Generator node.

Generates an explanation/answer grounded in retrieved context (with citation).
Includes a guardrail (edge case: conflicting instructions): if the student asks
for the full solution to an active task, the agent returns hints instead of the
answer, explaining the pedagogical reason.

If the answer contains a runnable code block, it is flagged for Self-Execution
so it can be verified before being shown.
"""
from __future__ import annotations

import logging
import re

from app.graph.state import TutorState
from app.llm.client import LLMUnavailable, chat
from app.tasks.repository import tasks_for_skill

logger = logging.getLogger(__name__)

_CODE_FENCE = re.compile(r"```(?:python|javascript|js)?\n(.*?)```", re.DOTALL)

_GUARDRAIL_KEYWORDS = ["give me the answer", "just the solution", "solve it for me", "дай ответ", "реши за меня"]


def _format_context(context: list) -> str:
    if not context:
        return "(no retrieved context)"
    lines = []
    for c in context:
        src = c.get("title") or c.get("doc_type", "source")
        url = f" [{c['url']}]" if c.get("url") else ""
        tc = f" ({c['timecode']})" if c.get("timecode") else ""
        lines.append(f"- {src}{url}{tc}: {c.get('text', '')[:300]}")
    return "\n".join(lines)


def _exercise_suggestion(state: TutorState) -> str:
    """Suggest a concrete practice exercise to follow a theory answer.

    Theory questions should return useful info AND a practice exercise. The
    question branch doesn't serve a task node, so we nudge the student towards
    one they can request, preferring a skill that actually has tasks.
    """
    skill_id = state.get("current_skill", "")
    if skill_id and tasks_for_skill(skill_id):
        return (
            "\n\n---\n**Practice exercise:** ready to apply this? Ask me for a task "
            "(say \"give me a task\") and I'll serve a hands-on exercise for this "
            "skill, then run your code against tests."
        )
    return (
        "\n\n---\n**Practice exercise:** want to apply this? Tell me what you want "
        "to learn (e.g. \"I want to learn Python loops\") and I'll set up a "
        "hands-on exercise you can run against tests."
    )


def answer_generator(state: TutorState) -> dict:
    message = state.get("user_message", "")
    context = state.get("retrieved_context", [])
    language = state.get("language", "python")
    has_active_task = bool(state.get("current_task_id"))

    # Guardrail: refuse to hand over full solution to an active task.
    if has_active_task and any(k in message.lower() for k in _GUARDRAIL_KEYWORDS):
        response = (
            "I won't hand over the full solution — solving it yourself is how the "
            "skill sticks. Here are hints instead:\n"
            "1. Re-read the task and identify the loop bounds.\n"
            "2. Use an accumulator variable initialised before the loop.\n"
            "3. Check the inclusive/exclusive end of your range.\n\n"
            "Try again and submit your code; I'll run it and give targeted feedback."
        )
        return {"agent_response": response, "next_action": "respond"}

    system = (
        f"You are a programming tutor teaching {language}. Answer concisely using "
        f"ONLY the provided context where possible, and cite sources inline like "
        f"[title]. If you include code, wrap it in a fenced code block and make it "
        f"runnable and correct."
    )
    user = f"Question: {message}\n\nContext:\n{_format_context(context)}"

    try:
        answer = chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
        )
    except LLMUnavailable:
        answer = (
            "I'm having trouble reaching the language model right now. Your progress "
            "is saved — please try again in a moment."
        )
        return {"agent_response": answer, "next_action": "respond"}

    # Detect code to verify via self-execution.
    match = _CODE_FENCE.search(answer)
    if match:
        code = match.group(1)
        return {
            "agent_response": answer,
            "generated_code": code,
            "regen_attempts": 0,
            "next_action": "self_execute",
        }

    # Theory answers should also point the student at a practice exercise.
    answer = answer + _exercise_suggestion(state)
    return {"agent_response": answer, "next_action": "respond"}
