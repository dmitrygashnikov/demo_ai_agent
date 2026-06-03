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

    # Internet-tasks (req. 3, Group B). ``topic`` is the active free-form theme
    # biasing generation/search (read here; the topic switch API/UI is Group E).
    # ``task_source`` records provenance ("curated" | "generated") for the just-
    # served task.
    topic: str
    task_source: str  # "curated" | "generated"

    # Run & Check de-duplication + failure remediation (req. 1, Group C).
    #   ``last_passed`` — whether the most recent code submission passed; drives
    #     the PASS de-duplication (the just-solved task is not re-stated).
    #   ``remediation_links`` — [{title, url, snippet}] videos/articles fetched
    #     via the fail-open web-search client on the FAILURE path.
    #   ``remediation_excerpt`` — short plain-language explanation of the
    #     error/topic derived from those links (LLM-distilled or snippet-only).
    #   ``offer_next_task`` — set True by the success path (Group D) to mark that
    #     a success should explicitly offer the next task; declared here so the
    #     channel exists and is surfaced through the runner payload.
    last_passed: bool | None
    remediation_links: list
    remediation_excerpt: str
    offer_next_task: bool

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
    off_topic: bool  # set by topic_guard when the message is off-topic
    pending_question: str | None  # human-in-the-loop clarification
    messages: Annotated[list, add_messages]

    # Misc bookkeeping
    solve_count: int
    meta: dict[str, Any]
