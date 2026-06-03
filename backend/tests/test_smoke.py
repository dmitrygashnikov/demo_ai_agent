"""Lightweight smoke tests for pure-logic components (no external services)."""
import sys
from dataclasses import dataclass

sys.path.insert(0, "backend")

from app.execution.base import TestCase, build_js_program, build_python_program  # noqa: E402
from app.graph.nodes._error_utils import (  # noqa: E402
    classify_from_error,
    detect_input_issue,
    extract_student_error,
    parse_harness_stdout,
)
from app.graph.nodes.topic_guard import _heuristic, topic_guard  # noqa: E402
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


def test_password_hash_roundtrip():
    # bcrypt hashing + verification round-trips and rejects wrong passwords.
    from app.auth.security import hash_password, verify_password

    h = hash_password("qwerty123456")
    assert h and h != "qwerty123456"
    assert verify_password("qwerty123456", h) is True
    assert verify_password("wrong-password", h) is False


def test_jwt_roundtrip():
    # A signed token decodes back to the same subject; tampered tokens fail.
    from app.auth.security import create_access_token, decode_access_token

    token = create_access_token("user-123", {"email": "a@b.c"})
    claims = decode_access_token(token)
    assert claims is not None
    assert claims["sub"] == "user-123"
    assert claims["email"] == "a@b.c"
    assert decode_access_token(token + "tampered") is None
    assert decode_access_token("not-a-token") is None


def test_topic_guard_heuristic_off_topic():
    # A clearly off-topic question is classified off-topic by the pure heuristic
    # (no LLM call needed).
    assert _heuristic("какой рецепт борща?", {}) is False
    assert _heuristic("what's a good borscht recipe?", {}) is False


def test_topic_guard_heuristic_on_topic():
    # Programming questions (loops / code) are on-topic via the heuristic.
    assert _heuristic("how do for loops work in python?", {}) is True
    assert _heuristic("объясни циклы в питоне", {}) is True
    # A question that references the active learning context is on-topic.
    assert _heuristic("can you give an example?", {"current_skill": "py_loops"}) is True


def test_topic_guard_node_off_topic_refusal(monkeypatch):
    # Force the runtime flag ON without touching Redis/Postgres.
    import app.graph.nodes.topic_guard as tg

    monkeypatch.setattr(tg, "get_runtime_settings", lambda: {"TOPIC_GUARD_ENABLED": True}, raising=False)
    # Patch the module-level import path used inside the node.
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.settings_store",
        type("M", (), {"get_runtime_settings": staticmethod(lambda: {"TOPIC_GUARD_ENABLED": True})}),
    )
    out = topic_guard({"user_message": "какой рецепт борща?", "language": "python"})
    assert out.get("off_topic") is True
    assert out.get("next_action") == "respond"
    assert "programming" in out.get("agent_response", "").lower()


def test_topic_guard_node_code_always_on_topic(monkeypatch):
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.settings_store",
        type("M", (), {"get_runtime_settings": staticmethod(lambda: {"TOPIC_GUARD_ENABLED": True})}),
    )
    out = topic_guard({"user_message": "", "submitted_code": "def f():\n    return 1\n"})
    assert out.get("off_topic") is False


def test_topic_guard_disabled_passthrough(monkeypatch):
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.settings_store",
        type("M", (), {"get_runtime_settings": staticmethod(lambda: {"TOPIC_GUARD_ENABLED": False})}),
    )
    # Even a clearly off-topic message passes through when guard is disabled.
    out = topic_guard({"user_message": "какой рецепт борща?"})
    assert out.get("off_topic") is False


# ---------------------------------------------------------------------------
# Fail-path remediation fix (Problems 1-3)
# ---------------------------------------------------------------------------

def test_parse_harness_stdout_errors_and_fails():
    stdout = (
        "ERROR: args=[5, 0] -> division by zero\n"
        "FAIL: args=[1, 2] expected=3 got=2\n"
        "__TESTS__ 0 2\n"
    )
    parsed = parse_harness_stdout(stdout)
    assert parsed["errors"] == [{"args": "[5, 0]", "msg": "division by zero"}]
    assert parsed["fails"] == [{"args": "[1, 2]", "expected": "3", "got": "2"}]


