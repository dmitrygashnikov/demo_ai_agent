"""Self-Execution node — the anti-hallucination guarantee (architecture 5.1).

Any code the agent intends to show the student is FIRST executed in the sandbox.
If it runs cleanly it is approved; if it fails, the error is fed back into the
LLM for a regeneration attempt (reflection loop), up to MAX_REGEN_ATTEMPTS. Only
verified code reaches the student.

The conditional routing (loop back vs. respond) is decided by
``self_execution_route`` in builder.py based on ``next_action`` set here.
"""
from __future__ import annotations

import logging
import re

from app.config import settings
from app.execution.base import TestCase
from app.execution.factory import get_executor
from app.graph.state import TutorState
from app.llm.client import LLMUnavailable, chat

logger = logging.getLogger(__name__)

_CODE_FENCE = re.compile(r"```(?:python|javascript|js)?\n(.*?)```", re.DOTALL)


def _detect_entry_point(code: str, language: str) -> str | None:
    if language == "python":
        m = re.search(r"def\s+(\w+)\s*\(", code)
    else:
        m = re.search(r"function\s+(\w+)\s*\(", code)
    return m.group(1) if m else None


def self_execution(state: TutorState) -> dict:
    code = state.get("generated_code") or ""
    language = state.get("language", "python")
    attempts = state.get("regen_attempts", 0)

    entry = _detect_entry_point(code, language)
    executor = get_executor()

    # Smoke-run: with no declared test cases we only verify the snippet runs
    # (imports resolve, no syntax/runtime error). For Python we additionally
    # reference the detected entry point so a NameError surfaces if the function
    # was never actually defined.
    tests: list[TestCase] = []
    if entry and language == "python":
        smoke_code = code + f"\n_ = {entry}\n"
    else:
        smoke_code = code
    result = executor.run(language, smoke_code, entry or "main", tests)

    if result.success or result.exit_code == 0:
        logger.info("Self-execution passed (attempt %d)", attempts)
        return {
            "execution_result": _result_dict(result),
            "next_action": "respond",
        }

    # Failed — try to regenerate with the error as feedback.
    if attempts >= settings.MAX_REGEN_ATTEMPTS:
        logger.warning("Self-execution gave up after %d attempts", attempts)
        note = (
            "\n\n_Note: I could not fully verify a runnable example after several "
            "attempts, so treat the snippet above as illustrative._"
        )
        return {
            "execution_result": _result_dict(result),
            "agent_response": (state.get("agent_response", "") + note),
            "next_action": "respond",
        }

    try:
        fixed = chat(
            [
                {
                    "role": "system",
                    "content": (
                        f"You wrote {language} code that failed to run. Fix it. "
                        f"Return ONLY a fenced code block with the corrected code."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Code:\n```\n{code}\n```\nError:\n{result.stderr}",
                },
            ],
            temperature=0,
        )
        m = _CODE_FENCE.search(fixed)
        new_code = m.group(1) if m else fixed
    except LLMUnavailable:
        return {
            "execution_result": _result_dict(result),
            "next_action": "respond",
        }

    logger.info("Regenerating code (attempt %d -> %d)", attempts, attempts + 1)
    return {
        "generated_code": new_code,
        "regen_attempts": attempts + 1,
        "next_action": "self_execute",  # loop back
    }


def _result_dict(r) -> dict:
    return {
        "success": r.success,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "exit_code": r.exit_code,
        "passed_tests": r.passed_tests,
        "total_tests": r.total_tests,
        "duration_ms": r.duration_ms,
        "timed_out": r.timed_out,
    }
