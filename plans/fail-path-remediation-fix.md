# Fail-Path Remediation Fix — Diagnostic & Technical Plan

**Scope:** Diagnosis only + step-by-step fix plan. No code changes here (Architect mode).
**Subsystem:** the failure path of a Run & Check submission:
`code_validator → error_classifier → web_search_node → remediation_planner → task_selector → respond`
(wired in [`backend/app/graph/builder.py`](../backend/app/graph/builder.py:138)).

**Four reported problems:**
1. On a wrong answer (incl. non-code / garbage input) the tutor must analyze **the student's actually-submitted code/text** — point at the wrong characters or say it isn't code at all — with example(s) of a correct solution and links explaining the type/class/object where the mistake was made.
2. Currently the tutor returns a **generic, hallucinated** error analysis (theory about syntax) instead of analyzing the real submitted input + the real sandbox error.
3. The blocks are in the **wrong order**. Required order in **one** message: (a) simplified error trace → (b) `Explanation` block with embedded links → (c) **then** the new (similar) task.
4. Prepared/generated tasks are varied in wording but **same in essence** (all "write a function that returns ..."). Need real variety of exercise *types*.

---

## 0. How the failure path actually works today (ground truth)

### 0.1 The sandbox harness hides the real error in `stdout`, not `stderr` — this is the master root cause

The Python harness in [`build_python_program()`](../backend/app/execution/base.py:54) wraps **every** test call in a `try/except` and prints the diagnostics to **stdout**:

```python
for __c in __CASES:
    try:
        __res = entry_point(*__c["args"])
        if __res == __c["expected"]:
            __passed += 1
        else:
            print("FAIL: args=%s expected=%s got=%s" % (...))   # -> STDOUT
    except Exception as __e:
        print("ERROR: args=%s -> %s" % (__c["args"], __e))      # -> STDOUT
print("__TESTS__ %d %d" % (__passed, __total))
```

The JS harness ([`build_js_program()`](../backend/app/execution/base.py:78)) does the same with `console.log` → stdout.

Consequences:
- A **runtime exception** inside the function (TypeError, IndexError, ZeroDivisionError, …) is caught per-test and its message goes to **stdout** as `ERROR: args=... -> <message>`. `stderr` stays **empty**.
- A wrong-but-running answer produces `FAIL: args=... expected=... got=...` lines on **stdout**. `stderr` empty.
- Only a **top-level** failure (e.g. a `SyntaxError` / `IndentationError` that prevents the module from even importing, or `entry_point` not defined → `NameError` at the harness line) produces a real traceback on **stderr**.
- For **non-code / garbage input** (e.g. the student pastes prose): in Python the file fails to parse → `SyntaxError` traceback on `stderr`; the per-test loop never runs, so `passed=0/total` but the actual offending text is in the traceback that nobody forwards.

`code_validator` packs both streams into `execution_result` ([`code_validator()`](../backend/app/graph/nodes/code_validator.py:41)):
```python
exec_dict = {"success", "stdout", "stderr", "passed_tests", "total_tests", "duration_ms", "timed_out"}
```
So `stdout` (where the real per-test ERROR/FAIL diagnostics live) **is available in state** but is **never used** downstream.

### 0.2 What each downstream node actually consumes

| Node | Reads from state | Reads `submitted_code`? | Reads real error? |
|------|------------------|--------------------------|-------------------|
| [`error_classifier()`](../backend/app/graph/nodes/error_classifier.py:43) | `execution_result`, `submitted_code` | yes (only when LLM branch fires) | only `stderr` (empty for caught runtime/logic errors) |
| [`web_search_node()`](../backend/app/graph/nodes/web_search.py:99) | `language`, `current_skill`, `last_error_type`, `topic` | **no** | **no** — builds a generic query + summarizes web snippets |
| [`remediation_planner()`](../backend/app/graph/nodes/remediation.py:19) | `execution_result`, `remediation_links`, `remediation_excerpt`, `last_error_type` | **no** | only `passed/total` counts + `timed_out` |
| [`task_selector()`](../backend/app/graph/nodes/task_selector.py:77) | `agent_response`, `last_passed`, `offer_next_task`, … | n/a | n/a |

