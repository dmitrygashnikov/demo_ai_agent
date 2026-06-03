"""Shared helpers to surface the *real* student error on the failure path.

The sandbox harness (:func:`app.execution.base.build_python_program` /
``build_js_program``) wraps every test call in a ``try/except`` and prints the
real per-test diagnostics to **stdout**:

  - ``ERROR: args=<args> -> <exception message>`` — a runtime exception thrown
    inside the student's function for that test case.
  - ``FAIL: args=<args> expected=<expected> got=<got>`` — the function ran but
    returned the wrong value.

Only a *top-level* failure (a ``SyntaxError`` / ``IndentationError`` that stops
the module importing, or an undefined ``entry_point`` → ``NameError`` at the
harness call site) yields a real traceback on **stderr**.

Historically nothing downstream read these signals: the explanation was
generated from generic web snippets, producing hallucinated advice unrelated to
the student's actual input. These helpers extract the real error so the
classifier, the explanation generator and the remediation message can all be
*grounded in the student's submitted code and the real sandbox error*.

Everything here is pure / deterministic and never raises — callers rely on it
on the fail-open remediation path.
"""
from __future__ import annotations

import re
from typing import Any

# Cap how many parsed diagnostic lines we surface so the explanation prompt and
# the student-facing trace stay concise.
_MAX_CASES = 5
# Cap stderr length fed to the LLM / shown in the trace (a full traceback can be
# long; the head + tail carry the useful signal).
_MAX_STDERR_CHARS = 1200

_ERROR_LINE_RE = re.compile(r"^ERROR:\s*args=(?P<args>.*?)\s*->\s*(?P<msg>.*)$")
_FAIL_LINE_RE = re.compile(
    r"^FAIL:\s*args=(?P<args>.*?)\s*expected=(?P<expected>.*?)\s*got=(?P<got>.*)$"
)

# Common runtime/exception symbols → our internal error_type taxonomy. Used both
# to classify and to enrich the search query with the concrete error symbol.
_EXCEPTION_TO_TYPE = [
    ("syntaxerror", "syntax"),
    ("indentationerror", "syntax"),
    ("unexpected token", "syntax"),
    ("typeerror", "type_error"),
    ("indexerror", "off_by_one"),
    ("rangeerror", "off_by_one"),
    ("out of range", "off_by_one"),
    ("keyerror", "runtime"),
    ("valueerror", "runtime"),
    ("zerodivisionerror", "runtime"),
    ("attributeerror", "runtime"),
    ("nameerror", "runtime"),
    ("referenceerror", "runtime"),
    ("recursionerror", "performance"),
]

# Exception symbol regex (e.g. ``TypeError``) used to pull the concrete symbol
# out of a traceback / ERROR line for targeted links.
_SYMBOL_RE = re.compile(r"\b([A-Z][A-Za-z]*(?:Error|Exception|Warning))\b")


def parse_harness_stdout(stdout: str) -> dict[str, list[dict[str, str]]]:
    """Parse the harness stdout into structured ``errors`` / ``fails`` lists.

    Returns ``{"errors": [{args, msg}], "fails": [{args, expected, got}]}``.
    ``errors`` are per-test runtime exceptions; ``fails`` are wrong-but-running
    results. Never raises.
    """
    errors: list[dict[str, str]] = []
    fails: list[dict[str, str]] = []
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _ERROR_LINE_RE.match(line)
        if m:
            errors.append({"args": m.group("args").strip(), "msg": m.group("msg").strip()})
            continue
        m = _FAIL_LINE_RE.match(line)
        if m:
            fails.append(
                {
                    "args": m.group("args").strip(),
                    "expected": m.group("expected").strip(),
                    "got": m.group("got").strip(),
                }
            )
    return {"errors": errors, "fails": fails}


