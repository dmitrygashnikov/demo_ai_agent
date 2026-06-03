"""Thin service wrapper around the compiled graph.

Handles invoking the graph for a session (thread), surfacing human-in-the-loop
interrupts, and resuming after a clarification answer.
"""
from __future__ import annotations

import logging
from typing import Any

from langgraph.types import Command

from app.graph.builder import get_graph

logger = logging.getLogger(__name__)


def _config(session_id: str, run_name: str, metadata: dict | None = None) -> dict:
    """Build the graph run config, attaching the optional Langfuse handler.

    Tracing is best-effort: if the handler cannot be created (Langfuse disabled
    or unavailable) we simply omit callbacks. Any failure is swallowed so the
    main flow is never affected (edge case: external observability is down).
    """
    config: dict[str, Any] = {"configurable": {"thread_id": session_id}}
    try:
        from app.observability.langfuse_client import get_langfuse_handler

        handler = get_langfuse_handler()
        if handler is not None:
            config["callbacks"] = [handler]
            config["run_name"] = run_name
            config["metadata"] = {"session_id": session_id, **(metadata or {})}
    except Exception:  # noqa: BLE001
        logger.debug("Langfuse handler attach skipped", exc_info=True)
    return config


def run_turn(
    user_id: str,
    session_id: str,
    user_message: str,
    submitted_code: str | None = None,
    language: str | None = None,
) -> dict:
    """Run one conversational turn. Returns a dict with response + metadata.

    If the graph interrupts (e.g. goal clarification), returns
    {"interrupted": True, "question": ...} so the caller can ask the student.
    """
    graph = get_graph()
    config = _config(
        session_id,
        run_name="tutor_turn",
        metadata={"user_id": user_id, "has_code": bool(submitted_code)},
    )

    state_in: dict[str, Any] = {
        "user_id": user_id,
        "session_id": session_id,
        "user_message": user_message,
        "submitted_code": submitted_code,
        "messages": [{"role": "user", "content": submitted_code or user_message}],
    }
    if language:
        state_in["language"] = language

    try:
        result = graph.invoke(state_in, config=config)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Graph turn failed")
        return {"interrupted": False, "response": f"Internal error: {exc}", "state": {}}

    return _interpret(result)


def resume_turn(session_id: str, answer: str) -> dict:
    """Resume an interrupted graph with the student's clarification answer."""
    graph = get_graph()
    config = _config(session_id, run_name="tutor_resume")
    try:
        result = graph.invoke(Command(resume=answer), config=config)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Graph resume failed")
        return {"interrupted": False, "response": f"Internal error: {exc}", "state": {}}
    return _interpret(result)


def _interpret(result: dict) -> dict:
    # LangGraph surfaces interrupts under "__interrupt__".
    interrupts = result.get("__interrupt__")
    if interrupts:
        intr = interrupts[0]
        value = getattr(intr, "value", intr)
        question = value.get("question") if isinstance(value, dict) else str(value)
        return {"interrupted": True, "question": question, "state": result}

    return {
        "interrupted": False,
        "response": result.get("agent_response", ""),
        "state": {
            "language": result.get("language"),
            "current_skill": result.get("current_skill"),
            "skill_state": result.get("skill_state"),
            "difficulty_level": result.get("difficulty_level"),
            "current_task_id": result.get("current_task_id"),
            "consecutive_successes": result.get("consecutive_successes"),
            "consecutive_failures": result.get("consecutive_failures"),
            "last_error_type": result.get("last_error_type"),
            "execution_result": result.get("execution_result"),
            "solve_count": result.get("solve_count"),
        },
    }
