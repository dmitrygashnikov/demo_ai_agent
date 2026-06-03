"""Error Classifier node — hybrid trace-parsing + LLM semantic classification.

Determines the error type (syntax, off_by_one, type_error, logic, timeout,
runtime, performance) which becomes the key for retrieving a targeted video
review during remediation.
"""
from __future__ import annotations

import logging

from app.graph.state import TutorState
from app.llm.client import LLMUnavailable, chat_json

logger = logging.getLogger(__name__)

_ERROR_TYPES = [
    "syntax", "type_error", "off_by_one", "logic", "runtime", "timeout", "performance"
]

_SYSTEM = (
    "Classify the student's failed coding attempt into one error type from "
    f"{_ERROR_TYPES}. Use the task, the code, stderr and which tests failed. "
    "Return JSON: {\"error_type\": one of the list, \"explanation\": short string}."
)


def _rule_based(exec_result: dict) -> str | None:
    stderr = (exec_result or {}).get("stderr", "") or ""
    if exec_result.get("timed_out"):
        return "timeout"
    low = stderr.lower()
    if "syntaxerror" in low or "unexpected token" in low:
        return "syntax"
    if "typeerror" in low:
        return "type_error"
    if "indexerror" in low or "rangeerror" in low or "out of range" in low:
        return "off_by_one"
    if stderr.strip():
        return "runtime"
    return None


def error_classifier(state: TutorState) -> dict:
    exec_result = state.get("execution_result", {}) or {}
    code = state.get("submitted_code", "") or ""

    error_type = _rule_based(exec_result)

    if error_type is None:
        # No stderr but tests failed → likely a logic/off-by-one error → ask LLM.
        try:
            res = chat_json(
                [
                    {"role": "system", "content": _SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Code:\n{code}\n\nStderr:\n{exec_result.get('stderr','')}\n"
                            f"Passed {exec_result.get('passed_tests')}/"
                            f"{exec_result.get('total_tests')} tests."
                        ),
                    },
                ],
                temperature=0,
            )
            error_type = res.get("error_type", "logic")
        except LLMUnavailable:
            error_type = "logic"

    if error_type not in _ERROR_TYPES:
        error_type = "logic"

    logger.info("Classified error_type=%s", error_type)
    return {"last_error_type": error_type, "next_action": "remediate"}
