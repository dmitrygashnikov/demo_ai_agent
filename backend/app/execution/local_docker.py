"""Local executor — runs code via the isolated ``code-executor`` HTTP service.

Despite the historical name, in this compose setup the local strategy talks to
the dedicated ``code-executor`` container (which itself enforces timeout/memory
limits and an ephemeral filesystem). This keeps the backend image slim and the
execution properly isolated on a separate service.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.execution.base import (
    CodeExecutor,
    ExecutionResult,
    TestCase,
    build_program,
)

logger = logging.getLogger(__name__)


class LocalDockerExecutor(CodeExecutor):
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.CODE_EXECUTOR_URL

    def run(
        self,
        language: str,
        code: str,
        entry_point: str,
        tests: list[TestCase],
    ) -> ExecutionResult:
        program = build_program(language, code, entry_point, tests)
        payload = {
            "language": language,
            "program": program,
            "timeout": settings.EXECUTION_TIMEOUT_SECONDS,
            "memory_mb": settings.EXECUTION_MEMORY_MB,
        }
        try:
            with httpx.Client(timeout=settings.EXECUTION_TIMEOUT_SECONDS + 10) as client:
                resp = client.post(f"{self.base_url}/run", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.error("Local executor failed: %s", exc)
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Executor service unreachable: {exc}",
                exit_code=-1,
                passed_tests=0,
                total_tests=len(tests) or 1,
                duration_ms=0,
                timed_out=False,
            )

        return ExecutionResult(
            success=data.get("success", False),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            exit_code=data.get("exit_code", -1),
            passed_tests=data.get("passed_tests", 0),
            total_tests=data.get("total_tests", len(tests) or 1),
            duration_ms=data.get("duration_ms", 0),
            timed_out=data.get("timed_out", False),
        )
