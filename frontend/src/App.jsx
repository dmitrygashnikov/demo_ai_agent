import React, { useEffect, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import Auth from "./Auth.jsx";
import {
  clearToken,
  createSection,
  getGraphSettings,
  getLanguages,
  getMe,
  getMetricsSummary,
  getProgress,
  getSectionIntro,
  getSections,
  getToken,
  resume as resumeApi,
  selectSection,
  sendChat,
  setGoal,
  setUnauthorizedHandler,
  submitCode,
  updateGraphSettings,
} from "./api";

const uid = () => Math.random().toString(36).slice(2, 10);

// Langfuse self-hosted UI (see docker-compose: langfuse on host port 3001).
const LANGFUSE_UI_URL = "http://localhost:3001";

const SETTING_FIELDS = [
  {
    key: "COOLDOWN_SOLVES",
    label: "Cooldown solves",
    hint: "A task is not re-served within this many of the student's solves.",
  },
  {
    key: "MAX_REGEN_ATTEMPTS",
    label: "Max regen attempts",
    hint: "Max code self-execution regeneration attempts before giving up.",
  },
  {
    key: "MASTERY_SUCCESS_STREAK",
    label: "Mastery success streak",
    hint: "Consecutive successes required to mark a skill as mastered.",
  },
  {
    key: "ADVANCED_SUCCESS_STREAK",
    label: "Advanced success streak",
    hint: "Consecutive successes on a mastered skill that trigger real-world cases.",
  },
];

function GraphSettingsPanel() {
  const [values, setValues] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null); // {type: 'ok'|'err', text}
  const [metrics, setMetrics] = useState(null);

  async function load() {
    setLoading(true);
    setStatus(null);
    try {
      const s = await getGraphSettings();
      setValues(s);
    } catch (e) {
      setStatus({ type: "err", text: "Failed to load: " + e.message });
    } finally {
      setLoading(false);
    }
  }

  async function loadMetrics() {
    try {
      const m = await getMetricsSummary();
      setMetrics(m);
    } catch {
      /* ignore — metrics are best-effort */
    }
  }

  useEffect(() => {
    load();
    loadMetrics();
  }, []);

  function onChange(key, raw) {
    setValues((v) => ({ ...v, [key]: raw }));
  }

  function onToggle(key, checked) {
    setValues((v) => ({ ...v, [key]: checked }));
  }

  async function onSave() {
    if (saving || !values) return;
    setSaving(true);
    setStatus(null);
    try {
      const payload = {};
      for (const f of SETTING_FIELDS) {
        payload[f.key] = parseInt(values[f.key], 10);
      }
      payload.TOPIC_GUARD_ENABLED = !!values.TOPIC_GUARD_ENABLED;
      const updated = await updateGraphSettings(payload);
      setValues(updated);
      setStatus({ type: "ok", text: "Saved — applied at runtime (no restart)." });
    } catch (e) {
      setStatus({ type: "err", text: "Save failed: " + e.message });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="settings-panel">
      <h2>Graph Settings</h2>
      <p className="muted">
        Runtime-editable adaptive parameters. Changes are persisted to Postgres,
        cached in Redis, and applied immediately — no backend restart required.
      </p>

      {loading && <div className="muted">Loading…</div>}

      {!loading && values && (
        <div className="settings-form">
          {SETTING_FIELDS.map((f) => (
            <div className="settings-row" key={f.key}>
              <label htmlFor={f.key}>{f.label}</label>
              <input
                id={f.key}
                type="number"
                min="1"
                value={values[f.key] ?? ""}
                onChange={(e) => onChange(f.key, e.target.value)}
              />
              <div className="muted settings-hint">{f.hint}</div>
            </div>
          ))}

          <div className="settings-row" key="TOPIC_GUARD_ENABLED">
            <label htmlFor="TOPIC_GUARD_ENABLED">On-topic guard</label>
            <input
              id="TOPIC_GUARD_ENABLED"
              type="checkbox"
              checked={!!values.TOPIC_GUARD_ENABLED}
              onChange={(e) => onToggle("TOPIC_GUARD_ENABLED", e.target.checked)}
            />
            <div className="muted settings-hint">
              When enabled, off-topic chat (not about programming or the current
              lesson) is politely declined. Fail-open if the LLM classifier is
              unavailable. Applied at runtime — no restart.
            </div>
          </div>

          <div className="settings-actions">
            <button onClick={onSave} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </button>
            <button className="secondary" onClick={load} disabled={saving}>
              Reload
            </button>
          </div>

          {status && (
            <div className={"settings-status " + status.type}>{status.text}</div>
          )}
        </div>
      )}

      <div className="settings-langfuse">
        <h3>Observability</h3>
        <a href={LANGFUSE_UI_URL} target="_blank" rel="noreferrer">
          Open Langfuse (tracing) ↗
        </a>
        <div className="muted">
          LangGraph runs (nodes + LLM calls) are traced in Langfuse. Tracing is
          enabled out-of-the-box for the default admin project. UI served on{" "}
          {LANGFUSE_UI_URL} — log in with the admin account (see README).
        </div>

        <h3 style={{ marginTop: 16 }}>Backend metrics</h3>
        {!metrics && <div className="muted">Loading metrics…</div>}
        {metrics && (
          <div className="metrics-grid">
            <div className="metric">
              <div className="metric-value">{metrics.users}</div>
              <div className="muted">users</div>
            </div>
            <div className="metric">
              <div className="metric-value">{metrics.total_solves}</div>
              <div className="muted">solves</div>
            </div>
            <div className="metric">
              <div className="metric-value">{metrics.attempts}</div>
              <div className="muted">attempts</div>
            </div>
            <div className="metric">
              <div className="metric-value">
                {Math.round((metrics.success_rate || 0) * 100)}%
              </div>
              <div className="muted">success rate</div>
            </div>
            <div className="metric">
              <div className="metric-value">
                {Math.round((metrics.avg_mastery || 0) * 100)}%
              </div>
              <div className="muted">avg mastery</div>
            </div>
            <div className="metric">
              <div className="metric-value">{metrics.tasks_served}</div>
              <div className="muted">tasks served</div>
            </div>
          </div>
        )}
        {metrics && (
          <div className="muted" style={{ marginTop: 8 }}>
            Tracing {metrics.langfuse?.enabled ? "active" : "disabled"} · source:
            GET /api/metrics/summary
          </div>
        )}
        <button
          className="secondary"
          style={{ marginTop: 8 }}
          onClick={loadMetrics}
        >
          Refresh metrics
        </button>
      </div>
    </div>
  );
}

// Renders the structured fields the backend now returns alongside an assistant
// message (Groups C/D/E surfacing): a task-source badge, the failure
// remediation explanation + web links, and a subtle next-task cue on success.
// All fields are optional and fail-open — nothing renders when absent.
function MessageMeta({ meta }) {
  if (!meta) return null;
  const { task_source, remediation_excerpt, remediation_links, offer_next_task, intro_links } = meta;
  const links = Array.isArray(remediation_links) ? remediation_links : [];
  // Intro material from the "?" pictogram (req #8): distinguishes
  // kind:"video" from "article" with a small icon.
  const intro = Array.isArray(intro_links) ? intro_links : [];
  const hasAnything =
    task_source || remediation_excerpt || links.length > 0 || offer_next_task || intro.length > 0;
  if (!hasAnything) return null;

  return (
    <div className="msg-meta">
      {task_source && (
        <span className={"badge source-" + task_source} title="Task provenance">
          {task_source === "generated" ? "✨ generated" : "📚 curated"}
        </span>
      )}

      {remediation_excerpt && (
        <div className="excerpt-panel">
          <div className="excerpt-title">💡 Explanation</div>
          <div className="excerpt-body">{remediation_excerpt}</div>
        </div>
      )}

      {links.length > 0 && (
        <div className="links-panel">
          <div className="links-title">🔗 Helpful resources</div>
          <ul className="links-list">
            {links.map((l, i) => (
              <li key={i}>
                <a href={l.url} target="_blank" rel="noreferrer">
                  {l.title || l.url}
                </a>
                {l.snippet && <div className="muted link-snippet">{l.snippet}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {intro.length > 0 && (
        <div className="links-panel intro-panel">
          <div className="links-title">📚 Intro material</div>
          <ul className="links-list">
            {intro.map((l, i) => {
              const isVideo = l.kind === "video";
              return (
                <li key={i} className={isVideo ? "intro-video" : "intro-article"}>
                  <a href={l.url} target="_blank" rel="noreferrer">
                    <span className="intro-kind" aria-hidden="true">
                      {isVideo ? "🎬" : "📄"}
                    </span>{" "}
                    {l.title || l.url}
                  </a>
                  {l.snippet && <div className="muted link-snippet">{l.snippet}</div>}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {offer_next_task && (
        <div className="next-task-cue">➡️ Next task ready below</div>
      )}
    </div>
  );
}

// Sidebar sections/themes panel (req #6, #8): a language dropdown, a client-side
// title filter, the list of section cards (pinned + highlighted current section
// at the top), a "?" intro button per card, and an "+ Add section" form.
// Wiring lives in App via the callbacks passed in; this component owns only the
// local UI state (filter text, add-form fields, validation error).
function SectionsPanel({
  languages,
  language,
  onLanguageChange,
  sections,
  currentSectionId,
  loading,
  busy,
  onSelect,
  onIntro,
  onCreate,
}) {
  const [filter, setFilter] = useState("");
  const [adding, setAdding] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [createErr, setCreateErr] = useState(null);
  const [creating, setCreating] = useState(false);

  // Filter (case-insensitive substring on title), then pin the current section
  // to the very top while preserving the backend's order for the rest.
  const q = filter.trim().toLowerCase();
  const filtered = sections.filter((s) =>
    q ? (s.title || "").toLowerCase().includes(q) : true
  );
  const ordered = [...filtered].sort((a, b) => {
    const ac = a.id === currentSectionId ? 0 : 1;
    const bc = b.id === currentSectionId ? 0 : 1;
    return ac - bc;
  });

  async function submitNew(e) {
    e?.preventDefault?.();
    const title = newTitle.trim();
    if (!title || creating) {
      if (!title) setCreateErr("Title is required.");
      return;
    }
    setCreating(true);
    setCreateErr(null);
    try {
      await onCreate({ title, description: newDesc.trim() || undefined });
      // Success — reset and collapse the form.
      setNewTitle("");
      setNewDesc("");
      setAdding(false);
    } catch (err) {
      // Surface 400 (title too long) / 409 (already exists) inline.
      setCreateErr(err?.message || "Could not create section.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="sections-panel">
      <div className="sections-head">
        <h3>Sections</h3>
        <label className="sections-lang">
          <span className="muted">Language</span>
          <select
            value={language}
            onChange={(e) => onLanguageChange(e.target.value)}
            aria-label="Learning language"
          >
            {languages.map((l) => (
              <option key={l.id} value={l.id}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <input
        className="sections-filter"
        type="text"
        placeholder="Filter sections…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        aria-label="Filter sections by title"
      />

      <div className="sections-list">
        {loading && <div className="muted">Loading sections…</div>}
        {!loading && ordered.length === 0 && (
          <div className="muted">No sections match.</div>
        )}
        {ordered.map((s) => {
          const isCurrent = s.id === currentSectionId;
          return (
            <div
              key={s.id}
              className={"section-card" + (isCurrent ? " current" : "")}
              role="button"
              tabIndex={0}
              title={s.description || s.title}
              onClick={() => !busy && onSelect(s)}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && !busy) {
                  e.preventDefault();
                  onSelect(s);
                }
              }}
            >
              <div className="section-card-main">
                <div className="section-title">
                  {isCurrent && <span className="section-pin" title="Current section">📌</span>}
                  {s.title}
                  {s.is_user_created && (
                    <span className="section-tag" title="Your section">you</span>
                  )}
                </div>
                {s.description && (
                  <div className="muted section-desc">{s.description}</div>
                )}
              </div>
              <button
                type="button"
                className="section-help"
                title={`Intro material for "${s.title}"`}
                aria-label={`Intro material for ${s.title}`}
                disabled={busy}
                onClick={(e) => {
                  e.stopPropagation();
                  onIntro(s);
                }}
              >
                ?
              </button>
            </div>
          );
        })}
      </div>

      <div className="sections-add">
        {!adding && (
          <button
            type="button"
            className="secondary section-add-btn"
            onClick={() => {
              setAdding(true);
              setCreateErr(null);
            }}
          >
            + Add section/theme
          </button>
        )}
        {adding && (
          <form className="section-add-form" onSubmit={submitNew}>
            <input
              type="text"
              placeholder="Section title (max 120 chars)"
              value={newTitle}
              maxLength={200}
              autoFocus
              onChange={(e) => setNewTitle(e.target.value)}
              aria-label="New section title"
            />
            <input
              type="text"
              placeholder="Description (optional)"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              aria-label="New section description"
            />
            {createErr && <div className="section-add-err">{createErr}</div>}
            <div className="section-add-actions">
              <button type="submit" disabled={creating}>
                {creating ? "Adding…" : "Add"}
              </button>
              <button
                type="button"
                className="secondary"
                disabled={creating}
                onClick={() => {
                  setAdding(false);
                  setCreateErr(null);
                  setNewTitle("");
                  setNewDesc("");
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [sessionId] = useState(() => localStorage.getItem("sid") || uid());
  const [tab, setTab] = useState("tutor"); // "tutor" | "settings"

  // --- Authentication state ---
  const [authUser, setAuthUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "👋 Hi! I'm your adaptive coding tutor. Tell me what you'd like to learn — e.g. \"I want to learn Python for automation\".",
    },
  ]);
  const [input, setInput] = useState("");
  const [language, setLanguage] = useState("python");
  const [code, setCode] = useState("def sum_to_n(n):\n    # your code here\n    return 0\n");
  const [skills, setSkills] = useState([]);
  const [solveCount, setSolveCount] = useState(0);
  // Track the active task id served by the backend so code submissions can be
  // self-describing (lets the backend recover the task if its session state
  // was lost).
  const [currentTaskId, setCurrentTaskId] = useState(null);
  // Problem 4 — answer-type exercises (predict_output / trace_value) ask the
  // student to TYPE the expected value/output rather than write a function. The
  // backend routes these to ``check_typed_answer`` regardless, so the SAME text
  // input is the submission; we only adapt the UI affordances (label/placeholder/
  // button) so it's clear what to enter. Fail-open: unknown/absent type → code.
  const [answerMode, setAnswerMode] = useState(false);
  const [pendingInterrupt, setPendingInterrupt] = useState(false);
  const [busy, setBusy] = useState(false);
  // Topic / theme ("тематика") — free-form, orthogonal to language/skill.
  // The editor "Theme" row was removed (req #6); the topic is now driven by
  // section selection in the sidebar. We still keep the topic value threaded so
  // the turn endpoints / MessageMeta stay in sync when the backend echoes it.
  const [topic, setTopicState] = useState("");        // current persisted theme

  // --- Sidebar sections / themes (req #6, #8) ---
  const [languages, setLanguages] = useState([
    { id: "python", label: "Python" },
    { id: "javascript", label: "JavaScript" },
  ]);
  const [sections, setSections] = useState([]);
  const [currentSectionId, setCurrentSectionId] = useState(null);
  const [sectionsLoading, setSectionsLoading] = useState(false);
  // Collapsible sidebar (req #5) — persisted so it survives reloads.
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem("sidebar_collapsed") === "1"
  );
  const endRef = useRef(null);

  // --- Chat scroll behaviour (req #1) ---
  // No more unconditional auto-scroll. We track whether the user is near the
  // bottom of the .messages container; new assistant/system messages that
  // arrive while the user has scrolled up increment an "unread" counter and
  // surface a floating scroll-to-bottom arrow instead of yanking the view.
  const messagesRef = useRef(null);   // the scrollable .messages container
  const [atBottom, setAtBottom] = useState(true);
  const [unread, setUnread] = useState(0);
  // Number of messages already accounted for, so the [messages] effect can tell
  // whether genuinely-new messages arrived (vs. an unrelated re-render).
  const prevMsgCountRef = useRef(messages.length);
  // Set transiently when the local user performs an action that SHOULD pin the
  // view to the bottom (typing a chat message / submitting code) — typical chat
  // UX where your own send scrolls you down, but incoming messages do not.
  const forceScrollRef = useRef(false);

  // Threshold (px) for "near the bottom" — small slack so a few px of rounding
  // doesn't leave the arrow stuck on.
  const BOTTOM_THRESHOLD = 60;

  // Smoothly scroll the chat to the newest message and clear the unread badge.
  function scrollToBottom(behavior = "smooth") {
    const el = messagesRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior });
    } else {
      endRef.current?.scrollIntoView({ behavior });
    }
    setUnread(0);
    setAtBottom(true);
  }

  // Scroll listener: recompute atBottom and clear unread once the user reaches
  // the bottom by scrolling manually.
  function onMessagesScroll() {
    const el = messagesRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    const nearBottom = distance < BOTTOM_THRESHOLD;
    setAtBottom(nearBottom);
    if (nearBottom) setUnread(0);
  }

  // --- Draggable splitter (req #4) ---
  // The chat and editor panels sit side-by-side (.content is a flex row), so the
  // splitter resizes horizontally (col-resize). editorWidthPct is the editor
  // panel width as a % of the .content width; persisted across reloads.
  const SPLIT_MIN = 25;
  const SPLIT_MAX = 70;
  const contentRef = useRef(null);
  const [editorWidthPct, setEditorWidthPct] = useState(() => {
    const saved = parseFloat(localStorage.getItem("editor_width_pct"));
    return Number.isFinite(saved) ? Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, saved)) : 46;
  });
  const draggingRef = useRef(false);

  // Force logout (used both by the button and on any 401 from the API layer).
  function handleLogout() {
    clearToken();
    setAuthUser(null);
  }

  // On startup: if a token exists, validate it via /api/auth/me.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setAuthUser(null);
    });
    let cancelled = false;
    async function check() {
      if (!getToken()) {
        setAuthChecked(true);
        return;
      }
      try {
        const me = await getMe();
        if (!cancelled) setAuthUser(me);
      } catch {
        clearToken();
      } finally {
        if (!cancelled) setAuthChecked(true);
      }
    }
    check();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    localStorage.setItem("sid", sessionId);
  }, [sessionId]);

  useEffect(() => {
    if (authUser?.preferred_language) setLanguage(authUser.preferred_language);
  }, [authUser]);

  // Chat scroll on new messages (req #1): NO unconditional auto-scroll. We only
  // pin to the bottom when (a) the user just performed an action that should
  // follow the view down (their own send / code submit — forceScrollRef), or
  // (b) they were already at the bottom. Otherwise incoming messages bump the
  // unread counter and the floating arrow appears.
  useEffect(() => {
    const prev = prevMsgCountRef.current;
    const added = messages.length - prev;
    prevMsgCountRef.current = messages.length;
    if (added <= 0) return; // no genuinely-new messages
    if (forceScrollRef.current) {
      forceScrollRef.current = false;
      // Defer to next frame so the new node is laid out before scrolling.
      requestAnimationFrame(() => scrollToBottom("smooth"));
      return;
    }
    if (atBottom) {
      requestAnimationFrame(() => scrollToBottom("auto"));
    } else {
      setUnread((u) => u + added);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  // Persist the chosen chat↔editor split so it survives reloads (req #4).
  useEffect(() => {
    localStorage.setItem("editor_width_pct", String(editorWidthPct));
  }, [editorWidthPct]);

  // Window-level drag handlers for the splitter. Attached once; they early-out
  // unless a drag is in progress (draggingRef). Computing the editor width from
  // clientX relative to the .content bounds keeps it correct regardless of the
  // (independent) sidebar collapse state.
  useEffect(() => {
    function onMove(e) {
      if (!draggingRef.current) return;
      const content = contentRef.current;
      if (!content) return;
      const rect = content.getBoundingClientRect();
      if (rect.width <= 0) return;
      // Editor sits on the RIGHT, so its width = distance from clientX to the
      // right edge of .content.
      const pct = ((rect.right - e.clientX) / rect.width) * 100;
      const clamped = Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, pct));
      setEditorWidthPct(clamped);
      e.preventDefault();
    }
    function onUp() {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      document.body.classList.remove("splitter-dragging");
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  // Begin a splitter drag (mousedown on the handle). Keyboard users can also
  // nudge the split with arrow keys via onSplitterKeyDown below.
  function onSplitterMouseDown(e) {
    draggingRef.current = true;
    document.body.classList.add("splitter-dragging");
    e.preventDefault();
  }

  function onSplitterKeyDown(e) {
    if (e.key === "ArrowLeft") {
      // Grow the editor (shrink chat).
      setEditorWidthPct((p) => Math.min(SPLIT_MAX, p + 2));
      e.preventDefault();
    } else if (e.key === "ArrowRight") {
      setEditorWidthPct((p) => Math.max(SPLIT_MIN, p - 2));
      e.preventDefault();
    }
  }

  useEffect(() => {
    if (authUser) {
      refreshProgress();
      loadLanguages();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authUser]);

  // Refetch sections whenever the active learning language changes (and once
  // the user is known). The editor language follows this same `language` state.
  useEffect(() => {
    if (authUser) refreshSections(language);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authUser, language]);

  // Persist the collapsed sidebar state (like `sid`).
  useEffect(() => {
    localStorage.setItem("sidebar_collapsed", sidebarCollapsed ? "1" : "0");
  }, [sidebarCollapsed]);

  async function refreshProgress() {
    try {
      const p = await getProgress();
      setSkills(p.skills || []);
      setSolveCount(p.solve_count || 0);
    } catch {
      /* ignore */
    }
  }

  // Load the available languages for the sidebar dropdown. Fail-open: the
  // default MVP set already populated in state is kept on any error.
  async function loadLanguages() {
    try {
      const langs = await getLanguages();
      if (langs && langs.length) setLanguages(langs);
    } catch {
      /* best-effort — keep defaults */
    }
  }

  // Fetch the sections for a language (global seeded + the user's own) and the
  // server-side current section. Fail-open: an empty list keeps the UI usable.
  async function refreshSections(lang) {
    setSectionsLoading(true);
    try {
      const data = await getSections(lang);
      setSections(data?.sections || []);
      setCurrentSectionId(data?.current_section_id || null);
    } catch {
      setSections([]);
    } finally {
      setSectionsLoading(false);
    }
  }

  // Sidebar language dropdown → also the active learning language for the rest
  // of the app (the editor language follows this). The section refetch is
  // driven by the `language` effect above.
  function onLanguageChange(next) {
    if (next && next !== language) setLanguage(next);
  }

  // Click a section card → set the topic AND serve a fresh themed task
  // (mirrors /api/chat). handleResult swaps in state.current_task_id's new task
  // and drops the cancelled one; we also pin the newly-selected section.
  async function onSelectSection(section) {
    if (busy) return;
    setBusy(true);
    try {
      const res = await selectSection(sessionId, section.id);
      handleResult(res);
      const newCurrent = res?.state?.current_section_id || section.id;
      setCurrentSectionId(newCurrent);
    } catch (e) {
      pushMsg("assistant", "Could not select section: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  // "?" pictogram → fetch intro material and render it in the chat as an
  // assistant message whose `meta.intro_links` drives the links/videos list.
  async function onSectionIntro(section) {
    if (busy) return;
    setBusy(true);
    try {
      const res = await getSectionIntro(section.id, { sessionId, language });
      pushMsg("assistant", res?.response || `📚 Intro to ${section.title}`, {
        intro_links: res?.links || [],
      });
    } catch (e) {
      pushMsg("assistant", "Could not load intro material: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  // Create a user section for the current language, then refresh the list.
  // Re-throws so SectionsPanel can show inline 400/409 validation errors.
  async function onCreateSection({ title, description }) {
    const created = await createSection({ language, title, description });
    await refreshSections(language);
    return created;
  }

  function pushMsg(role, content, meta) {
    setMessages((m) => [...m, { role, content, meta }]);
  }

  function handleResult(res) {
    if (res.interrupted) {
      setPendingInterrupt(true);
      pushMsg("assistant", "❓ " + res.question);
    } else {
      setPendingInterrupt(false);
      // Attach the structured payload fields so MessageMeta can render the
      // task-source badge, remediation links/excerpt and the next-task cue.
      const s = res.state || {};
      pushMsg("assistant", res.response || "(no response)", {
        task_source: s.task_source,
        remediation_excerpt: s.remediation_excerpt,
        remediation_links: s.remediation_links,
        offer_next_task: s.offer_next_task,
      });
      if (s.language) setLanguage(s.language);
      // Keep the local theme in sync if the backend echoes it.
      if (typeof s.topic === "string") setTopicState(s.topic);
      // Keep the pinned/highlighted current section in sync when a turn (e.g. a
      // section-select turn) echoes it.
      if (s.current_section_id) setCurrentSectionId(s.current_section_id);
      // Remember the latest served task so subsequent code submissions can
      // carry it back to the backend. A section-change turn returns the NEW
      // themed task here and discards `cancelled_task_id` (handled server-side).
      if (s.current_task_id) setCurrentTaskId(s.current_task_id);
      // Problem 4: switch the submission affordance for ANSWER-types. The
      // backend (code_validator → check_typed_answer) interprets the same text
      // input as a typed value for these types, so we only adjust the UI.
      if (typeof s.last_exercise_type === "string") {
        setAnswerMode(
          s.last_exercise_type === "predict_output" ||
            s.last_exercise_type === "trace_value"
        );
      }
    }
    refreshProgress();
  }

  async function onSend() {
    const text = input.trim();
    if (!text || busy) return;
    // The user's OWN message should follow the view to the bottom (typical chat
    // UX), so request a one-shot pinned scroll for this push.
    forceScrollRef.current = true;
    pushMsg("user", text);
    setInput("");
    setBusy(true);
    try {
      let res;
      if (pendingInterrupt) {
        res = await resumeApi(sessionId, text);
      } else if (/want to learn|learn |goal|хочу|научиться/i.test(text)) {
        res = await setGoal(sessionId, text, null);
      } else {
        res = await sendChat(sessionId, text);
      }
      handleResult(res);
    } catch (e) {
      pushMsg("assistant", "Error: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  async function onRunCode() {
    if (busy) return;
    // Submitting code is a deliberate user action — pin the view to the bottom
    // so the echoed submission + the assistant response are visible.
    forceScrollRef.current = true;
    // Answer-types echo the typed value as-is; code-types echo a fenced block.
    pushMsg(
      "user",
      answerMode ? code : "```" + language + "\n" + code + "\n```"
    );
    setBusy(true);
    try {
      const res = await submitCode(sessionId, code, currentTaskId);
      handleResult(res);
      // req #2: do NOT push a "🧪 Sandbox: …" status message into the chat. The
      // structured pass/fail already surfaces via the assistant `response` +
      // MessageMeta, so the sandbox status chatter is suppressed entirely.
    } catch (e) {
      pushMsg("assistant", "Error: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  // While verifying an existing token, render nothing (avoids auth flicker).
  if (!authChecked) {
    return (
      <div className="auth-screen">
        <div className="muted">Loading…</div>
      </div>
    );
  }

  // Not authenticated → show the login / register screen.
  if (!authUser) {
    return <Auth onAuthenticated={(user) => setAuthUser(user)} />;
  }

  return (
    <div className={"app" + (sidebarCollapsed ? " sidebar-is-collapsed" : "")}>
      <aside className={"sidebar" + (sidebarCollapsed ? " collapsed" : "")}>
        <button
          className="secondary sidebar-toggle"
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!sidebarCollapsed}
          onClick={() => setSidebarCollapsed((c) => !c)}
        >
          {sidebarCollapsed ? "▶" : "◀"}
        </button>

        {!sidebarCollapsed && (
          <div className="sidebar-inner">
            <div className="user-box">
              <div className="user-name">{authUser.name || authUser.email}</div>
              <div className="muted user-email">{authUser.email}</div>
              <button className="secondary logout-btn" onClick={handleLogout}>
                Log out
              </button>
            </div>

            <SectionsPanel
              languages={languages}
              language={language}
              onLanguageChange={onLanguageChange}
              sections={sections}
              currentSectionId={currentSectionId}
              loading={sectionsLoading}
              busy={busy}
              onSelect={onSelectSection}
              onIntro={onSectionIntro}
              onCreate={onCreateSection}
            />

            <h3 className="progress-head">Progress</h3>
            <div className="muted">Solves: {solveCount}</div>
            <div style={{ marginTop: 12 }}>
              {skills.length === 0 && <div className="muted">No skills tracked yet. Set a goal to begin.</div>}
              {skills.map((s) => (
                <div className="skill" key={s.skill_id}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span>{s.skill_id}</span>
                    <span className={"state " + s.state}>{s.state}</span>
                  </div>
                  <div className="muted">mastery {Math.round((s.mastery || 0) * 100)}% · attempts {s.attempts}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </aside>

      <div className="main">
        <header className="header">
          <h1>🎓 Adaptive AI Coding Tutor</h1>
          <small>Personalised, RAG-grounded, sandbox-verified programming tutor</small>
          <nav className="tabs">
            <button
              className={"tab " + (tab === "tutor" ? "active" : "")}
              onClick={() => setTab("tutor")}
            >
              Tutor
            </button>
            <button
              className={"tab " + (tab === "settings" ? "active" : "")}
              onClick={() => setTab("settings")}
            >
              Graph Settings
            </button>
          </nav>
        </header>

        {tab === "settings" ? (
          <div className="content settings-content">
            <GraphSettingsPanel />
          </div>
        ) : (
          <div className="content" ref={contentRef}>
            <section className="chat">
              <div
                className="messages"
                ref={messagesRef}
                onScroll={onMessagesScroll}
              >
                {messages.map((m, i) => (
                  <div key={i} className={"msg " + m.role}>
                    {m.content}
                    {m.role === "assistant" && <MessageMeta meta={m.meta} />}
                  </div>
                ))}
                {busy && <div className="msg assistant muted">…thinking</div>}
                <div ref={endRef} />
              </div>

              {/* Floating scroll-to-bottom arrow + unread badge (req #1). Shown
                  when the user is scrolled up; the badge appears only when there
                  are unread incoming messages. */}
              {!atBottom && (
                <button
                  type="button"
                  className={"scroll-bottom-btn" + (unread > 0 ? " has-unread" : "")}
                  title={unread > 0 ? `${unread} new message${unread > 1 ? "s" : ""} — scroll to latest` : "Scroll to latest"}
                  aria-label={unread > 0 ? `${unread} unread messages, scroll to latest` : "Scroll to latest message"}
                  onClick={() => scrollToBottom("smooth")}
                >
                  <span aria-hidden="true">↓</span>
                  {unread > 0 && (
                    <span className="unread-badge">{unread > 99 ? "99+" : unread}</span>
                  )}
                </button>
              )}

              <div className="composer">
                <input
                  value={input}
                  placeholder={pendingInterrupt ? "Answer the question…" : "Ask, set a goal, or chat…"}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && onSend()}
                />
                <button onClick={onSend} disabled={busy}>Send</button>
              </div>
            </section>

            {/* Draggable splitter between chat and editor (req #4). Side-by-side
                layout → col-resize. Keyboard-focusable with arrow-key nudge. */}
            <div
              className="splitter"
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize chat and editor panels"
              tabIndex={0}
              title="Drag to resize (←/→ to nudge)"
              onMouseDown={onSplitterMouseDown}
              onKeyDown={onSplitterKeyDown}
            />

            <section
              className="editor-panel"
              style={{ width: editorWidthPct + "%" }}
            >
              <div className="editor-toolbar">
                <span className="muted">
                  {answerMode ? "Your answer (type the expected value)" : "Solution editor"}
                </span>
                <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                  <option value="python">Python</option>
                  <option value="javascript">JavaScript</option>
                </select>
                <button className="secondary" onClick={onRunCode} disabled={busy}>
                  {answerMode ? "Submit answer" : "Run & Check"}
                </button>
              </div>
              {answerMode && (
                <div className="muted answer-hint">
                  ✏️ This is a predict-output / trace-value exercise — type the
                  expected value or output directly (no function needed) and
                  submit.
                </div>
              )}

              <Editor
                height="100%"
                language={language}
                theme="vs-dark"
                value={code}
                onChange={(v) => setCode(v ?? "")}
                options={{ minimap: { enabled: false }, fontSize: 14 }}
              />
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
