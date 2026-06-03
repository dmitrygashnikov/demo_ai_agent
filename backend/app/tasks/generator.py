"""Live LLM task generator with sandbox verification (req. 3, §6.1).

``generate_task(...)`` produces a coding task in the SAME schema as the curated
seed (prompt + visible/hidden tests + reference solution + skill/concept/
language/difficulty) and **proves it is solvable** before it is ever served:
the generated ``reference_solution`` is executed in the sandbox against its own
visible+hidden tests via the existing execution factory. This extends the
project's anti-hallucination guarantee (see ``graph/nodes/self_execution.py``)
to generated content.

Pipeline:
  1. (Optional) gather 2-3 web snippets via ``app.search.web_search`` to ground
     the prompt in the student's ``topic`` (fail-open: skipped if unavailable).
  2. LLM generation via ``chat_json`` with a strict schema-bound system prompt.
  3. Sandbox verification + reflection loop: on failure feed the error back to
     the LLM and regenerate, bounded by ``MAX_REGEN_ATTEMPTS`` (runtime setting)
     — identical philosophy to ``self_execution``.
  4. Persist the verified task via ``app.tasks.dynamic_store`` and return a
     ``Task`` (drop-in for ``app.tasks.repository``).

Fail-open: any LLM/search/verification failure after retries returns ``None``;
callers fall back to curated ``tasks_for_skill(...)``. Never raises.
"""
from __future__ import annotations

import json
import logging

from app.execution.base import TestCase, check_typed_answer
from app.execution.factory import get_executor
from app.llm.client import LLMUnavailable, chat_json
from app.search import web_search
from app.settings_store import get_runtime_settings
from app.tasks.dynamic_store import new_generated_id, save_generated_task
from app.tasks.repository import (
    ANSWER_EXERCISE_TYPES,
    DEFAULT_EXERCISE_TYPE,
    Task,
    normalize_exercise_type,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-exercise-type system prompts (Problem 4). The classic code-producing types
# share one schema (function + tests + reference_solution → verified by running
# the reference against the tests). The answer types (predict_output /
# trace_value) use a DIFFERENT schema: a self-contained ``given_code`` snippet
# that PRINTS its result, plus the ``expected_answer`` the student must type. Its
# verification runs ``given_code`` in the sandbox and checks the produced output
# equals ``expected_answer`` — preserving the anti-hallucination guarantee.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_CODE = (
    "You are an expert programming-exercise author for an adaptive coding tutor. "
    "Produce ONE small, self-contained coding task as STRICT JSON with EXACTLY "
    "these keys:\n"
    '  "prompt": a clear task statement (string),\n'
    '  "entry_point": the exact function name the student must define (string),\n'
    '  "reference_solution": a correct {language} solution defining {entry_point} '
    "(string, source code only),\n"
    '  "visible_tests": a non-empty list of {{"args": [...], "expected": ...}},\n'
    '  "hidden_tests": a non-empty list of {{"args": [...], "expected": ...}},\n'
    '  "difficulty": integer 1-5,\n'
    '  "concept": the concept string{extra_keys}.\n'
    "Hard requirements:\n"
    "- The function must be PURE: no I/O, no randomness, no network, no time.\n"
    "- All test ``args`` and ``expected`` values MUST be JSON-serialisable "
    "(numbers, strings, booleans, null, lists, objects).\n"
    "- ``reference_solution`` MUST pass every visible AND hidden test exactly.\n"
    "- Target language: {language}. Concept: {concept}. Difficulty ~{difficulty}.\n"
    "{type_rule}"
    "- Keep it short and unambiguous. Return JSON only — no prose, no fences."
)

