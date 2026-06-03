"""Topic Guardrail node — keeps the conversation on-topic.

This node runs FIRST (right after entry, before intent routing) and decides
whether the student's message is *on-topic* for a programming tutor: i.e. it is
about programming, the current learning process, a submitted piece of code, a
task, or an error. Off-topic small-talk ("what's a good borscht recipe?") is
politely declined with an invitation to return to learning.

Design notes
------------
* **Hybrid classifier**: a cheap deterministic heuristic (keywords + the
  student's current learning context) runs first. Only genuinely ambiguous
  messages fall through to the LLM classifier (``chat_json``).
* **Fail-open**: if the LLM is unavailable (``LLMUnavailable``) we DEFAULT TO
  ON-TOPIC so a transient observability/LLM outage never blocks a learner. The
  event is logged.
* **Context-aware**: code submissions (``submitted_code`` / intent=code) are
  ALWAYS on-topic. Questions that mention the active ``language`` /
  ``current_skill`` / ``learning_goal`` or generic code/error vocabulary are
  on-topic.
* **Runtime toggle**: behaviour is gated by the ``TOPIC_GUARD_ENABLED`` runtime
  setting (see ``settings_store``). When disabled the node is a no-op and every
  message passes through to normal routing.
"""
from __future__ import annotations

import logging

from app.graph.state import TutorState
from app.llm.client import LLMUnavailable, chat_json

logger = logging.getLogger(__name__)

# Vocabulary that strongly signals an on-topic (programming / learning) message.
_PROGRAMMING_KEYWORDS = {
    # generic programming / CS
    "code", "coding", "program", "programming", "function", "func", "method",
    "variable", "loop", "loops", "array", "list", "dict", "dictionary", "string",
    "int", "float", "bool", "class", "object", "recursion", "algorithm", "data structure",
    "compile", "syntax", "error", "exception", "bug", "debug", "traceback", "stack trace",
    "test", "tests", "unit test", "api", "regex", "iterate", "iteration", "return",
    "argument", "parameter", "import", "module", "package", "library", "framework",
    "exercise", "task", "problem", "challenge", "solution", "solve", "lesson",
    "learn", "practice", "skill", "concept", "example", "explain", "how do i",
    # languages / ecosystem
    "python", "javascript", "js", "java", "typescript", "node", "react", "sql",
    "html", "css", "git", "docker", "linux", "terminal", "command line",
    "print", "console.log", "def ", "for ", "while ", "if ", "else", "elif",
    "async", "await", "promise", "callback", "closure", "pointer", "memory",
    # russian programming vocabulary
    "код", "программ", "функци", "переменн", "цикл", "массив", "список", "словар",
    "строк", "класс", "объект", "рекурси", "алгоритм", "ошибк", "исключени",
    "отлад", "тест", "задач", "задани", "решени", "урок", "изуч", "научит",
    "пример", "объясн", "питон", "джаваскрипт", "цикла", "циклы", "циклов",
}

# Vocabulary that strongly signals an OFF-topic message (used as a tie-breaker
# only — never on its own, because many words are ambiguous).
_OFFTOPIC_KEYWORDS = {
    "recipe", "borscht", "borsch", "cook", "cooking", "weather", "football",
    "soccer", "movie", "film", "song", "joke", "horoscope", "stock price",
    "dating", "girlfriend", "boyfriend", "politics", "president", "vacation",
    "рецепт", "борщ", "погод", "футбол", "фильм", "песн", "анекдот", "гороскоп",
    "отпуск", "политик", "президент", "приготов", "готовит",
}

_SYSTEM = (
    "You are a topic classifier for a PROGRAMMING TUTOR. Decide if the user's "
    "message is ON-TOPIC. On-topic = anything about programming, software, the "
    "current learning process, a coding task/exercise, submitted code, or a "
    "programming error. Off-topic = unrelated small talk (recipes, weather, "
    "sports, movies, politics, etc.). "
    'Return JSON: {"on_topic": true|false, "reason": "short"}. '
    "When in doubt, prefer on_topic=true."
)


def _polite_refusal(language: str | None, current_skill: str | None,
                    learning_goal: str | None) -> str:
    lang = language or "programming"
    if current_skill:
        focus = f"the current topic ({current_skill})"
    elif learning_goal:
        focus = f"your goal: {learning_goal}"
    else:
        focus = "your current lesson"
    return (
        f"I'm a programming tutor, so I can only help with learning {lang} and "
        f"your coding practice. That question is outside what I can help with. "
        f"Let's get back to {focus} — ask me about the concept, a task, your "
        f"code, or an error you're seeing."
    )


def _heuristic(message: str, state: TutorState) -> bool | None:
    """Return True (on-topic), False (off-topic) or None (uncertain → ask LLM)."""
    text = (message or "").lower().strip()
    if not text:
        # Empty message alongside no code: let routing/clarify handle it.
        return True

    # Context: if the message references the active language / skill / goal it's
    # almost certainly about the current learning process.
    for ctx in (state.get("language"), state.get("current_skill"),
                state.get("learning_goal")):
        if ctx and isinstance(ctx, str) and ctx.lower() in text:
            return True

    has_prog = any(k in text for k in _PROGRAMMING_KEYWORDS)
    has_off = any(k in text for k in _OFFTOPIC_KEYWORDS)

    if has_prog and not has_off:
        return True
    if has_off and not has_prog:
        return False
    if has_prog and has_off:
        # Mixed signals — defer to the LLM.
        return None
    # No strong signal either way.
    return None


def topic_guard(state: TutorState) -> dict:
    """Classify on/off-topic and set ``off_topic`` accordingly.

    Reads the ``TOPIC_GUARD_ENABLED`` runtime flag; when disabled it is a no-op
    (always on-topic). Code submissions are always on-topic.
    """
    # Runtime toggle (best-effort: default ON if settings unavailable).
    enabled = True
    try:
        from app.settings_store import get_runtime_settings

        enabled = bool(get_runtime_settings().get("TOPIC_GUARD_ENABLED", True))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Topic guard settings read failed (%s); assuming enabled", exc)

    if not enabled:
        return {"off_topic": False}

    # Code submissions are unambiguously on-topic.
    if state.get("submitted_code") or state.get("intent") == "code":
        return {"off_topic": False}

    message = state.get("user_message", "") or ""

    decision = _heuristic(message, state)
    source = "heuristic"

    if decision is None:
        # Ambiguous — consult the LLM, but FAIL-OPEN on any LLM problem.
        try:
            result = chat_json(
                [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": message},
                ],
                temperature=0,
            )
            if "on_topic" in result:
                decision = bool(result.get("on_topic"))
                source = "llm"
            else:
                decision = True  # malformed response → fail-open
                source = "llm-malformed-failopen"
        except LLMUnavailable as exc:
            logger.warning(
                "Topic guard LLM unavailable (%s); failing open (on-topic)", exc
            )
            decision = True
            source = "llm-unavailable-failopen"

    on_topic = bool(decision)
    if not on_topic:
        refusal = _polite_refusal(
            state.get("language"),
            state.get("current_skill"),
            state.get("learning_goal"),
        )
        logger.info("Topic guard: OFF-TOPIC (source=%s)", source)
        return {
            "off_topic": True,
            "agent_response": refusal,
            "next_action": "respond",
        }

    logger.info("Topic guard: on-topic (source=%s)", source)
    return {"off_topic": False}