def test_extract_student_error_runtime_in_stdout():
    # Real per-test runtime error lives in stdout; stderr is empty (see §0.1).
    exec_result = {
        "stdout": "ERROR: args=[3] -> 'int' object is not subscriptable\n__TESTS__ 0 1\n",
        "stderr": "",
        "passed_tests": 0,
        "total_tests": 1,
        "timed_out": False,
    }
    se = extract_student_error(exec_result)
    assert "not subscriptable" in se["summary"]
    assert se["symbol"] == "TypeError" or se["errors"]  # symbol derived if present
    # A TypeError mention should classify as type_error from the real signal.
    exec_result["stdout"] = "ERROR: args=[3] -> TypeError: bad operand\n__TESTS__ 0 1\n"
    se2 = extract_student_error(exec_result)
    assert classify_from_error(se2, exec_result) == "type_error"


def test_extract_student_error_logic_fail():
    exec_result = {
        "stdout": "FAIL: args=[2] expected=4 got=5\n__TESTS__ 0 1\n",
        "stderr": "",
        "passed_tests": 0,
        "total_tests": 1,
    }
    se = extract_student_error(exec_result)
    assert "expected" in se["summary"] and "got" not in se["summary"].split("returned")[0]
    # No runtime exception → deterministic classifier returns None (→ LLM/logic).
    assert classify_from_error(se, exec_result) is None


def test_extract_student_error_timeout():
    se = extract_student_error({"timed_out": True, "stdout": "", "stderr": ""})
    assert se["timed_out"] is True
    assert classify_from_error(se, {"timed_out": True}) == "timeout"


def test_detect_input_issue_empty():
    d = detect_input_issue("   \n  ", "python")
    assert d is not None and d["kind"] == "empty"


def test_detect_input_issue_prose_python_syntax():
    # Plain prose is not valid Python → compile() SyntaxError.
    d = detect_input_issue("this is just a sentence about loops, not code", "python")
    assert d is not None and d["kind"] == "syntax"


def test_detect_input_issue_valid_code_returns_none():
    assert detect_input_issue("def f(x):\n    return x + 1\n", "python") is None


def test_remediation_message_order(monkeypatch):
    # The remediation message must read: trace → Explanation+links → example.
    # ``remediation`` imports the RAG video retriever which (optionally) pulls in
    # qdrant_client; stub it so the test runs without the optional dependency.
    import types as _types

    if "app.rag.retriever" not in sys.modules:
        _stub = _types.ModuleType("app.rag.retriever")
        _stub.retrieve_video_for_error = lambda *a, **k: []  # type: ignore[attr-defined]
        sys.modules["app.rag.retriever"] = _stub
    import app.graph.nodes.remediation as rem

    monkeypatch.setattr(rem, "retrieve_video_for_error", lambda *a, **k: [])
    monkeypatch.setattr(rem, "concept_of", lambda *a, **k: "loops")

    class _Task:
        language = "python"
        reference_solution = "def f(x):\n    return x + 1\n"

    monkeypatch.setattr(rem, "get_task", lambda *a, **k: _Task())

    state = {
        "language": "python",
        "current_skill": "py_loops",
        "current_task_id": "t1",
        "last_error_type": "type_error",
        "execution_result": {"passed_tests": 0, "total_tests": 2},
        "student_error": {"summary": "For input [3] your function raised: boom", "symbol": "TypeError"},
        "error_explanation": "You indexed an int, which isn't subscriptable.",
        "remediation_links": [{"title": "Docs", "url": "http://x"}],
    }
    out = rem.remediation_planner(state)
    resp = out["agent_response"]
    i_trace = resp.index("does not solve")
    i_expl = resp.index("Explanation:")
    i_links = resp.index("Watch / 📖 Read")
    i_example = resp.index("Example of a correct solution")
    assert i_trace < i_expl < i_links < i_example
    # No "ask me for a similar task" trailer (the task is appended by selector).
    assert "ask me for a similar task" not in resp
    assert out["next_action"] == "select_task"