def _trim_stderr(stderr: str) -> str:
    s = (stderr or "").strip()
    if len(s) <= _MAX_STDERR_CHARS:
        return s
    head = s[: _MAX_STDERR_CHARS // 2]
    tail = s[-_MAX_STDERR_CHARS // 2 :]
    return f"{head}\n...\n{tail}"


def extract_student_error(exec_result: dict | None) -> dict[str, Any]:
    """Build a concise, *real* error summary from the execution result.

    Combines the top-level ``stderr`` traceback (syntax / undefined entry point)
    with the per-test ``ERROR:`` / ``FAIL:`` diagnostics scraped from ``stdout``.

    Returns a dict::

        {
            "summary": str,            # human-readable real-error summary
            "stderr": str,             # trimmed top-level traceback (may be "")
            "errors": [ {args, msg} ], # runtime exceptions per case
            "fails":  [ {args, expected, got} ],
            "symbol": str | None,      # concrete exception symbol e.g. TypeError
            "timed_out": bool,
        }

    Never raises; degrades to an empty-ish summary when nothing is available.
    """
    exec_result = exec_result or {}
    stderr = _trim_stderr(exec_result.get("stderr", "") or "")
    parsed = parse_harness_stdout(exec_result.get("stdout", "") or "")
    errors = parsed["errors"][:_MAX_CASES]
    fails = parsed["fails"][:_MAX_CASES]
    timed_out = bool(exec_result.get("timed_out"))

    # Determine the concrete exception symbol (prefer stderr, then ERROR lines).
    symbol = None
    sym_match = _SYMBOL_RE.search(stderr)
    if sym_match:
        symbol = sym_match.group(1)
    if symbol is None:
        for e in errors:
            sm = _SYMBOL_RE.search(e["msg"])
            if sm:
                symbol = sm.group(1)
                break

    # Build a human-readable summary grounded in the real signals.
    lines: list[str] = []
    if timed_out:
        lines.append(
            "Your code timed out before finishing — this usually means an "
            "infinite loop (a loop whose exit condition is never met)."
        )
    if stderr:
        lines.append("The program failed before any test could run:\n" + stderr)
    for e in errors:
        lines.append(f"For input {e['args']} your function raised: {e['msg']}")
    for f in fails:
        lines.append(
            f"For input {f['args']} your function returned {f['got']} "
            f"but the expected result was {f['expected']}."
        )

    summary = "\n".join(lines).strip()

    return {
        "summary": summary,
        "stderr": stderr,
        "errors": errors,
        "fails": fails,
        "symbol": symbol,
        "timed_out": timed_out,
    }


def classify_from_error(student_error: dict | None, exec_result: dict | None = None) -> str | None:
    """Deterministically classify the error type from the *real* error signal.

    Looks at the trimmed stderr + per-test ERROR messages (the runtime
    exceptions) and maps known symbols to our internal taxonomy. Returns ``None``
    when nothing matches (caller may then fall back to the LLM / ``"logic"``).
    """
    exec_result = exec_result or {}
    if (student_error or {}).get("timed_out") or exec_result.get("timed_out"):
        return "timeout"

    haystack_parts = [(student_error or {}).get("stderr", "") or ""]
    for e in (student_error or {}).get("errors", []) or []:
        haystack_parts.append(e.get("msg", ""))
    haystack = "\n".join(haystack_parts).lower()

    for needle, etype in _EXCEPTION_TO_TYPE:
        if needle in haystack:
            return etype

    # A runtime exception we didn't specifically map is still a runtime error.
    if (student_error or {}).get("errors"):
        return "runtime"
    return None


# ---------------------------------------------------------------------------
# Non-code / garbage-input guard (Problem 1, Group B)
# ---------------------------------------------------------------------------

# Tokens that strongly indicate the submission is actually code (any language).
_CODE_TOKEN_RE = re.compile(
    r"(def\s+\w+|function\s+\w+|=>|return\b|class\s+\w+|import\b|"
    r"for\s*\(|while\s*\(|if\s*\(|for\s+\w+\s+in\b|=\s*[^=]|\{|\}|\(\s*\)|;\s*$)",
    re.MULTILINE,
)


def detect_input_issue(code: str | None, language: str) -> dict[str, Any] | None:
    """Cheap, deterministic "is this even code?" / syntax check.

    Returns a structured diagnosis dict when the submission is clearly not valid
    code, else ``None`` (let the normal run-against-tests path handle it).

    Diagnosis dict::

        {
            "kind": "empty" | "not_code" | "syntax",
            "message": str,            # student-facing, points at the problem
            "lineno": int | None,      # for syntax errors (Python compile)
            "offset": int | None,
            "text": str | None,        # offending source line
        }

    Never raises.
    """
    raw = code or ""
    if not raw.strip():
        return {
            "kind": "empty",
            "message": "You didn't submit any code — the editor was empty.",
            "lineno": None,
            "offset": None,
            "text": None,
        }

    lang = (language or "").lower()

    # Python: use compile() to get a precise SyntaxError location.
    if lang in ("python", "py"):
        try:
            compile(raw, "<submission>", "exec")
        except SyntaxError as exc:
            text = (exc.text or "").rstrip("\n")
            loc = ""
            if exc.lineno:
                loc = f" (line {exc.lineno}"
                if exc.offset:
                    loc += f", column {exc.offset}"
                loc += ")"
            pointer = ""
            if text:
                pointer = f"\nThe problem is around:\n    {text.strip()}"
            return {
                "kind": "syntax",
                "message": (
                    f"What you submitted is not valid Python — it doesn't even "
                    f"parse{loc}: {exc.msg}.{pointer}"
                ),
                "lineno": exc.lineno,
                "offset": exc.offset,
                "text": text or None,
            }
        except Exception:  # noqa: BLE001 — any other compile failure → treat as parse issue
            return {
                "kind": "syntax",
                "message": "What you submitted could not be parsed as Python code.",
                "lineno": None,
                "offset": None,
                "text": None,
            }
        # Compiles fine → it's real Python; let the test harness judge it.
        return None

    # Other languages (JS, …): no cheap compiler here. Fall back to the prose
    # heuristic only — actual syntax errors will surface via stderr at runtime.
    if not _looks_like_code(raw):
        return {
            "kind": "not_code",
            "message": (
                f"What you sent doesn't look like {language} code — it reads like "
                "plain text. Please submit a code snippet for the task."
            ),
            "lineno": None,
            "offset": None,
            "text": None,
        }
    return None


def _looks_like_code(text: str) -> bool:
    """Heuristic: does this text contain code-like tokens (vs. prose)?"""
    if _CODE_TOKEN_RE.search(text):
        return True
    # Prose tends to be mostly alphabetic words separated by spaces with few
    # of the symbols common in code.
    symbol_count = sum(text.count(c) for c in "(){}[];=<>+*/")
    return symbol_count >= 2