The student's `Explanation` text comes from [`_summarise()`](../backend/app/graph/nodes/web_search.py:52), which is grounded **only in web search snippets** for a generic query like `"python loops off by one error explanation tutorial"`. It literally never sees the student's code or the real error → this is exactly the hallucinated "you likely forgot a colon after `except`…" output reported in Problem 2.

---

## 1. Problem 1 — analysis is not about the submitted code / non-code detection

### Root cause
- The submitted code (`state["submitted_code"]`) and the real per-test error (in `execution_result["stdout"]` as `ERROR:`/`FAIL:` lines, or `stderr` for top-level syntax errors) are **never fed into the explanation generator**. The explanation is produced by [`web_search_node._summarise()`](../backend/app/graph/nodes/web_search.py:52) from generic web snippets only.
- There is **no "is this even code?" detection**. Non-code input is just treated as a normal failed attempt; the harness emits a `SyntaxError` to `stderr` that nobody surfaces or interprets for the student.
- No "example of a correct solution" is ever shown. The task carries a `reference_solution` ([`Task`](../backend/app/tasks/repository.py:16)) that is verified solvable, but the failure path never references it.
- Links are not tied to the *type/class/object* of the mistake — `web_search._build_query()` ([`_build_query()`](../backend/app/graph/nodes/web_search.py:38)) themes the query by `language + concept + error_type + topic`, not by the actual error symbol (e.g. `TypeError`, `IndexError`, the offending token).

### Fix direction
Introduce a dedicated **submission-analysis** step that is grounded in the student's actual input:

1. **Add a non-code / empty-input guard** (cheap, deterministic, runs before/insideclassification):
   - empty/whitespace submission → "you didn't submit any code".
   - For Python: try `compile(code, "<submission>", "exec")`; on `SyntaxError` capture `e.msg`, `e.lineno`, `e.offset`, `e.text` → this localizes the bad characters precisely. (For JS, detect from the `stderr` traceback / `SyntaxError` line.)
   - Heuristic "looks like prose, not code" check (no `def`/`function`/`=>`/`return`/assignment tokens, mostly natural-language words) → message "what you sent doesn't look like {language} code".
2. **Forward the real error signal**: extract a *student-error* string from `execution_result` (see Problem 2 fix for the extraction helper), combining `stderr` (top-level traceback) + the `ERROR:`/`FAIL:` lines from `stdout`.
3. **Feed code + real error into the LLM** that writes the `Explanation` (replace the snippet-only `_summarise`). The prompt must include: the submitted code verbatim, the extracted real error/trace, the failing test args/expected/got, and the task's `entry_point`.
4. **Show a correct example**: include the task's `reference_solution` (or a fresh LLM-written minimal correct snippet) in the response, clearly labeled as "Example of a correct solution".
5. **Targeted links**: extend the search query to include the concrete error symbol (e.g. `TypeError`, `list index out of range`) so links explain the actual type/class/object involved.

---

## 2. Problem 2 — generic hallucinated trace instead of analysis of the real input

### Root cause (precise)
- [`error_classifier._rule_based()`](../backend/app/graph/nodes/error_classifier.py:27) inspects **only** `exec_result["stderr"]`. For the common case (caught runtime error or wrong result) `stderr` is empty (see §0.1), so it returns `None` and falls to the LLM branch — or, when even the LLM is unavailable, defaults to `"logic"`.
- The LLM classification branch ([`error_classifier()`](../backend/app/graph/nodes/error_classifier.py:49)) does pass `code` + `stderr` + pass counts, but again `stderr` is empty, so the LLM classifies from `code` + counts only and produces a vague label.
- The student-facing **explanation** is **not** produced by `error_classifier` at all. It comes from [`web_search_node._summarise()`](../backend/app/graph/nodes/web_search.py:52), whose system prompt says *"explain the '{error_type}' mistake the student likely made … Ground your explanation ONLY in the provided search snippets."* — i.e. it is **explicitly told to ignore the student's code** and speak generically about the error_type. That is the direct source of the "student likely forgot a colon after `except`…" output.
- The `error_classifier.explanation` field returned by the LLM is **discarded** (only `error_type` is kept, [line 66](../backend/app/graph/nodes/error_classifier.py:66)).