def test_task_selector_preserves_remediation_prefix(monkeypatch):
    import app.graph.nodes.task_selector as ts

    monkeypatch.setattr(ts, "get_solve_count", lambda *a, **k: 0)
    monkeypatch.setattr(ts, "record_serve", lambda *a, **k: None)
    monkeypatch.setattr(ts, "filter_unique_tasks", lambda u, pool, sc: pool)
    monkeypatch.setattr(ts, "_maybe_generate", lambda **k: None)

    class _Task:
        id = "t2"
        language = "python"
        difficulty = 2
        kind = "similar"
        entry_point = "f"
        prompt = "Write a function."

    monkeypatch.setattr(ts, "tasks_for_skill", lambda *a, **k: [_Task()])

    remediation_text = "❌ trace...\n\n**Explanation:** because reasons"
    state = {
        "current_skill": "py_loops",
        "user_id": "",
        "last_passed": False,
        "agent_response": remediation_text,
        "skill_state": "remediation",
    }
    out = ts.task_selector(state)
    resp = out["agent_response"]
    # Remediation analysis preserved AND the similar task appended after it.
    assert resp.startswith(remediation_text)
    assert "🔁 **Try a similar task:**" in resp
    assert resp.index(remediation_text) < resp.index("Try a similar task")


# ---------------------------------------------------------------------------
# Exercise-type diversity (Problem 4)
# ---------------------------------------------------------------------------

def test_normalize_exercise_type_failopen():
    from app.tasks.repository import normalize_exercise_type

    assert normalize_exercise_type("predict_output") == "predict_output"
    assert normalize_exercise_type("find_the_bug") == "find_the_bug"
    # Unknown / missing / empty → implement_return (backward compat + fail-open).
    assert normalize_exercise_type("totally_unknown_type") == "implement_return"
    assert normalize_exercise_type(None) == "implement_return"
    assert normalize_exercise_type("") == "implement_return"


def test_task_default_exercise_type_backward_compat():
    # A curated dict WITHOUT exercise_type defaults to implement_return.
    from app.tasks.repository import _make_task

    t = _make_task(
        {
            "id": "x",
            "language": "python",
            "concept": "loops",
            "skill_id": "py_loops",
            "difficulty": 1,
            "kind": "practice",
            "entry_point": "f",
            "prompt": "p",
            "reference_solution": "def f():\n    return 1\n",
            "visible_tests": [{"args": [], "expected": 1}],
            "hidden_tests": [{"args": [], "expected": 1}],
        }
    )
    assert t.exercise_type == "implement_return"
    assert t.is_answer_type() is False


def test_curated_has_diverse_exercise_types():
    # Early skills must carry ≥3 DISTINCT exercise types (variety in essence).
    from collections import defaultdict

    from app.seed.content.curated import TASKS
    from app.tasks.repository import normalize_exercise_type

    by_skill: dict[str, set] = defaultdict(set)
    for t in TASKS:
        by_skill[t["skill_id"]].add(normalize_exercise_type(t.get("exercise_type")))

    for skill in ("py_variables", "py_io", "py_loops", "js_variables"):
        assert len(by_skill[skill]) >= 3, f"{skill} has too few exercise types: {by_skill[skill]}"
    # The diversified set must include real non-implement types.
    all_types = set().union(*by_skill.values())
    assert "predict_output" in all_types
    assert "find_the_bug" in all_types


def test_check_typed_answer_predict():
    # predict_output / trace_value: compare a TYPED answer to expected (tolerant).
    from app.execution.base import check_typed_answer

    ok = check_typed_answer("8 5", "8 5")
    assert ok.success and ok.passed_tests == 1 and ok.total_tests == 1

    # Tolerant normalisation: whitespace + surrounding quotes + trailing newline.
    assert check_typed_answer("  8   5 \n", "8 5").success is True
    assert check_typed_answer("'Hello, Ada!'", "Hello, Ada!").success is True
    assert check_typed_answer("0\n1\n2", "0 1 2").success is True

    bad = check_typed_answer("9 5", "8 5")
    assert bad.success is False and bad.passed_tests == 0
    # A mismatch emits the harness FAIL: convention so the fail-path stays grounded.
    assert "FAIL:" in bad.stdout
    # Empty answer never accidentally passes.
    assert check_typed_answer("", "anything").success is False


def test_curated_predict_tasks_are_answer_type():
    # The curated predict/trace tasks load as answer types with an expected_answer.
    from app.tasks.repository import get_task

    for tid in ("py_loops_predict_range", "py_variables_trace_swap", "py_io_predict_fstring"):
        t = get_task(tid)
        assert t is not None, tid
        assert t.is_answer_type() is True
        assert t.expected_answer
        assert t.given_code


