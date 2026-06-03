"""RapidAPI CodeRunner executor (req. 6, optional).

Used only when both ``RAPIDAPI_KEY`` and ``RAPIDAPI_CODERUNNER_HOST`` are set.
On any failure it raises ``RapidApiError`` so the factory / caller can fall back
to the local executor (edge case: external API outage).

The exact RapidAPI CodeRunner request schema varies by listing; this client
targets a common ``/run`` JSON contract sending ``{language, code, stdin}`` and
reading ``{stdout, stderr, ...}``. We submit the same generated harness as the
local executor and parse the ``__TESTS__`` marker from stdout.
"""
from __future__ import annotations

import logging
import re

import httpx

from app.config import settings
from app.execution.base import (
    CodeExecutor,
    ExecutionResult,
    TestCase,
    build_program,
)

logger = logging.getLogger(__name__)

_TEST_MARKER = re.compile(r"__TESTS__\s+(\d+)\s+(\d+)")

# Map our language ids to common CodeRunner language identifiers.
_LANG_MAP = {
    "python": "python3",
    "javascript": "nodejs",
    "js": "nodejs",
    "node": "nodejs",
}


class RapidApiError(Exception):
    pass


class RapidApiCodeRunner(CodeExecutor):
    def __init__(self) -> None:
        if not settings.rapidapi_enabled:
            raise RapidApiError("RapidAPI CodeRunner is not configured")
        self.host = settings.RAPIDAPI_CODERUNNER_HOST
        self.key = settings.RAPIDAPI_KEY

    def run(
        self,
        language: str,
        code: str,
        entry_point: str,
        tests: list[TestCase],
    ) -> ExecutionResult:
        program = build_program(language, code, entry_point, tests)
        url = f"https://{self.host}/run"
        headers = {
            "content-type": "application/json",
            "X-RapidAPI-Key": self.key,
            "X-RapidAPI-Host": self.host,
        }
        payload = {
            "language": _LANG_MAP.get(language, language),
            "code": program,
            "stdin": "",
        }
        try:
            with httpx.Client(timeout=settings.EXECUTION_TIMEOUT_SECONDS + 15) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.error("RapidAPI CodeRunner failed: %s", exc)
            raise RapidApiError(str(exc)) from exc

        stdout = data.get("stdout") or data.get("output") or ""
        stderr = data.get("stderr") or data.get("error") or ""

        match = _TEST_MARKER.search(stdout)
        if match:
            passed, total = int(match.group(1)), int(match.group(2))
            success = passed == total and total > 0
        else:
            total = len(tests) or 1
            success = not stderr
            passed = total if success else 0

        return ExecutionResult(
            success=success,
            stdout=stdout,
            stderr=stderr,
            exit_code=0 if success else 1,
            passed_tests=passed,
            total_tests=total,
            duration_ms=int(float(data.get("cpuTime", 0) or 0) * 1000),
            timed_out=False,
        )
