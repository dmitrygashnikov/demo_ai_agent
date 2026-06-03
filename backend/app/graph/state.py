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

    # Section change (req. 6/7). ``section_change`` is set True for the single
    # turn produced by ``POST /api/sections/select`` (and the WS ``select_section``
    # handler). It forces ``task_selector`` to DISCARD the previously-served
    # ``current_task_id`` and mint a fresh themed task, and to prepend the
    # theme-set acknowledgement line ("🎨 Theme set to …") — purely informational,
    # never applying success/remediation prefixes. ``section_title`` carries the
    # human-readable title for that acknowledgement. ``cancelled_task_id`` records
    # the id of the task that was cancelled (logged + surfaced in the payload).
    section_change: bool
    section_title: str
    cancelled_task_id: str | None

    # Exercise-type variety (Problem 4). ``last_exercise_type`` records the
    # exercise_type of the most-recently SERVED task so ``task_selector`` can
    # rotate AWAY from it on the next turn (so consecutive exercises differ in
    # essence — e.g. an "implement" is not followed by another "implement" —
    # not just in wording). Checkpointed per session like ``current_task_id``.
    last_exercise_type: str | None

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

    # Code-grounded failure analysis (fail-path remediation fix, Problems 1-3).
    #   ``student_error`` — structured *real* error extracted from the sandbox:
    #     {summary, stderr, errors[{args,msg}], fails[{args,expected,got}],
    #      symbol, timed_out}. Built by ``extract_student_error`` from the
    #     harness stdout (ERROR:/FAIL: lines) + top-level stderr traceback.
    #   ``failed_cases`` — convenience list of the failing cases (errors+fails)
    #     for the explanation prompt / student-facing trace.
    #   ``input_diagnosis`` — non-code / empty / SyntaxError guard result
    #     ({kind, message, lineno, offset, text}) or None when the submission
    #     looks like real code.
    #   ``error_explanation`` — code-grounded plain-language explanation of the
    #     student's actual mistake (LLM, grounded in their code + real error;
    #     deterministic fallback when the LLM is down).
    #   ``error_symbol`` — concrete exception symbol (e.g. ``TypeError``) used to
    #     target remediation links at the real type/class/object.
    student_error: dict | None
    failed_cases: list
    input_diagnosis: dict | None
    error_explanation: str
    error_symbol: str | None

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
