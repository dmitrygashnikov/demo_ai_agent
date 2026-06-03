import React, { useEffect, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import {
  getGraphSettings,
  getMetricsSummary,
  getProgress,
  resume as resumeApi,
  sendChat,
  setGoal,
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

export default function App() {
  const [userId] = useState(() => localStorage.getItem("uid") || uid());
  const [sessionId] = useState(() => localStorage.getItem("sid") || uid());
  const [tab, setTab] = useState("tutor"); // "tutor" | "settings"
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
  const [pendingInterrupt, setPendingInterrupt] = useState(false);
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    localStorage.setItem("uid", userId);
    localStorage.setItem("sid", sessionId);
  }, [userId, sessionId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function refreshProgress() {
    try {
      const p = await getProgress(userId);
      setSkills(p.skills || []);
      setSolveCount(p.solve_count || 0);
    } catch {
      /* ignore */
    }
  }

  function pushMsg(role, content) {
    setMessages((m) => [...m, { role, content }]);
  }

  function handleResult(res) {
    if (res.interrupted) {
      setPendingInterrupt(true);
      pushMsg("assistant", "❓ " + res.question);
    } else {
      setPendingInterrupt(false);
      pushMsg("assistant", res.response || "(no response)");
      if (res.state?.language) setLanguage(res.state.language);
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
        res = await setGoal(userId, sessionId, text, null);
      } else {
        res = await sendChat(userId, sessionId, text);
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
      const res = await submitCode(userId, sessionId, code);
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

  return (
    <div className="app">
      <aside className="sidebar">
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
