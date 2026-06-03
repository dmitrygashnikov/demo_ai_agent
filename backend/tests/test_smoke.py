"""Lightweight smoke tests for pure-logic components (no external services)."""
import sys
from dataclasses import dataclass

sys.path.insert(0, "backend")

from app.execution.base import TestCase, build_js_program, build_python_program  # noqa: E402
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


if __name__ == "__main__":
    test_python_harness_marker()
    test_js_harness_builds()
    test_cooldown_filter()
    test_topic_guard_heuristic_off_topic()
    test_topic_guard_heuristic_on_topic()
    print("ALL SMOKE TESTS PASSED")
