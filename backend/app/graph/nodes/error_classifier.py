"""Error Classifier node — hybrid trace-parsing + LLM semantic classification.

Determines the error type (syntax, off_by_one, type_error, logic, timeout,
runtime, performance) which becomes the key for retrieving a targeted video
review during remediation.

Fail-path remediation fix (Problems 1 & 2): classification is now grounded in
the **real** student error extracted by ``code_validator`` (the per-test
``ERROR:`` / ``FAIL:`` diagnostics from stdout + the top-level stderr
traceback), not the almost-always-empty raw stderr. The LLM ``explanation`` is
kept (previously discarded) and threaded downstream so the student-facing
analysis is about their actual code. A non-code / SyntaxError submission is
classified deterministically as ``syntax`` without an LLM round-trip.
"""
from __future__ import annotations

import logging

from app.graph.nodes._error_utils import classify_from_error, extract_student_error
from app.graph.state import TutorState
from app.llm.client import LLMUnavailable, chat_json

logger = logging.getLogger(__name__)

_ERROR_TYPES = [
    "syntax", "type_error", "off_by_one", "logic", "runtime", "timeout", "performance"
]

_SYSTEM = (
    "You are a programming tutor classifying a student's failed coding attempt. "
    f"Choose exactly one error type from {_ERROR_TYPES}. Base your decision on "
    "the student's actual code, the real error/diagnostics, and which tests "
    "failed — NOT on generic assumptions. Return JSON: "
    "{\"error_type\": one of the list, \"explanation\": a short, concrete "
    "explanation of the mistake in THIS student's code}."
)


def error_classifier(state: TutorState) -> dict:
    exec_result = state.get("execution_result", {}) or {}
    code = state.get("submitted_code", "") or ""

    # The real error was extracted in ``code_validator``; recompute defensively
    # if it is missing (e.g. older checkpoint) — both helpers are fail-open.
    student_error = state.get("student_error") or extract_student_error(exec_result)
    input_diagnosis = state.get("input_diagnosis")

    explanation = ""

    # 1) Non-code / SyntaxError submission → deterministic syntax classification
    #    with the precise, code-grounded message produced by the input guard.
    if input_diagnosis and input_diagnosis.get("kind") in ("syntax", "not_code", "empty"):
        error_type = "syntax"
        explanation = input_diagnosis.get("message", "")
        logger.info("Classified error_type=%s (input guard: %s)", error_type, input_diagnosis.get("kind"))
        return {
            "last_error_type": error_type,
            "error_explanation": explanation,
            "error_symbol": student_error.get("symbol"),
            "next_action": "remediate",
        }

    # 2) Deterministic classification from the *real* extracted error.
    error_type = classify_from_error(student_error, exec_result)

    # 3) When the deterministic rules can't decide (e.g. a wrong-but-running
    #    answer with no exception), ask the LLM — grounded in the real signals.
    if error_type is None:
        try:
            failing = student_error.get("summary", "") or "(no diagnostic captured)"
            res = chat_json(
                [
                    {"role": "system", "content": _SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Submitted code:\n```\n{code}\n```\n\n"
                            f"Real error / failing cases:\n{failing}\n\n"
                            f"Passed {exec_result.get('passed_tests')}/"
                            f"{exec_result.get('total_tests')} tests."
                        ),
                    },
                ],
                temperature=0,
            )
            error_type = res.get("error_type", "logic")
            explanation = (res.get("explanation") or "").strip()
        except LLMUnavailable:
            error_type = "logic"

    if error_type not in _ERROR_TYPES:
        error_type = "logic"

    logger.info("Classified error_type=%s (explanation=%s)", error_type, bool(explanation))
    return {
        "last_error_type": error_type,
        # Keep the LLM explanation (previously discarded) so the downstream
        # code-grounded explanation generator can use/augment it.
        "error_explanation": explanation,
        "error_symbol": student_error.get("symbol"),
        "next_action": "remediate",
    }
