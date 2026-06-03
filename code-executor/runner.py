"""Isolated code-execution micro-service.

Receives code + a test harness, runs it in a temporary directory with a hard
wall-clock timeout and (on Linux) a memory limit, and reports the result.

This is intentionally simple but enforces the critical guarantees required by
the tutor:
  * hard timeout (kills infinite loops),
  * memory cap,
  * ephemeral filesystem (temp dir wiped after each run),
  * no persistent state between runs.

The harness convention: the caller sends the student/agent ``code`` plus a
``test_program`` that imports / uses that code and prints a final line of the
form ``__TESTS__ <passed> <total>``. The runner parses that line to report the
number of passed tests. If no such line is present, success is inferred from a
zero exit code.
"""
from __future__ import annotations

import os
import re
import resource
import subprocess
import tempfile
import time
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="code-executor")

DEFAULT_TIMEOUT = int(os.getenv("EXECUTION_TIMEOUT_SECONDS", "10"))
DEFAULT_MEMORY_MB = int(os.getenv("EXECUTION_MEMORY_MB", "256"))

TEST_MARKER_RE = re.compile(r"__TESTS__\s+(\d+)\s+(\d+)")


class ExecRequest(BaseModel):
    language: str  # "python" | "javascript"
    program: str  # full program to run (code + embedded test harness)
    timeout: Optional[int] = None
    memory_mb: Optional[int] = None


class ExecResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    passed_tests: int
    total_tests: int
    duration_ms: int
    timed_out: bool


def _limit_resources(memory_mb: int):
    """Pre-exec hook to cap address space (Linux only)."""
    def _set():
        try:
            mem_bytes = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            # Limit number of processes to curb fork bombs.
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except (ValueError, OSError):
            pass
    return _set


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run", response_model=ExecResponse)
def run(req: ExecRequest) -> ExecResponse:
    timeout = req.timeout or DEFAULT_TIMEOUT
    memory_mb = req.memory_mb or DEFAULT_MEMORY_MB

    if req.language == "python":
        filename, cmd = "main.py", ["python", "main.py"]
    elif req.language in ("javascript", "js", "node"):
        filename, cmd = "main.js", ["node", "main.js"]
    else:
        return ExecResponse(
            success=False, stdout="", stderr=f"Unsupported language: {req.language}",
            exit_code=-1, passed_tests=0, total_tests=0, duration_ms=0, timed_out=False,
        )

    with tempfile.TemporaryDirectory() as workdir:
        path = os.path.join(workdir, filename)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(req.program)

        start = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                preexec_fn=_limit_resources(memory_mb),
                env={"PATH": os.environ.get("PATH", ""), "HOME": workdir},
            )
            stdout, stderr, exit_code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = (exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")) \
                + f"\nExecution timed out after {timeout}s."
            exit_code = -1

        duration_ms = int((time.monotonic() - start) * 1000)

    passed, total = 0, 0
    match = TEST_MARKER_RE.search(stdout)
    if match:
        passed, total = int(match.group(1)), int(match.group(2))
        success = (not timed_out) and passed == total and total > 0
    else:
        # No explicit test markers: success == clean exit.
        success = (not timed_out) and exit_code == 0
        total = 1
        passed = 1 if success else 0

    return ExecResponse(
        success=success,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        passed_tests=passed,
        total_tests=total,
        duration_ms=duration_ms,
        timed_out=timed_out,
    )
