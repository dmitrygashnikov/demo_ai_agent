"""TutorState — the LangGraph shared state (architecture section 3.1)."""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class TutorState(TypedDict, total=False):
    # Identity & goal
    user_id: str
    session_id: str
    language: str  # python | javascript
    learning_goal: str
    goal_profile: dict

    # Current learning position
    current_skill: str
    skill_state: str  # introducing | practicing | remediation | mastered | advanced
    difficulty_level: int

    # Interaction
    user_message: str
    submitted_code: str | None
    current_task_id: str | None
    retrieved_context: list
    execution_result: dict | None

    # Self-execution loop bookkeeping
    generated_code: str | None
    generated_entry_point: str | None
    regen_attempts: int

    # Diagnostics
    last_error_type: str | None
    consecutive_successes: int
    consecutive_failures: int

    # Output / routing
    intent: str
    agent_response: str
    next_action: str
    pending_question: str | None  # human-in-the-loop clarification
    messages: Annotated[list, add_messages]

    # Misc bookkeeping
    solve_count: int
    meta: dict[str, Any]
