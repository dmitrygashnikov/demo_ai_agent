# Implementation Spec — Sidebar Sections, RAG Link Persistence, Chat & Layout Enhancements

> Scope: the 10 user-requested changes for the Adaptive AI Coding Tutor (LangGraph + RAG + sandbox).
> This document is **investigation + design only**. No application code is implemented here.
> File references use the form [`path`](path:line).

---

## 0. Requirement → section map

| # | Requirement (short) | Primary section(s) |
|---|---------------------|--------------------|
| 1 | No chat auto-scroll; unread badge + scroll-to-bottom arrow | §6.7 |
| 2 | Do not render "Sandbox" messages | §1.3, §6.8 |
| 3 | RAG task/link persistence + availability check + pruning (≥4 links, 50 fails/3 days) | §2.2, §4.2–4.6, §5.2 |
| 4 | Draggable splitter between chat and editor | §6.6 |
| 5 | Collapsible left sidebar | §6.1 |
| 6 | Human-readable sections, 20+/language, user-added, clickable, filter, pinned current, remove editor "Theme" row | §2.1, §3, §5.1, §6.2–6.4 |
| 7 | Section change emits chat msg + produces NEW themed task + cancels prior task | §4.1, §3.3 |
| 8 | "?" pictogram → intro articles/videos for topic+language; language dropdown in sidebar | §3.5, §4.7, §6.5 |
| 9 | Seed new sections + links into RAG | §5 |
| 10 | Update README.md + README_RU.md | §7 |

---

## 1. Findings (current behaviour)

### 1.1 The "3 sidebar sections" and why they are machine-readable

There is **no "sections/themes" concept in the codebase today**. What the user calls the
"3 sections that are not human-readable" is the **Progress list in the left sidebar**,
rendered in [`frontend/src/App.jsx`](frontend/src/App.jsx:538-551):

```jsx
{skills.map((s) => (
  <div className="skill" key={s.skill_id}>
    <span>{s.skill_id}</span>           // <-- raw machine key, e.g. "py_variables"
    <span className={"state " + s.state}>{s.state}</span>
    ...
```

The list is populated from `GET /api/progress/me` → `skills` (see [`_progress_for`](backend/app/api/routes.py:147-162)),
which returns rows from `skill_progress`. The values shown are the **raw `skill_id`** strings
(`py_variables`, `py_io`, `py_conditions`, …) — never the human `Skill.name`.

For a brand-new user, exactly **3 rows** are seeded by
[`ensure_user_profile`](backend/app/db/progress_repo.py:48-88) via `skills_for_language(lang)[:3]`,
i.e. the first three skills of the language:

- Python: `py_variables`, `py_io`, `py_conditions`
- JavaScript: `js_variables`, `js_io`, `js_conditions`

These three rows render as `py_variables` / `py_io` / `py_conditions` — the **"3 non-human-readable sections."**
The human-readable names already exist on the `Skill` model (`Skill.name`, e.g. `"Variables & types (python)"`)
in [`skill_graph.py`](backend/app/db/skill_graph.py:24-40) but are **not** exposed by `/api/progress/me`.

> Note: `THEORY` in [`curated.py`](backend/app/seed/content/curated.py:16-50) also happens to contain
> exactly 3 docs, but those are RAG documents, not sidebar items. The sidebar = skill_progress rows.

### 1.2 How `topic` flows end-to-end

`topic` (free-form theme, orthogonal to language/skill) is already fully threaded:

1. **Storage**: `users.topic` column on [`User`](backend/app/db/models.py:53), idempotent migration
   `ALTER TABLE users ADD COLUMN IF NOT EXISTS topic VARCHAR` in [`main.py`](backend/app/main.py:50-52).
2. **Repo**: [`get_user_topic`](backend/app/db/progress_repo.py:167-176) / [`set_user_topic`](backend/app/db/progress_repo.py:179-190).
3. **REST**: `GET /api/topic`, `PUT /api/topic`, `GET /api/topics` in [`routes.py`](backend/app/api/routes.py:197-240).
4. **WS**: `{type:"topic"}` convenience + per-turn `topic` field in [`ws.py`](backend/app/api/ws.py:77-90).
5. **Runner**: [`run_turn`](backend/app/graph/runner.py:39-115) resolves `topic` (explicit per-turn → else `User.topic`)
   and writes it into `state_in["topic"]`.
6. **State**: `topic` channel in [`TutorState`](backend/app/graph/state.py:33).
7. **Consumers**: [`task_selector`](backend/app/graph/nodes/task_selector.py:185) (themed generation via
   `_maybe_generate`) and [`web_search_node`](backend/app/graph/nodes/web_search.py:167) (query theming).