_SYSTEM_PROMPT_ANSWER = (
    "You are an expert programming-exercise author for an adaptive coding tutor. "
    "Produce ONE small 'predict the output / trace the value' exercise as STRICT "
    "JSON with EXACTLY these keys:\n"
    '  "prompt": a clear instruction telling the student to read the code and '
    "type the exact output / final value (string),\n"
    '  "given_code": a SHORT, self-contained {language} snippet that, when run, '
    "PRINTS exactly the value the student must predict (string, source code "
    "only; it MUST print the answer and nothing else),\n"
    '  "expected_answer": the exact text the snippet prints (string),\n'
    '  "difficulty": integer 1-5,\n'
    '  "concept": the concept string.\n'
    "Hard requirements:\n"
    "- ``given_code`` must be PURE and DETERMINISTIC: no input, no randomness, "
    "no network, no time. It must print the answer using "
    "{print_fn}.\n"
    "- ``expected_answer`` MUST equal exactly what ``given_code`` prints.\n"
    "- Target language: {language}. Concept: {concept}. Difficulty ~{difficulty}.\n"
    "- Keep it short and unambiguous. Return JSON only — no prose, no fences."
)

# Per-type extra instruction appended to the CODE system prompt.
_TYPE_RULES = {
    "implement_return": "",
    "find_the_bug": (
        "- This is a FIND-THE-BUG task: also include a key \"given_code\" — a "
        "version of the function that is plausible but BUGGY (fails some tests). "
        "The student fixes it. ``reference_solution`` is the CORRECT version.\n"
    ),
    "fill_in_the_blank": (
        "- This is a FILL-IN-THE-BLANK task: also include a key \"template\" — the "
        "reference_solution with 1-2 critical tokens replaced by ``___`` blanks "
        "the student must complete. ``reference_solution`` is the full answer.\n"
    ),
    "refactor": (
        "- This is a REFACTOR task: also include a key \"given_code\" — working but "
        "ugly/verbose code with the SAME behaviour. The student rewrites it; "
        "``reference_solution`` is a clean version. Both pass the same tests.\n"
    ),
    "conditions_branching": (
        "- Emphasise if/elif/else branching with tests covering each branch.\n"
    ),
    "loops_accumulate": (
        "- Emphasise a loop/accumulator pattern over a collection.\n"
    ),
    "io_transform": (
        "- Emphasise parsing/transforming structured input into output.\n"
    ),
}

# Extra JSON keys mentioned in the CODE schema header per type.
_TYPE_EXTRA_KEYS = {
    "find_the_bug": ',\n  "given_code": a buggy version of the function (string)',
    "refactor": ',\n  "given_code": working-but-ugly equivalent code (string)',
    "fill_in_the_blank": ',\n  "template": the solution with ``___`` blanks (string)',
}


def _system_prompt_for(
    exercise_type: str, language: str, concept: str, difficulty: int
) -> str:
    etype = normalize_exercise_type(exercise_type)
    if etype in ANSWER_EXERCISE_TYPES:
        print_fn = (
            "console.log(...)" if language in ("javascript", "js", "node") else "print(...)"
        )
        return _SYSTEM_PROMPT_ANSWER.format(
            language=language,
            concept=concept,
            difficulty=difficulty,
            print_fn=print_fn,
        )
    return _SYSTEM_PROMPT_CODE.format(
        language=language,
        concept=concept,
        difficulty=difficulty,
        entry_point="{entry_point}",
        type_rule=_TYPE_RULES.get(etype, ""),
        extra_keys=_TYPE_EXTRA_KEYS.get(etype, ""),
    )


def _build_user_prompt(
    language: str,
    concept: str,
    difficulty: int,
    topic: str | None,
    grounding: list[str],
    kind: str,
    exercise_type: str = DEFAULT_EXERCISE_TYPE,
) -> str:
    etype = normalize_exercise_type(exercise_type)
    if etype in ANSWER_EXERCISE_TYPES:
        lead = (
            f"Create a {language} '{etype}' exercise practising the concept "
            f"'{concept}' at difficulty {difficulty}: a short snippet whose "
            f"printed output the student must predict."
        )
    else:
        lead = (
            f"Create a {language} '{etype}' coding task practising the concept "
            f"'{concept}' at difficulty {difficulty} (kind: {kind})."
        )
    parts = [lead]
    if topic:
        parts.append(
            f"Theme the task around: '{topic}'. Use realistic, on-theme framing "
            f"(e.g. domain-appropriate variable names / scenario) while still "
            f"testing '{concept}'."
        )
    if grounding:
        joined = "\n".join(f"- {g}" for g in grounding if g)
        parts.append(
            "For inspiration only (do NOT copy verbatim, do NOT require external "
            f"data), here are real-world snippets:\n{joined}"
        )
    return "\n\n".join(parts)


