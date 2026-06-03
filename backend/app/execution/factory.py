"""Executor factory (req. 6).

Selects the execution strategy based on ``.env``:
  * RapidAPI CodeRunner if configured (online),
  * otherwise the local code-executor container.

Also provides a fallback wrapper: if the (primary) RapidAPI executor fails at
runtime, it transparently falls back to the local executor — covering the
"external API outage" edge case.
"""
from __future__ import annotations

import logging

from app.config import settings
from app.execution.base import CodeExecutor, ExecutionResult, TestCase
from app.execution.local_docker import LocalDockerExecutor
from app.execution.rapidapi import RapidApiCodeRunner, RapidApiError

logger = logging.getLogger(__name__)


class FallbackExecutor(CodeExecutor):
    """Try RapidAPI first, fall back to local on failure."""

    def __init__(self) -> None:
        self.primary = RapidApiCodeRunner()
        self.fallback = LocalDockerExecutor()

    def run(self, language, code, entry_point, tests: list[TestCase]) -> ExecutionResult:
        try:
            return self.primary.run(language, code, entry_point, tests)
        except RapidApiError as exc:
            logger.warning("RapidAPI failed (%s); falling back to local executor", exc)
            return self.fallback.run(language, code, entry_point, tests)


def get_executor() -> CodeExecutor:
    if settings.rapidapi_enabled:
        logger.info("Using RapidAPI CodeRunner (with local fallback)")
        return FallbackExecutor()
    logger.info("Using local code-executor container")
    return LocalDockerExecutor()
