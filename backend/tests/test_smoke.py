"""Lightweight smoke tests for pure-logic components (no external services)."""
import sys
from dataclasses import dataclass

sys.path.insert(0, "backend")

from app.execution.base import TestCase, build_js_program, build_python_program  # noqa: E402
from app.tasks.uniqueness import COOLDOWN_SOLVES, filter_unique_tasks  # noqa: E402


@dataclass
class _T:
    id: str


def test_python_harness_marker():
    code = "def add(a, b):\n    return a + b\n"
    prog = build_python_program(code, "add", [TestCase([1, 2], 3), TestCase([2, 2], 4)])
    ns: dict = {}
    exec(prog, ns)  # should print __TESTS__ 2 2 (captured by runner in prod)


def test_js_harness_builds():
    prog = build_js_program("function f(x){return x;}", "f", [TestCase([1], 1)])
    assert "__TESTS__" in prog
    assert "function f" in prog


def test_cooldown_filter():
    assert COOLDOWN_SOLVES == 500
    cands = [_T("a"), _T("b"), _T("c")]
    hist = {"a": 10, "b": 400}
    # At solve_count 520: a (520-10=510 >= 500) allowed, b (120 < 500) blocked, c never served.
    allowed = {t.id for t in filter_unique_tasks("u", cands, 520, hist)}
    assert "a" in allowed and "c" in allowed and "b" not in allowed
    # At 450: a (440 < 500) blocked, b blocked, c allowed.
    allowed2 = {t.id for t in filter_unique_tasks("u", cands, 450, hist)}
    assert allowed2 == {"c"}


if __name__ == "__main__":
    test_python_harness_marker()
    test_js_harness_builds()
    test_cooldown_filter()
    print("ALL SMOKE TESTS PASSED")