### Fix direction
1. **Add a stderr+stdout extraction helper** (e.g. `extract_student_error(exec_result) -> str`) that:
   - returns `stderr` when non-empty (top-level traceback / syntax error),
   - else scrapes the `ERROR:` and `FAIL:` lines out of `stdout` (these are the per-test diagnostics: actual exception messages and expected-vs-got), capped to the first N lines.
   This gives the *real* student error for both runtime and logic failures.
2. **Use that signal in `_rule_based`**: classify on `stderr + extracted-stdout` instead of `stderr` only, so logic/type errors are no longer mislabeled `"logic"` by default.
3. **Replace `_summarise` with code-grounded analysis** in `web_search_node` (or move explanation generation into a small new helper / into `remediation_planner`). The new prompt MUST receive and be instructed to analyze:
   - the submitted code verbatim (`state["submitted_code"]`),
   - the extracted real error string,
   - the failing test case(s) (args / expected / got from the `FAIL:` lines),
   - the task prompt + `entry_point`.
   Web snippets become *supporting context for links*, not the sole grounding for the explanation.
4. **Keep search fail-open**: if the LLM is down, fall back to a deterministic explanation built from the extracted error string itself (e.g. echo the real exception + the first failing case), which is still grounded in the student's input — never a generic template.
5. **Thread `submitted_code` through** the failure path. It is already in state (`TutorState.submitted_code`, [`state.py`](../backend/app/graph/state.py:24)); `web_search_node`/`remediation_planner` simply need to read it.

---

## 3. Problem 3 — wrong order of blocks (trace / Explanation / new task)

### Root cause (precise)
- [`remediation_planner()`](../backend/app/graph/nodes/remediation.py:55) builds `agent_response` in this internal order: (1) "❌ does not solve … passed X/Y", (2) "Diagnosed issue", (3) optional timeout note, (4) **Explanation**, (5) **links**, (6) "try again / ask for a similar task". So *within* remediation the order is `trace → Explanation → links` — close to required, but links currently sit after Explanation and there is no clearly separated "simplified trace" block.
- The **fatal ordering bug** is in `task_selector`. The new/similar task is appended to the remediation message **only on the success path**:
  - [`task_selector()`](../backend/app/graph/nodes/task_selector.py:92): `success_prefix = state.get("agent_response", "") if last_passed else ""`.
  - On a **failure** `last_passed == False` (set in [`code_validator()`](../backend/app/graph/nodes/code_validator.py:75)), so `success_prefix == ""`.
  - Therefore the `prompt` (the new task) **overwrites** `agent_response` entirely ([lines 226–231](../backend/app/graph/nodes/task_selector.py:226)). The remediation explanation produced by `remediation_planner` is **thrown away**; the student sees only the new task.
- Net observed effect: depending on timing the student sees the new task block but loses the Explanation, or the blocks read out of order. The required single-message order (trace → Explanation+links → new task) is never assembled because the two builders (`remediation_planner` and `task_selector`) clobber rather than compose on the failure path.

### Where the final message is assembled
- Failure path: `remediation_planner` sets `agent_response` (trace + explanation + links) → `task_selector` then **replaces** it with the task prompt. The `respond` node ([`misc.respond`](../backend/app/graph/nodes/misc.py:1)) just emits whatever `agent_response` holds.

### Fix direction
Make `task_selector` **compose** on the failure path the same way it does on success:
1. Add a **failure prefix** symmetric to `success_prefix`. When `last_passed is False` (i.e. we came through remediation), capture the remediation message as `remediation_prefix = state.get("agent_response", "")`.
2. When `remediation_prefix` is present, render the new task **after** it with a clear "similar task" heading:
   `f"{remediation_prefix}\n\n🔁 **Try a similar task:**\n\n{prompt}"`.
3. Restructure the `remediation_planner` message into the exact required sub-order so the final single message reads:
   - (a) **Simplified trace** block — the de-jargoned real error (built from the extracted student error, not counts only),
   - (b) **Explanation** block with embedded links (links inline within / right under Explanation as the task requires "вложенные ссылки"),
   - (c) (then, appended by `task_selector`) the new similar task.