8. **Frontend**: `applyTopic` in [`App.jsx`](frontend/src/App.jsx:403-422) PUTs the topic and **emits the chat
   message** `🎨 Theme set to "<t>". New tasks will be themed accordingly.` — **but it does NOT trigger a new
   turn**, so no new task is generated and the previous task is not cancelled (this is requirement #7's bug).

**Key gap for #7**: setting the topic only persists it + prints a chat line. The next themed task only appears
on the *next* user action (chat/submit). There is no concept of "cancel the previously-served task."

### 1.3 How the chat renders messages + how "Sandbox" messages are tagged

Messages are local React state `messages: [{role, content, meta}]`, rendered in
[`App.jsx`](frontend/src/App.jsx:581-590). Auto-scroll is unconditional:

```jsx
useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);  // line 360-362
```

"Sandbox" messages are **client-side only**, pushed by `onRunCode` in
[`App.jsx`](frontend/src/App.jsx:499-506):

```jsx
pushMsg("assistant", `🧪 Sandbox: ${er.passed_tests}/${er.total_tests} tests passed` + ...)
```

They are **not tagged** with any field — they are assistant messages whose `content` starts with `🧪 Sandbox:`.
To filter them (req #2) we add a structured marker (a `kind: "sandbox"` on the pushed message) rather than
matching the emoji string. The simplest robust approach: stop pushing them, or push them with
`{role:"assistant", kind:"sandbox", ...}` and filter on `kind`. (See §6.8.)

### 1.4 The editor "Theme" row

The "Theme" row is the `topic-toolbar` block in [`App.jsx`](frontend/src/App.jsx:623-666) (label "Theme",
suggestion `<select>`, free-text input, "Set" button, active chip). CSS in
[`styles.css`](frontend/src/styles.css:107-128). Requirement #6 says **remove this row from the editor toolbar**
(topic selection moves into the sidebar via section selection).

### 1.5 How RAG stores / retrieves documents

- **Vector store**: Qdrant, single collection `tutor_content` ([`vectorstore.py`](backend/app/rag/vectorstore.py:17-82)).
  `upsert(docs=[{text, metadata}])` embeds text and stores payload; `search(query, filters, top_k)` does dense
  search with exact-match metadata filters (`language`, `concept`, `doc_type`, `error_type`, …).
- **Ingestion**: [`ingest_all`](backend/app/rag/ingestion.py:17-76) indexes `THEORY`, `VIDEOS`, and all curated
  tasks at startup. **Idempotency caveat**: it **skips entirely if `store.count() > 0`** (line 22-24) — so adding
  new seed content (req #9) requires either `force=True` or a count-aware/per-doc upsert (see §5.3).
- **Retrieval**: [`retrieve`](backend/app/rag/retriever.py:32-60) and
  [`retrieve_video_for_error`](backend/app/rag/retriever.py:63-84). Videos carry `url` + `timecode` in payload.
- **There is no SQL/relational store for links today.** Remediation links are fetched live per-turn via
  [`web_search`](backend/app/search/__init__.py:53-92) (`SearchResult{title,url,snippet}`) and never persisted.
  `VIDEOS` (curated) are the only persisted link-like docs (in Qdrant).

### 1.6 Migration & seed patterns (to mirror)

- Tables created via `Base.metadata.create_all` in [`init_db`](backend/app/db/session.py:35-39).
- In-place column adds: idempotent `ALTER TABLE … ADD COLUMN IF NOT EXISTS` in
  [`_startup_seed`](backend/app/main.py:32-89) inside `with engine.begin() as conn:`.
- Idempotent row seeding: `seed_skills` ([`skills.py`](backend/app/seed/skills.py:13-38)) get-or-update per row;
  `seed_default_user` ([`default_user.py`](backend/app/seed/default_user.py:26-49)).
- Seed ordering in [`_startup_seed`](backend/app/main.py:19-127): init_db → migrations → runtime settings →
  skills → default user → RAG ingestion.

---

## 2. Data model

Two new tables, both added to [`backend/app/db/models.py`](backend/app/db/models.py:1) and created by
`create_all`, **plus** idempotent `ALTER TABLE … IF NOT EXISTS` startup blocks in
[`main.py`](backend/app/main.py:32-89) (so existing volumes upgrade; `create_all` only adds tables/columns
on a fresh volume).

### 2.1 `sections` table (themes/sections)

```python
class Section(Base):
    """A learning section/theme shown in the sidebar (req. 6).

    Seeded sections are human-readable per language; users may also add their own.
    A section optionally maps to a skill concept so selecting it can set the topic
    and (when relevant) steer the skill axis. ``key`` is a stable slug used by the
    API/seed; ``title`` is what the sidebar renders.
    """
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("language", "key", name="uq_section_lang_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    language: Mapped[str] = mapped_column(String, index=True, nullable=False)  # python | javascript
    key: Mapped[str] = mapped_column(String, nullable=False)                   # slug, e.g. "data_analysis_pandas"
    title: Mapped[str] = mapped_column(String, nullable=False)                 # human-readable, e.g. "Data analysis with pandas"
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Optional concept this section maps to (for skill steering); "" = pure topic theme.
    concept: Mapped[str] = mapped_column(String, default="", nullable=False)
    # Free-form topic string applied when this section is selected (defaults to title).
    topic: Mapped[str | None] = mapped_column(String, nullable=True)
    is_user_created: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    # NULL for seeded/global sections; set to a user id for user-created sections.
    owner_user_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

**Visibility rule**: a user sees sections where `owner_user_id IS NULL` (global/seeded) **OR**
`owner_user_id == current_user.id` (their own), filtered by `language`.

**Per-user "current section"**: add one column to `users` (mirrors `topic`):

```python
# on User
current_section_id: Mapped[str | None] = mapped_column(String, nullable=True)
```

> Why a column on `users` rather than a join table: the app tracks exactly one active section per user, exactly
> like `topic`. Keeps the change minimal and matches the existing single-value `topic` pattern.

### 2.2 `remediation_links` table (pragmatic link store)

```python
class RemediationLink(Base):
    """Persisted remediation/intro link reusable across students (req. 3).

    Pragmatic counter-based health tracking (NOT full event logging): a rolling
    3-day window + a fail counter drives pruning. Saved by web_search/remediation
    and the "?" intro flow; verified for availability at serve-time.
    """
    __tablename__ = "remediation_links"
    __table_args__ = (
        UniqueConstraint("url", "error_type", "language", name="uq_link_url_err_lang"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    url: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, default="", nullable=False)
    snippet: Mapped[str] = mapped_column(Text, default="", nullable=False)
    language: Mapped[str] = mapped_column(String, default="", nullable=False, index=True)
    # Reuse key: the concrete error/topic this link explains. For remediation use
    # an error symbol/type (e.g. "TypeError", "off_by_one"); for intro/"?" use the
    # section concept/key (e.g. "loops", "data_analysis_pandas").
    error_type: Mapped[str] = mapped_column(String, default="", nullable=False, index=True)
    concept: Mapped[str] = mapped_column(String, default="", nullable=False, index=True)
    # "remediation" | "intro" — lets the "?" flow and the failure flow share a table.
    kind: Mapped[str] = mapped_column(String, default="remediation", server_default="remediation", nullable=False)

    # ---- Pragmatic health counters (the "50 fails in 3 days" rule) ----
    fail_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    fail_window_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_ok: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

### 2.3 Pruning algorithm ("50 fails in 3 days", simple counters)

Implemented in a new `backend/app/rag/link_store.py` helper. Constants:

```python
FAIL_WINDOW = timedelta(days=3)
FAIL_THRESHOLD = 50
```

On a **failed availability check** for a link row `L`:

```text
now = utcnow()
if L.fail_window_start is None or (now - L.fail_window_start) > FAIL_WINDOW:
    # window expired or never started → reset the rolling window
    L.fail_window_start = now
    L.fail_count = 1
else:
    L.fail_count += 1
L.last_checked = now
L.last_ok = False
if L.fail_count > FAIL_THRESHOLD:        # >50 fails within the active 3-day window
    delete L                              # prune from the store
```

On a **successful** availability check: `L.last_checked = now; L.last_ok = True`
(do **not** reset `fail_count` mid-window — the window is purely time-based, matching the "within the last 3
days" wording; it self-resets when 3 days elapse without crossing the threshold). This is the simplest
counter scheme that satisfies "more than 50 fails within the last 3 days → delete."

### 2.4 Startup migrations (mirror [`main.py`](backend/app/main.py:32-89))

Add inside the existing `with engine.begin() as conn:` block:

```python
conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS current_section_id VARCHAR"))
# sections / remediation_links: created by create_all on a fresh volume. For
# existing volumes, create_all DOES add new *tables* (it only skips existing
# ones), so no explicit CREATE TABLE is required — but adding new *columns* to
# them later would need ADD COLUMN IF NOT EXISTS, same as the topic pattern.
```

> `Base.metadata.create_all` creates missing tables on existing volumes, so `sections` and
> `remediation_links` appear automatically. Only **new columns on pre-existing tables** (here: `users`)
> need an explicit `ALTER TABLE … ADD COLUMN IF NOT EXISTS`.

---

## 3. API design

All section endpoints are **REST** under the existing `/api` router
([`routes.py`](backend/app/api/routes.py:26)), authenticated with
`Depends(get_current_user)` ([`auth/deps.py`](backend/app/auth/deps.py:1)) unless noted public.
New Pydantic models live alongside the existing ones in [`routes.py`](backend/app/api/routes.py:29-101).
Section CRUD + intro lives in a new module `backend/app/api/sections.py` (router included in
[`main.py`](backend/app/main.py:152-154)) to keep `routes.py` focused; or appended to `routes.py` — implementer's
choice. WebSocket additions go in [`ws.py`](backend/app/api/ws.py:35).

### 3.1 List sections — `GET /api/sections?language=python`

- **Auth**: required (uses current user to include their own sections).
- **Query**: `language` (required: `python|javascript`).
- **Response**:
```json
{
  "language": "python",
  "current_section_id": "py-loops-uuid",
  "sections": [
    { "id": "py-loops-uuid", "key": "loops", "title": "Loops & iteration",
      "description": "...", "concept": "loops", "topic": "loops",
      "is_user_created": false, "owner_user_id": null, "order_index": 4 }
  ]
}
```
- Returns global (`owner_user_id IS NULL`) + the user's own sections for `language`, ordered by `order_index, title`.

### 3.2 Get languages — `GET /api/languages`

- **Auth**: public (static, like `GET /api/topics`).
- **Response**: `{ "languages": [ {"id":"python","label":"Python"}, {"id":"javascript","label":"JavaScript"} ] }`
- Source: derived from distinct `Section.language` / the MVP set `["python","javascript"]`.

### 3.3 Select current section — `POST /api/sections/select`

This is the **core of requirement #7**: it sets the topic, **runs a fresh themed turn that cancels the previous
task and produces a new one**, and returns both the persisted state and the new task as a normal turn result.

- **Auth**: required. `user_id` from token.
- **Request**:
```json
{ "session_id": "abc123", "section_id": "py-loops-uuid" }
```
- **Behaviour** (server):
  1. Load the `Section` (must be visible to the user); `400` if not found/visible.
  2. Persist `users.current_section_id = section_id` and `users.topic = section.topic or section.title`.
  3. Call `run_turn(user_id, session_id, user_message="", language=section.language, topic=<resolved>,
     section_change=True)` — a new internal flag (see §4.1) that forces `task_selector` to **discard the
     previously-served `current_task_id`** and emit a fresh themed task, while emitting the theme-set chat line.
  4. Return the **turn result** (same shape as `/api/chat`): `{ interrupted, response, state }` where
     `state.current_task_id` is the NEW task and `state.topic` is the new theme.
- **Response** (example):
```json
{
  "interrupted": false,
  "response": "🎨 Theme set to \"Loops & iteration\". New tasks will be themed accordingly.\n\n**Task (python, difficulty 2)** ...",
  "state": { "topic": "loops", "current_task_id": "gen_…", "task_source": "generated", "language": "python", ... }
}
```

> The chat "Theme set to …" line is produced **server-side** in this turn (so it is part of `response` and is
> consistent across REST/WS) rather than only client-side as today.

### 3.4 Create user section — `POST /api/sections`

- **Auth**: required. `owner_user_id` = current user.
- **Request**:
```json
{ "language": "python", "title": "Bioinformatics basics", "description": "DNA string processing", "concept": "" }
```
- **Server**: derive `key = slugify(title)`; enforce `UniqueConstraint(language, key)` scoped per-owner by
  prefixing user keys (`u_<short_uid>_<slug>`) to avoid clashing with global slugs; `is_user_created=True`,
  `topic = title`. `409` on duplicate, `400` on empty/oversized title (reuse the 120-char limit from
  [`_MAX_TOPIC_LEN`](backend/app/api/routes.py:101)).
- **Response**: the created section object (same shape as items in §3.1).

### 3.5 Intro material ("?") — `POST /api/sections/{section_id}/intro`

Backs requirement #8. Returns intro links/videos **and** pushes them as a chat turn so they land in the
conversation for the selected language.

- **Auth**: required.
- **Request**:
```json
{ "session_id": "abc123", "language": "python" }
```
- **Behaviour**:
  1. Resolve the section + concept/key.
  2. Pull persisted intro links from `remediation_links` where `kind='intro'`,
     `concept=section.concept or section.key`, `language=…`; **verify availability** (§4.4); replace dead ones
     via web search; ensure at least a few (target 4 articles + 1–2 videos, fail-open to fewer).
  3. Emit an assistant chat message containing the links (so it appears in chat), and also return them
     structured for the `MessageMeta` links panel.
- **Response**:
```json
{
  "response": "📚 Intro to **Loops & iteration** (python):",
  "links": [ {"title":"…","url":"…","snippet":"…","kind":"article"}, {"title":"…","url":"…","kind":"video"} ]
}
```
- REST (not WS) keeps the "?" click a simple request/response; the frontend appends the returned message to
  the chat (`pushMsg` with `meta.remediation_links`-style payload).

### 3.6 Optional WebSocket parity

Add WS message types mirroring the REST calls so a WS-only client stays in parity (optional for MVP):
- `{type:"select_section", section_id, session_id}` → runs the §3.3 turn, replies `{type:"final", response, state}`.
- `{type:"section_intro", section_id, language}` → replies `{type:"intro", response, links}`.

The REST endpoints are the source of truth; WS handlers in [`ws.py`](backend/app/api/ws.py:65-126) delegate to
the same service functions via `asyncio.to_thread`.

---

## 4. Graph / flow changes

### 4.1 Section select → set topic + new themed task + cancel previous (req #7)

Today `task_selector` already **excludes** `current_task_id` from the pool
([`task_selector.py`](backend/app/graph/nodes/task_selector.py:250,260)). The missing piece is **triggering a
turn at all** when the theme changes, and **forcing a brand-new task** even on an otherwise idle turn.

Design:

- Add an optional `section_change: bool` channel to [`TutorState`](backend/app/graph/state.py:9) and a
  `section_change` parameter to [`run_turn`](backend/app/graph/runner.py:39) (threaded into `state_in`).
- `POST /api/sections/select` (§3.3) calls `run_turn(..., topic=resolved, section_change=True)`.
- Routing: when `section_change` is true and there is no `submitted_code`/goal text, the intent should resolve
  to a **"serve a themed task"** path. Cleanest approach without a new node: add a branch in
  [`intent_router`](backend/app/graph/nodes/router.py:46) — if `state.get("section_change")`, set
  `intent = "goal"`-like routing that goes `skill_path_builder → task_selector` **OR** introduce a tiny new
  intent `"section"` routed straight to `skill_path_builder` (so the current skill is (re)derived for the new
  language) then `task_selector`. Recommended: reuse the goal branch target by routing `section` →
  `skill_path_builder` in [`route_intent`](backend/app/graph/nodes/builder.py:49-55) and
  [`builder.py`](backend/app/graph/builder.py:108-117).
- In [`task_selector`](backend/app/graph/nodes/task_selector.py:180): when `section_change` is set, treat it like
  a deliberate fresh serve:
  - "Cancel previous task" = simply do **not** treat the old task as active; the old `current_task_id` is already
    excluded from the pool (line 250/260) and is overwritten by the new task id (line 371). Add an explicit
    `cancelled_task_id` log + ensure `last_passed`/remediation prefixes are not applied on a section-change turn
    (so the message is purely "Theme set … + new task").
  - Prepend the **theme-set line** to the rendered prompt:
    `🎨 Theme set to "<title>". New tasks will be themed accordingly.\n\n<new task>`.
  - With a topic set, `_maybe_generate` ([`task_selector.py`](backend/app/graph/nodes/task_selector.py:125-177))
    already mints a themed generated task (fail-open to curated).

> Result: selecting a section yields one chat turn: theme-set confirmation **immediately followed by a new
> themed task**, and the previously-served task is no longer the active one.

### 4.2 Saving links to the new store (req #3a)

In [`web_search_node`](backend/app/graph/nodes/web_search.py:161-235), after fetching `links`
(line 199), **persist** each result into `remediation_links` via `link_store.save_links(...)`:
- key fields: `url`, `title`, `snippet`, `language`, `error_type = state.last_error_type`,
  `concept = concept_of(skill_id)`, `kind="remediation"`.
- Upsert on `(url, error_type, language)` (the unique constraint) — get-or-create; do not reset counters on
  re-save. Fail-open (wrap in try/except, never break the turn).

Symmetrically, the §3.5 intro flow saves with `kind="intro"`.

### 4.3 Serve-time reuse of saved links

Augment `web_search_node` (and the intro flow) to **prefer the persisted store** before/in addition to a live
search:
1. Load candidate links from `remediation_links` filtered by `error_type`+`language` (remediation) or
   `concept`+`language` (intro), ordered by `last_ok desc, fail_count asc`.
2. Verify availability (§4.4); drop dead ones (and decrement their health via §2.3).
3. If the verified set has `< 4`, run the existing live `web_search(...)` to top up, **save** the new links
   (§4.2), and include them.

### 4.4 Availability verification (HTTP check)

New `link_store.check_url(url) -> bool` in `backend/app/rag/link_store.py`:
- `HEAD` request (fallback to `GET` with a tiny range) using `httpx`/`requests` with a short timeout
  (e.g. 4s) and redirects allowed; treat `2xx/3xx` as alive, everything else (incl. timeout/conn error) as dead.
- Strictly **fail-open at the feature level**: a network error marks the *link* dead for this serve and bumps
  its fail counter, but never raises to the graph turn.
- Verification is applied **at serve-time** (when assembling the response), not at save-time.

### 4.5 Replace dead links via search (req #3c)

When a saved link fails verification:
- record the failure (§2.3 → may prune at >50/3-days),
- exclude it from this response,
- run a targeted `web_search` to find replacements, `save_links` the new ones, and substitute.

### 4.6 Guarantee ≥4 links per error explanation (req #3 / "≥4 links")

- Set `_MAX_LINKS`/target in [`web_search.py`](backend/app/graph/nodes/web_search.py:39) to **4 minimum**
  (rename to `_MIN_LINKS = 4` and fetch a few extra, e.g. `max_results=6`, to survive dead-link pruning).
- The assembly order in [`remediation.py`](backend/app/graph/nodes/remediation.py:117-129) already lists up to 4
  links (`remediation_links[:4]`) plus a curated video; **raise that cap and combine** persisted + live +
  curated `VIDEOS` until **≥4 verified links** are present.
- Fail-open: if the internet is unreachable AND the store is empty, the seeded intro/remediation links (§5.2)
  guarantee a floor of ≥4 per seeded concept so the requirement holds offline too. The deterministic
  explanation path ([`web_search.py`](backend/app/graph/nodes/web_search.py:68-87)) still runs.

### 4.7 Intro material flow (req #8)

The "?" endpoint (§3.5) reuses §4.3–4.4 with `kind="intro"`, scoped to `concept`/`key`+`language`, targeting
4 articles + 1–2 videos. It does not touch skill progress or `current_task_id` (pure informational turn).

### 4.8 Uniqueness ("never the same task twice") interaction (req #3)

The existing per-user `task_serve_history` + [`filter_unique_tasks`](backend/app/tasks/uniqueness.py:51-70)
already prevents re-serving. The requirement "a given student must never be shown the same task twice" is
stronger than the 500-solve cooldown. Pragmatic change: in
[`filter_unique_tasks`](backend/app/tasks/uniqueness.py:62-65), treat **any prior serve** to that user as
disqualifying (i.e. `last is None` only), with the existing least-recently-served fallback
([`uniqueness.py`](backend/app/tasks/uniqueness.py:68-69)) retained so generation/fallback never dead-ends.
Generated tasks are naturally unique per request, so themed sections keep producing fresh tasks.

---

## 5. Seed plan

### 5.1 Sections (20+ per language, human-readable)

New seed module `backend/app/seed/sections.py` with `seed_sections()` (idempotent get-or-create per
`(language, key)`, mirroring [`seed_skills`](backend/app/seed/skills.py:13-38)), called from
[`_startup_seed`](backend/app/main.py:99-117) after `seed_skills`. Each section has `language`, `key`, `title`,
`description`, optional `concept` (mapped to an existing skill concept when applicable), `topic` (defaults to
title), `order_index`.

The first 15 mirror the existing concepts (so the sidebar replaces today's machine-readable skill list with
readable titles), then ≥5 more domain themes → **≥20 per language**.

**Python sections (20):**
1. Variables & types — `variables`
2. Input / output — `io`
3. Conditions & branching — `conditions`
4. Loops & iteration — `loops`
5. Functions — `functions`
6. Lists & collections — `collections`
7. Dictionaries — `dicts`
8. String processing — `strings`
9. Error handling — `errors`
10. Object-oriented programming — `oop`
11. Comprehensions & functional — `comprehensions`
12. Recursion — `recursion`
13. Modules & imports — `modules`
14. Working with APIs — `api`
15. Mini project — `project`
16. Data analysis with pandas — `data_analysis_pandas`
17. Web scraping — `web_scraping`
18. Automation scripting — `automation`
19. File & CSV processing — `file_csv`
20. Testing with pytest — `testing_pytest`

**JavaScript sections (20):**
1. Variables & types — `variables`
2. Input / output — `io`
3. Conditions & branching — `conditions`
4. Loops & iteration — `loops`
5. Functions — `functions`
6. Arrays & collections — `collections`
7. Objects — `dicts`
8. String processing — `strings`
9. Error handling — `errors`
10. Object-oriented programming — `oop`
11. Array methods & functional — `comprehensions`
12. Recursion — `recursion`
13. Modules & imports — `modules`
14. Working with APIs — `api`
15. Mini project — `project`
16. DOM manipulation basics — `dom`
17. Async & promises — `async`
18. Fetch & HTTP requests — `fetch_http`
19. JSON data handling — `json_data`
20. Node.js scripting — `node_scripting`

> Concepts 1–15 reuse existing skill concepts so section selection can also steer the skill axis; 16–20 are
> domain themes that primarily set `topic` (concept `""` or the nearest existing concept).

### 5.2 Intro + remediation links seed (RAG, req #9)

New `INTRO_LINKS` (and additional `REMEDIATION_LINKS`) structure in
[`curated.py`](backend/app/seed/content/curated.py:1) (or a sibling `curated_links.py`). For **each section
concept/key per language**, seed **≥4 article links + ≥1 video** so requirement #3's "≥4 links per error
explanation" and #8's intro material hold even fully offline. Shape:

```python
INTRO_LINKS = [
  { "language": "python", "concept": "loops", "kind": "intro",
    "title": "Python for loops — official tutorial",
    "url": "https://docs.python.org/3/tutorial/controlflow.html#for-statements",
    "snippet": "How for/range iteration works in Python." },
  { "language": "python", "concept": "loops", "kind": "video",
    "title": "Python loops explained (video)",
    "url": "https://www.youtube.com/results?search_query=python+loops+tutorial",
    "snippet": "Intro video walkthrough." },
  ...  # ≥4 per (language, concept)
]
```

Seeded into:
- the **`remediation_links` table** via a new `seed_links()` (idempotent upsert on `(url,error_type,language)`),
  called from [`_startup_seed`](backend/app/main.py:99-117) — this is what the serve-time verify/replace/prune
  logic reads.
- (Optional) Qdrant via `ingest_all` so they are also semantically retrievable, with `doc_type="link"` metadata.

Use **stable, real URLs** (official docs: docs.python.org, developer.mozilla.org) for the article floor so the
HTTP availability check passes offline-of-search but online-of-egress; the example.com video URLs in the
current `VIDEOS` seed remain as curated fallbacks.

### 5.3 RAG ingestion idempotency fix (req #9 enablement)

[`ingest_all`](backend/app/rag/ingestion.py:22-24) currently early-returns when `count() > 0`, so newly seeded
docs would never be added on an existing volume. Change to either:
- add a per-doc dedupe key in payload and upsert missing docs, or
- bump a stored "seed version" and re-ingest when it changes, or
- gate the skip behind an env (`RAG_REINGEST=true`).

The `remediation_links` **table** seed (§5.2) is independent of Qdrant and is the authoritative source for the
link-health features, so this Qdrant fix is only needed if links are also pushed into Qdrant.

---

## 6. Frontend plan (`App.jsx` / `styles.css` / `api.js`)

New API client functions in [`api.js`](frontend/src/api.js:1): `getSections(language)`, `getLanguages()`,
`createSection(payload)`, `selectSection(sessionId, sectionId)`, `getSectionIntro(sectionId, language, sessionId)`.

### 6.1 Collapsible sidebar (req #5)

- Add `const [sidebarCollapsed, setSidebarCollapsed] = useState(false)` in
  [`App.jsx`](frontend/src/App.jsx:281). Toggle button in the `aside.sidebar`
  ([`App.jsx`](frontend/src/App.jsx:530)).
- CSS: `.sidebar.collapsed { width: 44px; padding: 8px; overflow: hidden; }` and hide inner content when
  collapsed; a persistent ◀/▶ toggle. Update [`styles.css`](frontend/src/styles.css:9-15).
- Persist in `localStorage` (like `sid`).

### 6.2 Section list with filter + language dropdown (req #6, #8)

Replace the Progress list area ([`App.jsx`](frontend/src/App.jsx:538-551)) with a `SectionsPanel`:
- A **language `<select>`** at the top (python/javascript) — moved here from the editor toolbar; on change,
  refetch sections for that language and update `language` state (editor toolbar language dropdown can be removed
  or kept read-only).
- A **filter `<input>`** above the list; client-side case-insensitive `title.includes(filter)`.
- The list of section cards (`getSections(language).sections`).
- An **"+ Add section"** affordance (req #6): small form (title + optional description) → `createSection` →
  refetch.
- Keep the existing skill/progress mini-list below (optional), now also rendering `Skill.name` if exposed.

### 6.3 Clickable cards + pinned/highlighted current (req #6)

- Each card `onClick` → `selectSection(sessionId, section.id)` → on success, append the returned `response`
  (theme line + new task) to chat via the normal `handleResult` path, and set `currentSectionId` +
  `topic` from `state`.
- Sorting/pinning: render the section whose `id === currentSectionId` **first** with a highlight class
  (`.section-card.current { border-color: #1f6feb; background: #1f6feb22; }`).
- Section objects' `current_section_id` comes from `GET /api/sections` response (§3.1).

### 6.4 Remove editor "Theme" row (req #6)

Delete the `topic-toolbar` block ([`App.jsx`](frontend/src/App.jsx:623-666)) and its CSS
([`styles.css`](frontend/src/styles.css:107-128)). Topic is now driven entirely by section selection.
`getTopic/getTopics/setTopic` in [`api.js`](frontend/src/api.js:141-161) become internal/optional (the PUT path
is now §3.3). Keep `topic` display as the active section highlight.

### 6.5 "?" pictogram per section (req #8)

- Add a `?` button inside each section card; `onClick` (stopPropagation so it doesn't also select) →
  `getSectionIntro(section.id, language, sessionId)` → append `response` + `links` to chat (reuse
  `MessageMeta` links panel by pushing `meta.remediation_links`).
- CSS: small circular `.section-help` button.

### 6.6 Draggable splitter between chat and editor (req #4)

- The layout is `.content { display:flex }` with `.chat { flex:1 }` and `.editor-panel { width:46% }`
  ([`styles.css`](frontend/src/styles.css:20-31)).
- Add a `<div className="splitter" />` between `<section className="chat">` and
  `<section className="editor-panel">` ([`App.jsx`](frontend/src/App.jsx:580-602)).
- State `const [editorWidthPct, setEditorWidthPct] = useState(46)`. Mouse handlers: `onMouseDown` on the
  splitter sets a dragging flag; window `mousemove` computes `editorWidthPct` from clientX relative to
  `.content` bounds (clamp 25%–70%); `mouseup` clears the flag. Apply as inline style
  `style={{ width: editorWidthPct + "%" }}` on `.editor-panel` (overriding the CSS width) and remove the fixed
  `min-width` conflict if needed.
- CSS: `.splitter { width:6px; cursor:col-resize; background:#242838; }` and a hover highlight. Persist pct in
  `localStorage`.

### 6.7 No auto-scroll + unread badge + scroll-to-bottom arrow (req #1)

- Remove/replace the unconditional scroll effect ([`App.jsx`](frontend/src/App.jsx:360-362)).
- Track whether the user is near the bottom: `messagesRef` on `.messages`, an `onScroll` handler computing
  `atBottom = scrollHeight - scrollTop - clientHeight < threshold`.
- State: `const [atBottom, setAtBottom] = useState(true)` and `const [unread, setUnread] = useState(0)`.
- When a new message arrives: if `atBottom`, keep it pinned (auto-scroll allowed only when already at bottom);
  if **not** at bottom, increment `unread` and do **not** scroll.
- Render a floating **down-arrow button** (corner of `.chat`) shown when `!atBottom`, with the `unread` count
  badge; `onClick` → smooth-scroll to `endRef` and reset `unread = 0`. Reset `unread` to 0 whenever `atBottom`
  becomes true via scrolling.
- CSS: `.scroll-bottom-btn { position:absolute; right:16px; bottom:80px; ... }` plus a `.unread-badge`. `.chat`
  needs `position:relative`.

### 6.8 Hide "Sandbox" messages (req #2)

- Tag the sandbox message when pushed in `onRunCode` ([`App.jsx`](frontend/src/App.jsx:499-506)) with
  `kind:"sandbox"` (extend `pushMsg`/message shape).
- In the render loop ([`App.jsx`](frontend/src/App.jsx:582-587)) **skip** messages with `kind === "sandbox"`
  (or simply stop pushing them). Recommended: stop pushing the sandbox summary entirely, since the structured
  pass/fail already surfaces via the assistant `response` + `MessageMeta`. Filtering by `kind` is the
  defensive option that also hides any future server-originated "Sandbox" messages.

---

## 7. Subtask boundaries (clean seams for implementation)

| Subtask | Mode | Files | Delivers |
|---------|------|-------|----------|
| **B1. Schema & migrations** | code | [`models.py`](backend/app/db/models.py:1), [`main.py`](backend/app/main.py:32) | `Section`, `RemediationLink`, `users.current_section_id`; ADD COLUMN migrations |
| **B2. Link store + health** | code | new `backend/app/rag/link_store.py` | `save_links`, `get_links`, `check_url`, pruning (§2.3, §4.2–4.6) |
| **B3. Section service + REST/WS** | code | new `backend/app/api/sections.py`, [`routes.py`](backend/app/api/routes.py:1), [`ws.py`](backend/app/api/ws.py:1), [`progress_repo.py`](backend/app/db/progress_repo.py:1) | §3 endpoints + `get/set_current_section` |
| **B4. Graph flow (section change + ≥4 links + reuse)** | code | [`runner.py`](backend/app/graph/runner.py:39), [`state.py`](backend/app/graph/state.py:9), [`router.py`](backend/app/graph/nodes/router.py:46), [`builder.py`](backend/app/graph/builder.py:74), [`task_selector.py`](backend/app/graph/nodes/task_selector.py:180), [`web_search.py`](backend/app/graph/nodes/web_search.py:161), [`remediation.py`](backend/app/graph/nodes/remediation.py:68), [`uniqueness.py`](backend/app/tasks/uniqueness.py:51) | §4 |
| **B5. Seed** | code | new `backend/app/seed/sections.py`, [`curated.py`](backend/app/seed/content/curated.py:1), new `seed_links()`, [`ingestion.py`](backend/app/rag/ingestion.py:17), [`main.py`](backend/app/main.py:99) | §5 |
| **F1. Sidebar (collapse, sections, filter, language, add, "?", pin)** | code | [`App.jsx`](frontend/src/App.jsx:530), [`api.js`](frontend/src/api.js:1), [`styles.css`](frontend/src/styles.css:9) | §6.1–6.5 |
| **F2. Layout & chat (splitter, no-autoscroll, unread badge, hide Sandbox, remove Theme row)** | code | [`App.jsx`](frontend/src/App.jsx:356), [`styles.css`](frontend/src/styles.css:20) | §6.4, §6.6–6.8 |
| **D1. Docs** | documentation-writer | [`README.md`](README.md:1), [`README_RU.md`](README_RU.md:1) | req #10 |

**Dependency order:** B1 → (B2, B3, B5) → B4 → F1/F2 (frontend depends on B3/B4 endpoints) → D1.
B2 and B5 can proceed in parallel after B1; F1/F2 are independent of each other.

### Backend vs frontend split

- **Backend only:** B1–B5 (schema, link store, section service, graph flow, seed).
- **Frontend only:** F1–F2 (`App.jsx`, `styles.css`, `api.js`).
- **Docs only:** D1 (`README.md`, `README_RU.md`).

---

## 8. Risks & fail-open notes

- **HTTP availability checks** add per-serve latency. Mitigate: short timeout (≤4s), check only the links about
  to be served (≤6), run checks concurrently, and cache `last_checked` so a link verified recently
  (e.g. within 6h) is trusted without re-probing. Must stay within the README's ≤5s median latency target.
- **Pruning** runs lazily on failed checks only (no background job needed) — matches "simple counters, not full
  event logging."
- **Offline egress**: seeded `remediation_links` (§5.2) with real doc URLs guarantee the ≥4-links floor and the
  "?" intro material even when live search returns nothing; the deterministic explanation path is unchanged.
- **Section-change turn** must not clobber an in-progress remediation/success message — only applies its
  theme-set + new-task path when `section_change` is set and there is no code submission (§4.1).
- **"Never the same task twice"** (§4.8) tightens the cooldown to "any prior serve"; the least-recently-served
  fallback prevents dead-ends, and generated themed tasks keep the pool effectively infinite.