def _gather_grounding(topic: str | None, concept: str, language: str) -> list[str]:
    """Best-effort web snippets to theme the task. Fail-open → empty list."""
    if not topic:
        return []
    try:
        results = web_search(
            f"{topic} {concept} {language} example problem",
            max_results=3,
        )
    except Exception as exc:  # noqa: BLE001 — search must never block generation
        logger.debug("Grounding search failed (%s); proceeding without", exc)
        return []
    return [r.snippet for r in results if r.snippet][:3]


def _coerce_tests(raw) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for case in raw:
        if isinstance(case, dict) and "args" in case and "expected" in case:
            args = case["args"]
            if not isinstance(args, list):
                args = [args]
            out.append({"args": args, "expected": case["expected"]})
    return out


def _to_test_cases(cases: list[dict]) -> list[TestCase]:
    return [TestCase(args=c["args"], expected=c["expected"]) for c in cases]


def _wrap_snippet_for_capture(language: str, given_code: str, entry_point: str) -> str:
    """Wrap a print-producing snippet so the harness can compare its output.

    Builds a function ``entry_point()`` that runs ``given_code`` while capturing
    stdout and RETURNS the captured text (trimmed). The existing run-against-
    tests harness then compares that return value to ``expected_answer`` — so the
    answer-type verification reuses the SAME sandbox path (no executor change).
    """
    if language in ("javascript", "js", "node"):
        # Capture console.log output by overriding it for the duration of the run.
        indented = "\n".join("    " + ln for ln in given_code.splitlines())
        return (
            f"function {entry_point}() {{\n"
            "  const __lines = [];\n"
            "  const __orig = console.log;\n"
            "  console.log = (...a) => __lines.push(a.join(' '));\n"
            "  try {\n"
            f"{indented}\n"
            "  } finally {\n"
            "    console.log = __orig;\n"
            "  }\n"
            "  return __lines.join('\\n').trim();\n"
            "}\n"
        )
    # Python: capture stdout with contextlib.redirect_stdout.
    indented = "\n".join("        " + ln for ln in given_code.splitlines())
    return (
        "import io as __io\n"
        "import contextlib as __ctx\n"
        f"def {entry_point}():\n"
        "    __buf = __io.StringIO()\n"
        "    with __ctx.redirect_stdout(__buf):\n"
        f"{indented}\n"
        "    return __buf.getvalue().strip()\n"
    )


