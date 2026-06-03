import React, { useEffect, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import {
  getProgress,
  resume as resumeApi,
  sendChat,
  setGoal,
  submitCode,
} from "./api";

const uid = () => Math.random().toString(36).slice(2, 10);

export default function App() {
  const [userId] = useState(() => localStorage.getItem("uid") || uid());
  const [sessionId] = useState(() => localStorage.getItem("sid") || uid());
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
        </header>

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
      </div>
    </div>
  );
}
