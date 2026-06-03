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