4. Ensure the "When you're ready, try again or ask me for a similar task." trailer is removed or moved, since the similar task is now appended directly (avoids the contradictory "ask me for a similar task" while one is already shown).
5. Confirm `remediation_planner` already routes to `task_selector` (`next_action="select_task"`, [line 106](../backend/app/graph/nodes/remediation.py:106)) and `task_selector` returns `next_action="respond"` — no graph rewiring needed, only message composition.

---

## 4. Problem 4 — tasks varied in wording but identical in essence

### Root cause
- Every early-skill curated task is the same shape: "define a function that returns X". See [`curated.py`](../backend/app/seed/content/curated.py:206) (`py_variables_swap`, `py_io_greet`, `py_functions_square`, …) — all `entry_point` + `return`.
- The `Task` schema ([`repository.py`](../backend/app/tasks/repository.py:16)) and the execution harness ([`base.py`](../backend/app/execution/base.py:54)) **only** support the "call `entry_point(*args)` and compare return value" model. There is no field describing the *kind of cognitive exercise*; `kind` is just `practice|similar|real_case` (difficulty/role, not exercise type).
- The generator ([`generator.py`](../backend/app/tasks/generator.py:39)) hard-codes the same schema ("define {entry_point}", visible/hidden tests on the return value), so even generated tasks are structurally identical regardless of wording. Its system prompt forces "the function must be PURE … reference_solution defining {entry_point}".
- `task_selector` selects by `skill_id`/`kind`/`difficulty` only ([`task_selector()`](../backend/app/graph/nodes/task_selector.py:112)); it has no notion of "serve a different *exercise type* than last time".

### Proposed exercise-type taxonomy (`exercise_type`)
Introduce a new field `exercise_type` on `Task` (and on the generator schema):

