import React, { useState } from "react";
import { login, register, setToken } from "./api";

// Login / Register screen shown before the main tutor UI. Registration is open
// to everyone — there is no email verification step.
export default function Auth({ onAuthenticated }) {
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("python");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const isRegister = mode === "register";

  async function onSubmit(e) {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      const data = isRegister
        ? await register({ email, password, name, preferred_language: language })
        : await login({ email, password });
      setToken(data.access_token);
      onAuthenticated(data.user);
    } catch (err) {
      setError(err.message || "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <h1>🎓 Adaptive AI Coding Tutor</h1>
        <p className="muted">
          {isRegister
            ? "Create an account to start learning. No email verification required."
            : "Sign in to continue your personalised learning journey."}
        </p>

        <div className="auth-tabs">
          <button
            type="button"
            className={"auth-tab " + (!isRegister ? "active" : "")}
            onClick={() => {
              setMode("login");
              setError(null);
            }}
          >
            Log in
          </button>
          <button
            type="button"
            className={"auth-tab " + (isRegister ? "active" : "")}
            onClick={() => {
              setMode("register");
              setError(null);
            }}
          >
            Register
          </button>
        </div>

        <form className="auth-form" onSubmit={onSubmit}>
          <label htmlFor="auth-email">Email</label>
          <input
            id="auth-email"
            type="email"
            value={email}
            placeholder="admin@example.com"
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            required
          />

          <label htmlFor="auth-password">Password</label>
          <input
            id="auth-password"
            type="password"
            value={password}
            placeholder={isRegister ? "Choose a password (min 6 chars)" : "Your password"}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={isRegister ? "new-password" : "current-password"}
            required
          />

          {isRegister && (
            <>
              <label htmlFor="auth-name">Name (optional)</label>
              <input
                id="auth-name"
                type="text"
                value={name}
                placeholder="Your name"
                onChange={(e) => setName(e.target.value)}
              />

              <label htmlFor="auth-language">Preferred language</label>
              <select
                id="auth-language"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                <option value="python">Python</option>
                <option value="javascript">JavaScript</option>
              </select>
            </>
          )}

          {error && <div className="auth-error">{error}</div>}

          <button type="submit" disabled={busy} className="auth-submit">
            {busy ? "Please wait…" : isRegister ? "Create account" : "Log in"}
          </button>
        </form>

        <div className="muted auth-hint">
          Default demo account: <code>admin@example.com</code> /{" "}
          <code>qwerty123456</code> (override via APP_DEFAULT_USER_* in .env).
        </div>
      </div>
    </div>
  );
}