def test_curated_predict_expected_matches_actual_output():
    # Anti-hallucination: the curated predict/trace expected_answer must equal
    # what the canonical runnable code (reference_solution, which PRINTS the
    # answer) actually outputs. For predict tasks given_code already prints; for
    # trace tasks given_code is shown as-is (no print) and reference_solution is
    # the runnable, answer-printing version.
    import contextlib
    import io

    from app.execution.base import _normalize_answer
    from app.tasks.repository import get_task

    for tid in ("py_loops_predict_range", "py_variables_trace_swap", "py_io_predict_fstring"):
        t = get_task(tid)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exec(compile(t.reference_solution, "<curated>", "exec"), {})
        actual = buf.getvalue().strip()
        assert _normalize_answer(actual) == _normalize_answer(t.expected_answer), tid


def test_task_selector_rotates_exercise_type(monkeypatch):
    import app.graph.nodes.task_selector as ts

    monkeypatch.setattr(ts, "get_solve_count", lambda *a, **k: 0)
    monkeypatch.setattr(ts, "record_serve", lambda *a, **k: None)
    monkeypatch.setattr(ts, "filter_unique_tasks", lambda u, pool, sc: pool)
    monkeypatch.setattr(ts, "_maybe_generate", lambda **k: None)

    class _Task:
        def __init__(self, tid, etype):
            self.id = tid
            self.language = "python"
            self.difficulty = 1
            self.kind = "practice"
            self.entry_point = "f"
            self.prompt = "Do a thing."
            self.exercise_type = etype
            self.given_code = ""
            self.template = ""
            self.expected_answer = ""

    pool = [_Task("a", "implement_return"), _Task("b", "predict_output")]
    monkeypatch.setattr(ts, "tasks_for_skill", lambda *a, **k: pool)

    # Last served was implement_return → selector must pick a DIFFERENT type.
    state = {
        "current_skill": "py_loops",
        "user_id": "",
        "last_exercise_type": "implement_return",
        "skill_state": "practicing",
    }
    out = ts.task_selector(state)
    assert out["last_exercise_type"] == "predict_output"
    assert out["current_task_id"] == "b"


def test_task_selector_rotation_failopen_no_variety(monkeypatch):
    # When only ONE type is available, rotation degrades gracefully (no dead-end).
    import app.graph.nodes.task_selector as ts

    monkeypatch.setattr(ts, "get_solve_count", lambda *a, **k: 0)
    monkeypatch.setattr(ts, "record_serve", lambda *a, **k: None)
    monkeypatch.setattr(ts, "filter_unique_tasks", lambda u, pool, sc: pool)
    monkeypatch.setattr(ts, "_maybe_generate", lambda **k: None)

    class _Task:
        id = "only"
        language = "python"
        difficulty = 1
        kind = "practice"
        entry_point = "f"
        prompt = "Do a thing."
        exercise_type = "implement_return"
        given_code = ""
        template = ""
        expected_answer = ""

    monkeypatch.setattr(ts, "tasks_for_skill", lambda *a, **k: [_Task()])
    state = {
        "current_skill": "py_loops",
        "user_id": "",
        "last_exercise_type": "implement_return",
        "skill_state": "practicing",
    }
    out = ts.task_selector(state)
    assert out["current_task_id"] == "only"
    assert out["last_exercise_type"] == "implement_return"


def test_render_task_prompt_predict_no_define_function():
    import app.graph.nodes.task_selector as ts

    class _Task:
        language = "python"
        difficulty = 1
        prompt = "What does it print?"
        exercise_type = "predict_output"
        given_code = "print(1 + 1)"
        template = ""
        entry_point = ""

    rendered = ts._render_task_prompt(_Task())
    # predict/trace must NOT instruct the student to define a function.
    assert "Define a function" not in rendered
    assert "print(1 + 1)" in rendered

    class _ImplTask:
        language = "python"
        difficulty = 1
        prompt = "Write f."
        exercise_type = "implement_return"
        given_code = ""
        template = ""
        entry_point = "f"

    impl = ts._render_task_prompt(_ImplTask())
    assert "Define a function named `f`" in impl


if __name__ == "__main__":
    test_python_harness_marker()
    test_js_harness_builds()
    test_cooldown_filter()
    test_topic_guard_heuristic_off_topic()
    test_topic_guard_heuristic_on_topic()
    test_parse_harness_stdout_errors_and_fails()
    test_extract_student_error_runtime_in_stdout()
    test_extract_student_error_logic_fail()
    test_extract_student_error_timeout()
    test_detect_input_issue_empty()
    test_detect_input_issue_prose_python_syntax()
    test_detect_input_issue_valid_code_returns_none()
    print("ALL SMOKE TESTS PASSED")