| `exercise_type` | What the student does | How it's checked (sandbox-compatible) |
|-----------------|------------------------|----------------------------------------|
| `implement_return` | Write a function returning a value (today's only type) | call `entry_point`, compare return (existing harness) |
| `predict_output` | Given code, predict the printed/returned result | compare student's typed answer to expected (no sandbox, or sandbox the given code to derive expected) |
| `trace_value` | Trace a variable's value after a loop/condition runs | same as predict_output |
| `find_the_bug` | Given a buggy function, identify/fix the bug | run student's fixed version against tests (existing harness) |
| `fill_in_the_blank` | Complete a partial function (blanks marked `___`) | substitute student's snippet, run tests |
| `refactor` | Rewrite working-but-ugly code keeping behavior | run against the SAME tests as the original |
| `conditions_branching` | Implement branching logic (if/elif/else) | tests over multiple branches |
| `loops_accumulate` | Implement loop/accumulator logic | tests over collections |
| `io_transform` | Parse/transform input → output | tests with structured I/O |

`predict_output` / `trace_value` need a small answer-checking path (compare a typed answer, not a function). `find_the_bug` / `fill_in_the_blank` / `refactor` / `implement_return` reuse the existing run-against-tests harness with minor wrapping.

### Fix direction
1. **Schema:** add `exercise_type: str` to [`Task`](../backend/app/tasks/repository.py:16), `_make_task()` ([line 37](../backend/app/tasks/repository.py:37)) with a default of `"implement_return"` for backward compat; add the field to curated task dicts.
2. **Curated content:** diversify the early skills (`py_variables`, `js_variables`, `py_io`, etc.) so each skill carries ≥3 *different* `exercise_type`s (e.g. one `implement_return`, one `predict_output`, one `find_the_bug`). Add the supporting fields these types need (e.g. `given_code` for predict/trace/bug, `template` with `___` for fill-in-the-blank, `expected_answer` for predict/trace).
3. **Selector variety:** in [`task_selector()`](../backend/app/graph/nodes/task_selector.py:112), bias selection away from the `exercise_type` last served to the student (track last type in progress/serve history or in state), so consecutive exercises differ in essence, not just wording.
4. **Generator:** parametrize [`generate_task()`](../backend/app/tasks/generator.py:186) with a target `exercise_type` and branch [`_SYSTEM_PROMPT`](../backend/app/tasks/generator.py:39) / [`_build_user_prompt()`](../backend/app/tasks/generator.py:61) per type. Pass the desired type down from `_maybe_generate()` ([`task_selector._maybe_generate()`](../backend/app/graph/nodes/task_selector.py:28)) (rotate types). Extend [`_parse_candidate()`](../backend/app/tasks/generator.py:147) and verification to validate the type-specific fields.
5. **Harness/answer-check:** add a non-function answer-checking path for `predict_output`/`trace_value` (compare typed answer to `expected_answer`); for code-producing types keep using [`build_program()`](../backend/app/execution/base.py:103). For `predict_output`, derive `expected_answer` by sandbox-running `given_code` at authoring/verify time to keep the anti-hallucination guarantee.
6. **Prompt rendering:** `task_selector` renders the prompt assuming "Define a function named `{entry_point}`" ([lines 199–203](../backend/app/graph/nodes/task_selector.py:199)). Make this conditional on `exercise_type` (e.g. predict/trace shouldn't ask to "submit code defining a function").

---

## 5. Step-by-step remediation plan (for the implementation phase)

> Ordered; each step lists file + function + nature of change. No effort estimates.

### Group A — Surface the real student error (fixes Problems 1 & 2 foundation)
- **A1.** [`backend/app/execution/base.py`](../backend/app/execution/base.py:54): add a helper to parse harness stdout into structured failures (`ERROR:` lines = runtime exceptions; `FAIL:` lines = wrong result with args/expected/got). Optionally tag `ERROR` lines so a runtime-error type can be inferred. (Harness output format unchanged → no executor redeploy risk.)
- **A2.** New helper `extract_student_error(exec_result) -> dict|str` (e.g. in `error_classifier.py` or a small `app/graph/nodes/_error_utils.py`): combine `stderr` (top-level) + parsed `stdout` ERROR/FAIL lines into a concise "real error" summary + a list of failing cases.
- **A3.** [`error_classifier.py`](../backend/app/graph/nodes/error_classifier.py:27): feed the A2 output into `_rule_based()` and the LLM branch; **keep** the LLM `explanation` (currently discarded at [line 66](../backend/app/graph/nodes/error_classifier.py:66)) by returning it in state for downstream use.

### Group B — Non-code / garbage-input guard (Problem 1)
- **B1.** [`code_validator.py`](../backend/app/graph/nodes/code_validator.py:19) (or a new pre-check inside it): before/after running, detect empty submission and `compile()`-level `SyntaxError` for Python (capture `lineno/offset/text`); add a prose-vs-code heuristic. Store a structured "input issue" in state (e.g. `input_diagnosis`).
- **B2.** Route such cases so the explanation explicitly says "this isn't {language} code / you submitted no code" and points at the offending line/characters — still proceeds through remediation so links + correct example + similar task are produced.

### Group C — Code-grounded explanation + correct example + targeted links (Problems 1 & 2)
- **C1.** [`web_search.py`](../backend/app/graph/nodes/web_search.py:52): replace `_summarise()` (snippet-only) with a code-grounded explanation generator that receives `submitted_code`, the A2 real-error, failing cases, task prompt + `entry_point`. Web snippets become supporting context, not the sole grounding.
- **C2.** [`web_search.py` `_build_query()`](../backend/app/graph/nodes/web_search.py:38): include the concrete error symbol/type (e.g. `TypeError`, `index out of range`) so links explain the actual type/class/object.
- **C3.** [`remediation.py`](../backend/app/graph/nodes/remediation.py:19): read `submitted_code` + task `reference_solution` (via `get_task(current_task_id)`); include a clearly-labeled **"Example of a correct solution"** snippet in the response. Add deterministic LLM-down fallback that echoes the real error + first failing case (still grounded in student input).

### Group D — Fix message ordering (Problem 3)
- **D1.** [`remediation.py`](../backend/app/graph/nodes/remediation.py:55): restructure `parts` into the exact sub-order: (a) **Simplified trace** (de-jargoned real error), (b) **Explanation** with embedded/inline links. Remove the trailing "ask me for a similar task" line (the task will be appended next).
- **D2.** [`task_selector.py`](../backend/app/graph/nodes/task_selector.py:92): add a `remediation_prefix` symmetric to `success_prefix` (active when `last_passed is False`); compose `f"{remediation_prefix}\n\n🔁 **Try a similar task:**\n\n{prompt}"` instead of overwriting `agent_response`. Mirror the same guard in the no-task fallback ([lines 168–194](../backend/app/graph/nodes/task_selector.py:168)) so remediation text is preserved even when no similar task is available.

### Group E — Exercise-type diversity (Problem 4)
- **E1.** [`repository.py`](../backend/app/tasks/repository.py:16): add `exercise_type` (default `implement_return`) + optional fields (`given_code`, `template`, `expected_answer`) to `Task`/`_make_task()`.
- **E2.** [`curated.py`](../backend/app/seed/content/curated.py:92): diversify early-skill tasks to cover ≥3 distinct `exercise_type`s per skill (per language).
- **E3.** [`base.py`](../backend/app/execution/base.py:103): add an answer-checking path for `predict_output`/`trace_value`; keep `build_program()` for code-producing types.
- **E4.** [`generator.py`](../backend/app/tasks/generator.py:39): parametrize by `exercise_type`; branch system/user prompts; extend `_parse_candidate()`/`_verify()` for type-specific fields (derive `expected_answer` by sandbox-running `given_code`).
- **E5.** [`task_selector.py`](../backend/app/graph/nodes/task_selector.py:112): rotate/bias `exercise_type` so consecutive tasks differ in essence; make the prompt rendering ([lines 199–203](../backend/app/graph/nodes/task_selector.py:199)) conditional on type.
- **E6.** [`state.py`](../backend/app/graph/state.py:9): if needed, add `last_exercise_type` (or persist via serve history) to support E5 rotation.

### Group F — Verification
- **F1.** Manual: submit (i) prose/garbage, (ii) a runtime-error solution, (iii) a wrong-but-running solution; confirm the Explanation references the actual code/error, shows a correct example + targeted links, and the single message reads trace → Explanation+links → similar task.
- **F2.** Update/extend smoke tests in [`backend/tests/test_smoke.py`](../backend/tests/test_smoke.py) for the new error-extraction helper, the message ordering, and exercise-type selection.

---

## 6. Summary of root causes → fixes

| # | Root cause (file · function) | Fix |
|---|------------------------------|-----|
| 1 | Submitted code + real error never fed to explanation; no non-code detection; no correct example; links not error-specific. Explanation comes from [`web_search._summarise()`](../backend/app/graph/nodes/web_search.py:52) (web-snippet-only). Harness sends real per-test errors to **stdout** ([`build_python_program()`](../backend/app/execution/base.py:54)) which nobody reads. | Add input guard + stdout/stderr error extraction; ground the explanation in the submitted code & real error; include task `reference_solution` as a correct example; add the error symbol to the search query. |
| 2 | [`error_classifier._rule_based()`](../backend/app/graph/nodes/error_classifier.py:27) reads only (empty) `stderr`; explanation prompt in [`_summarise()`](../backend/app/graph/nodes/web_search.py:52) is explicitly told to ignore the code and speak generically; LLM `explanation` is discarded. | Extract the real error from stdout+stderr; replace generic prompt with a code-grounded one that analyzes the student's actual input + real error; deterministic, input-grounded fallback when LLM is down. |
| 3 | On failure `last_passed is False`, so [`task_selector()`](../backend/app/graph/nodes/task_selector.py:92) has empty `success_prefix` and **overwrites** the remediation `agent_response` with the new task — Explanation lost / order broken. | Add a `remediation_prefix` and compose trace → Explanation+links → similar task in one message; restructure [`remediation_planner()`](../backend/app/graph/nodes/remediation.py:55) sub-order accordingly. |
| 4 | Single task shape ("define function returning X") baked into [`curated.py`](../backend/app/seed/content/curated.py:206), [`Task`](../backend/app/tasks/repository.py:16) schema, harness ([`base.py`](../backend/app/execution/base.py:54)) and [`generator.py`](../backend/app/tasks/generator.py:39); selector ignores exercise type. | Add `exercise_type` taxonomy + supporting fields; diversify curated content; add answer-checking path; parametrize generator by type; rotate types in the selector. |