def _verify_answer_task(task: Task) -> tuple[bool, str]:
    """Verify a predict_output/trace_value task by RUNNING ``given_code``.

    Runs the snippet in the sandbox, captures its printed output and checks it
    equals ``expected_answer`` (tolerant normalisation). This preserves the
    anti-hallucination guarantee: the answer shown to the student is exactly what
    the code actually prints. Fail-open on executor error.
    """
    given = (task.given_code or "").strip()
    expected = (task.expected_answer or "").strip()
    if not given or not expected:
        return False, "answer task missing given_code or expected_answer"
    entry = "__run_snippet"
    wrapper = _wrap_snippet_for_capture(task.language, given, entry)
    try:
        executor = get_executor()
        # A single test: the wrapped snippet's captured output must equal the
        # normalised expected answer. We normalise expected to match the
        # snippet's ``.trim()``/``.strip()`` so a trailing newline never fails it.
        result = executor.run(
            task.language,
            wrapper,
            entry,
            [TestCase(args=[], expected=expected)],
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"executor error: {exc}"

    passed_all = result.total_tests > 0 and result.passed_tests == result.total_tests
    diagnostic = (
        f"answer-check passed {result.passed_tests}/{result.total_tests}; "
        f"stdout={result.stdout[-300:]}; stderr={result.stderr[-300:]}"
    )
    return passed_all, diagnostic


def _verify(task: Task) -> tuple[bool, str]:
    """Verify a generated task in the sandbox (preserves anti-hallucination).

    ``predict_output`` / ``trace_value`` are verified by running ``given_code``
    and checking the printed output equals ``expected_answer``. All code types
    run the reference solution against ALL tests. Returns ``(passed_all,
    diagnostic)``. Fail-open: an executor error counts as a (recoverable)
    verification failure with the error captured for reflection.
    """
    if normalize_exercise_type(task.exercise_type) in ANSWER_EXERCISE_TYPES:
        return _verify_answer_task(task)
    try:
        executor = get_executor()
        result = executor.run(
            task.language,
            task.reference_solution,
            task.entry_point,
            task.all_test_cases(),
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"executor error: {exc}"

    passed_all = (
        result.total_tests > 0 and result.passed_tests == result.total_tests
    )
    diagnostic = (
        f"passed {result.passed_tests}/{result.total_tests}; "
        f"stdout={result.stdout[-500:]}; stderr={result.stderr[-500:]}"
    )
    return passed_all, diagnostic


def _parse_candidate(
    data: dict,
    *,
    language: str,
    skill_id: str,
    concept: str,
    difficulty: int,
    kind: str,
    task_id: str,
    exercise_type: str = DEFAULT_EXERCISE_TYPE,
) -> Task | None:
    if not isinstance(data, dict):
        return None
    etype = normalize_exercise_type(exercise_type)
    prompt = str(data.get("prompt") or "").strip()
    given_code = str(data.get("given_code") or "").strip()
    template = str(data.get("template") or "").strip()
    expected_answer = str(data.get("expected_answer") or "").strip()
    try:
        gen_difficulty = int(data.get("difficulty", difficulty))
    except (TypeError, ValueError):
        gen_difficulty = difficulty
    gen_difficulty = min(max(gen_difficulty, 1), 5)
    concept_val = str(data.get("concept") or concept)

    # Answer types (predict_output / trace_value): no entry_point / tests; instead
    # a printing snippet + the expected typed answer. The reference_solution is
    # set to the snippet so existing consumers (and re-verification) have it.
    if etype in ANSWER_EXERCISE_TYPES:
        if not (prompt and given_code and expected_answer):
            return None
        return Task(
            id=task_id,
            language=language,
            concept=concept_val,
            skill_id=skill_id,
            difficulty=gen_difficulty,
            kind=kind,
            entry_point="",
            prompt=prompt,
            reference_solution=given_code,
            visible_tests=[],
            hidden_tests=[],
            exercise_type=etype,
            given_code=given_code,
            expected_answer=expected_answer,
        )

    # Code-producing types: require a function + tests + reference solution
    # exactly like before.
    entry_point = str(data.get("entry_point") or "").strip()
    reference_solution = str(data.get("reference_solution") or "").strip()
    visible = _coerce_tests(data.get("visible_tests"))
    hidden = _coerce_tests(data.get("hidden_tests"))
    if not (prompt and entry_point and reference_solution and visible and hidden):
        return None
    # find_the_bug / refactor want a given_code; fill_in_the_blank wants a
    # template. If the LLM omitted them, degrade gracefully to implement_return
    # so we still serve a valid, verified task rather than discarding it.
    if etype == "fill_in_the_blank" and not template:
        etype = DEFAULT_EXERCISE_TYPE
    if etype in ("find_the_bug", "refactor") and not given_code:
        etype = DEFAULT_EXERCISE_TYPE
    return Task(
        id=task_id,
        language=language,
        concept=concept_val,
        skill_id=skill_id,
        difficulty=gen_difficulty,
        kind=kind,
        entry_point=entry_point,
        prompt=prompt,
        reference_solution=reference_solution,
        visible_tests=visible,
        hidden_tests=hidden,
        exercise_type=etype,
        given_code=given_code,
        template=template,
    )


def generate_task(
    language: str,
    skill_id: str,
    concept: str,
    difficulty: int,
    topic: str | None = None,
    *,
    kind: str = "practice",
    created_by: str | None = None,
    exercise_type: str | None = None,
) -> Task | None:
    """Generate, sandbox-verify, persist and return a fresh task — or ``None``.

    Only a task whose reference solution passes ALL of its own visible+hidden
    tests is returned (for answer types: whose ``given_code`` actually prints
    ``expected_answer``). On exhaustion of the bounded verify/reflect loop (or
    any LLM/search failure) returns ``None`` so the caller falls back to curated
    content. Never raises.

    ``exercise_type`` (Problem 4) selects the schema/prompt branch; an unknown or
    missing value degrades to ``implement_return`` (today's behaviour).
    """
    etype = normalize_exercise_type(exercise_type)
    max_attempts = int(get_runtime_settings().get("MAX_REGEN_ATTEMPTS", 3))
    grounding = _gather_grounding(topic, concept, language)
    task_id = new_generated_id()

    system = _system_prompt_for(etype, language, concept, difficulty)
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": _build_user_prompt(
                language, concept, difficulty, topic, grounding, kind, etype
            ),
        },
    ]

    for attempt in range(max_attempts):
        try:
            data = chat_json(messages, temperature=0.4)
        except LLMUnavailable as exc:
            logger.warning("Task generation LLM unavailable (%s); falling back", exc)
            return None
        except Exception as exc:  # noqa: BLE001 — never propagate
            logger.warning("Task generation error (%s); falling back", exc)
            return None

        candidate = _parse_candidate(
            data,
            language=language,
            skill_id=skill_id,
            concept=concept,
            difficulty=difficulty,
            kind=kind,
            task_id=task_id,
            exercise_type=etype,
        )
        if candidate is None:
            logger.info(
                "Generated task malformed (attempt %d/%d) for skill=%s",
                attempt + 1,
                max_attempts,
                skill_id,
            )
            if etype in ANSWER_EXERCISE_TYPES:
                retry_msg = (
                    "Your previous output was missing required keys. Return STRICT "
                    "JSON with a non-empty ``given_code`` snippet that PRINTS the "
                    "answer and a matching ``expected_answer``."
                )
            else:
                retry_msg = (
                    "Your previous output was missing required keys or had empty "
                    "tests. Return STRICT JSON with non-empty visible_tests and "
                    "hidden_tests and a complete reference_solution."
                )
            messages.append({"role": "user", "content": retry_msg})
            continue

        passed, diagnostic = _verify(candidate)
        if passed:
            save_generated_task(candidate, topic=topic, created_by=created_by)
            logger.info(
                "Generated+verified task=%s skill=%s concept=%s topic=%r (attempt %d)",
                candidate.id,
                skill_id,
                concept,
                topic,
                attempt + 1,
            )
            return candidate

        logger.info(
            "Generated task failed verification (attempt %d/%d): %s",
            attempt + 1,
            max_attempts,
            diagnostic,
        )
        # Reflection: feed the failing solution + diagnostic back for a fix.
        if etype in ANSWER_EXERCISE_TYPES:
            echo = {
                "prompt": candidate.prompt,
                "given_code": candidate.given_code,
                "expected_answer": candidate.expected_answer,
            }
            fix_msg = (
                "Running ``given_code`` in the sandbox did NOT print "
                f"``expected_answer`` ({diagnostic}). Fix the snippet or the "
                "expected_answer so they agree EXACTLY. Return the corrected "
                "STRICT JSON only."
            )
        else:
            echo = {
                "prompt": candidate.prompt,
                "entry_point": candidate.entry_point,
                "reference_solution": candidate.reference_solution,
                "visible_tests": candidate.visible_tests,
                "hidden_tests": candidate.hidden_tests,
            }
            fix_msg = (
                "Your reference_solution did NOT pass all of its own tests "
                f"in the sandbox ({diagnostic}). Fix either the solution or "
                "the tests so the reference_solution passes EVERY visible and "
                "hidden test. Return the corrected STRICT JSON only."
            )
        messages.append({"role": "assistant", "content": json.dumps(echo)})
        messages.append({"role": "user", "content": fix_msg})

    logger.warning(
        "Task generation exhausted %d attempts for skill=%s; falling back to curated",
        max_attempts,
        skill_id,
    )
    return None
