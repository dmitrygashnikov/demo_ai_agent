import React, { useEffect, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import Auth from "./Auth.jsx";
import {
  clearToken,
  getGraphSettings,
  getMe,
  getMetricsSummary,
  getProgress,
  getToken,
  getTopic,
  getTopics,
  resume as resumeApi,
  sendChat,
  setGoal,
  setTopic,
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
  const { task_source, remediation_excerpt, remediation_links, offer_next_task } = meta;
  const links = Array.isArray(remediation_links) ? remediation_links : [];
  const hasAnything =
    task_source || remediation_excerpt || links.length > 0 || offer_next_task;
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

      {offer_next_task && (
        <div className="next-task-cue">➡️ Next task ready below</div>
      )}
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
  const [pendingInterrupt, setPendingInterrupt] = useState(false);
  const [busy, setBusy] = useState(false);
  // Topic / theme ("тематика") — free-form, orthogonal to language/skill.
  const [topic, setTopicState] = useState("");        // current persisted theme
  const [topicDraft, setTopicDraft] = useState("");    // free-text input buffer
  const [topicSuggestions, setTopicSuggestions] = useState([]);
  const [topicSaving, setTopicSaving] = useState(false);
  const endRef = useRef(null);

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

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (authUser) {
      refreshProgress();
      loadTopic();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authUser]);

  async function refreshProgress() {
    try {
      const p = await getProgress();
      setSkills(p.skills || []);
      setSolveCount(p.solve_count || 0);
    } catch {
      /* ignore */
    }
  }

  // Load the persisted theme + suggestion list. Fully fail-open: any failure
  // leaves the UI working with no topic (neutral behaviour).
  async function loadTopic() {
    try {
      const sugg = await getTopics();
      setTopicSuggestions(sugg || []);
    } catch {
      /* suggestions are best-effort */
    }
    try {
      const data = await getTopic();
      const t = data?.topic || "";
      setTopicState(t);
      setTopicDraft(t);
    } catch {
      /* topic fetch best-effort */
    }
  }

  // Persist a new theme (empty string clears it). Used by both the dropdown
  // and the free-text input.
  async function applyTopic(next) {
    if (topicSaving) return;
    setTopicSaving(true);
    try {
      const data = await setTopic(next);
      const t = data?.topic || "";
      setTopicState(t);
      setTopicDraft(t);
      pushMsg(
        "assistant",
        t
          ? `🎨 Theme set to "${t}". New tasks will be themed accordingly.`
          : "🎨 Theme cleared — back to neutral tasks."
      );
    } catch (e) {
      pushMsg("assistant", "Could not set theme: " + e.message);
    } finally {
      setTopicSaving(false);
    }
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
      if (typeof s.topic === "string") {
        setTopicState(s.topic);
        setTopicDraft(s.topic);
      }
      // Remember the latest served task so subsequent code submissions can
      // carry it back to the backend.
      if (s.current_task_id) setCurrentTaskId(s.current_task_id);
    }
    refreshProgress();
  }

  async function onSend() {
    const text = input.trim();
    if (!text || busy) return;
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
    pushMsg("user", "```" + language + "\n" + code + "\n```");
    setBusy(true);
    try {
      const res = await submitCode(sessionId, code, currentTaskId);
      handleResult(res);
      if (res.state?.execution_result) {
        const er = res.state.execution_result;
        pushMsg(
          "assistant",
          `🧪 Sandbox: ${er.passed_tests}/${er.total_tests} tests passed` +
            (er.stderr ? `\n${er.stderr.slice(0, 400)}` : "")
        );
      }
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
    <div className="app">
      <aside className="sidebar">
        <div className="user-box">
          <div className="user-name">{authUser.name || authUser.email}</div>
          <div className="muted user-email">{authUser.email}</div>
          <button className="secondary logout-btn" onClick={handleLogout}>
            Log out
          </button>
        </div>
        <h3>Progress</h3>
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
          <div className="content">
            <section className="chat">
              <div className="messages">
                {messages.map((m, i) => (
                  <div key={i} className={"msg " + m.role}>
                    {m.content}
                    {m.role === "assistant" && <MessageMeta meta={m.meta} />}
                  </div>
                ))}
                {busy && <div className="msg assistant muted">…thinking</div>}
                <div ref={endRef} />
              </div>
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

            <section className="editor-panel">
              <div className="editor-toolbar">
                <span className="muted">Solution editor</span>
                <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                  <option value="python">Python</option>
                  <option value="javascript">JavaScript</option>
                </select>
                <button className="secondary" onClick={onRunCode} disabled={busy}>
                  Run &amp; Check
                </button>
              </div>

              <div className="topic-toolbar">
                <span className="muted topic-label">Theme</span>
                <select
                  className="topic-select"
                  value={topicSuggestions.includes(topic) ? topic : ""}
                  disabled={topicSaving}
                  onChange={(e) => applyTopic(e.target.value)}
                >
                  <option value="">— neutral —</option>
                  {topicSuggestions.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <input
                  className="topic-input"
                  placeholder="custom theme…"
                  value={topicDraft}
                  disabled={topicSaving}
                  onChange={(e) => setTopicDraft(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && applyTopic(topicDraft)}
                />
                <button
                  className="secondary topic-set"
                  disabled={topicSaving}
                  onClick={() => applyTopic(topicDraft)}
                >
                  Set
                </button>
                {topic && (
                  <span className="topic-chip" title="Active theme">
                    🎨 {topic}
                    <button
                      className="topic-clear"
                      title="Clear theme"
                      disabled={topicSaving}
                      onClick={() => applyTopic("")}
                    >
                      ×
                    </button>
                  </span>
                )}
              </div>
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
