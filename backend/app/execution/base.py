"""CodeExecutor strategy interface and shared data structures (req. 6).

A ``TestCase`` describes a single check: given ``code`` defining a function,
call ``entry_point`` with ``args`` and compare the (JSON-serialisable) result to
``expected``. We build a language-specific harness from these test cases so the
sandbox can report passed/total objectively.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestCase:
    args: list[Any]
    expected: Any
    name: str = ""


@dataclass
class ExecutionResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    passed_tests: int
    total_tests: int
    duration_ms: int
    timed_out: bool = False


class CodeExecutor(ABC):
    """Strategy interface for running code with tests in a sandbox."""

    @abstractmethod
    def run(
        self,
        language: str,
        code: str,
        entry_point: str,
        tests: list[TestCase],
    ) -> ExecutionResult:
        ...


# ----------------------------------------------------------------------------
# Harness builders — turn (code + entry_point + tests) into a runnable program
# that prints "__TESTS__ <passed> <total>" (parsed by the executor).
# ----------------------------------------------------------------------------

def build_python_program(code: str, entry_point: str, tests: list[TestCase]) -> str:
    cases = [{"args": t.args, "expected": t.expected} for t in tests]
    cases_json = json.dumps(cases)
    return f'''\
import json

{code}

__CASES = json.loads({cases_json!r})
__passed = 0
__total = len(__CASES)
for __c in __CASES:
    try:
        __res = {entry_point}(*__c["args"])
        if __res == __c["expected"]:
            __passed += 1
        else:
            print("FAIL: args=%s expected=%s got=%s" % (__c["args"], __c["expected"], __res))
    except Exception as __e:
        print("ERROR: args=%s -> %s" % (__c["args"], __e))
print("__TESTS__ %d %d" % (__passed, __total))
'''


def build_js_program(code: str, entry_point: str, tests: list[TestCase]) -> str:
    cases = [{"args": t.args, "expected": t.expected} for t in tests]
    cases_json = json.dumps(cases)
    return f'''\
{code}

const __CASES = {cases_json};
let __passed = 0;
const __total = __CASES.length;
for (const __c of __CASES) {{
  try {{
    const __res = {entry_point}(...__c.args);
    if (JSON.stringify(__res) === JSON.stringify(__c.expected)) {{
      __passed += 1;
    }} else {{
      console.log("FAIL: args=" + JSON.stringify(__c.args) + " expected=" + JSON.stringify(__c.expected) + " got=" + JSON.stringify(__res));
    }}
  }} catch (e) {{
    console.log("ERROR: args=" + JSON.stringify(__c.args) + " -> " + e);
  }}
}}
console.log("__TESTS__ " + __passed + " " + __total);
'''


def build_program(language: str, code: str, entry_point: str, tests: list[TestCase]) -> str:
    if language == "python":
        return build_python_program(code, entry_point, tests)
    if language in ("javascript", "js", "node"):
        return build_js_program(code, entry_point, tests)
    raise ValueError(f"Unsupported language: {language}")


# ----------------------------------------------------------------------------
# Answer-checking path for non-code exercise types (Problem 4).
#
# ``predict_output`` / ``trace_value`` ask the student to TYPE an expected value
# (the printed output or a traced variable), not to write a function. There is
# no ``entry_point`` to call, so the existing run-against-tests harness does not
# apply. We compare the student's typed answer to the task's ``expected_answer``
# with tolerant normalisation so trivial formatting differences (extra spaces,
# trailing newline, surrounding quotes, casing) don't reject a correct answer.
# This is a pure, deterministic check — it never touches the sandbox and never
# raises — so it cannot break the existing failure path (Problems 1-3) or the
# classic ``implement_return`` flow.
# ----------------------------------------------------------------------------

def _normalize_answer(text: str) -> str:
    s = str(text or "").strip()
    # Strip a single pair of surrounding quotes a student may add around a string.
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1]
    # Collapse all runs of whitespace (incl. newlines) to a single space so
    # "0\n1\n2" matches "0 1 2" and "8  5" matches "8 5".
    s = " ".join(s.split())
    return s.casefold()


def check_typed_answer(submitted: str, expected_answer: str) -> ExecutionResult:
    """Compare a student's typed answer to ``expected_answer`` (1 logical test).

    Returns an ``ExecutionResult`` shaped exactly like a sandbox run so the rest
    of the pipeline (``code_validator`` → success/failure routing, the
    ``ERROR:``/``FAIL:`` stdout convention consumed by ``extract_student_error``)
    works unchanged. A mismatch emits a ``FAIL:`` line on stdout — the same shape
    the harness uses — so the fail-path explanation stays grounded in the real
    submitted value.
    """
    expected_norm = _normalize_answer(expected_answer)
    got_norm = _normalize_answer(submitted)
    passed = expected_norm == got_norm and expected_norm != ""
    if passed:
        stdout = "__TESTS__ 1 1\n"
    else:
        got_display = str(submitted or "").strip() or "(empty)"
        stdout = (
            f"FAIL: args=[] expected={expected_answer!r} got={got_display!r}\n"
            "__TESTS__ 0 1\n"
        )
    return ExecutionResult(
        success=passed,
        stdout=stdout,
        stderr="",
        exit_code=0,
        passed_tests=1 if passed else 0,
        total_tests=1,
        duration_ms=0,
        timed_out=False,
    )
