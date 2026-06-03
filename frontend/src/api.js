// Backend client for the Adaptive AI Coding Tutor.
// REST calls go through the nginx /api proxy; WebSocket via /ws.
// All protected calls attach the JWT Bearer token from localStorage and a 401
// triggers an automatic logout (handled by a registered callback).

const TOKEN_KEY = "auth_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

// The app registers a callback here so a 401 anywhere can force a logout.
let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

function authHeaders(extra = {}) {
  const token = getToken();
  return token ? { ...extra, Authorization: `Bearer ${token}` } : { ...extra };
}

// Core fetch wrapper: attaches auth header, parses JSON, handles 401.
async function apiFetch(url, { method = "GET", body, auth = true } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const finalHeaders = auth ? authHeaders(headers) : headers;

  const res = await fetch(url, {
    method,
    headers: finalHeaders,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && auth) {
    clearToken();
    if (onUnauthorized) onUnauthorized();
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data?.detail) detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }

  // Some endpoints (204) may have no body.
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

// ----------------------------- Auth --------------------------------------

export async function register({ email, password, name, preferred_language }) {
  return apiFetch("/api/auth/register", {
    method: "POST",
    auth: false,
    body: { email, password, name: name || null, preferred_language: preferred_language || null },
  });
}

export async function login({ email, password }) {
  return apiFetch("/api/auth/login", {
    method: "POST",
    auth: false,
    body: { email, password },
  });
}

export async function getMe() {
  return apiFetch("/api/auth/me");
}

// ----------------------------- Tutor -------------------------------------

export async function setGoal(sessionId, goal, language) {
  return apiFetch("/api/goal", {
    method: "POST",
    body: { session_id: sessionId, goal, language },
  });
}

export async function sendChat(sessionId, message) {
  return apiFetch("/api/chat", {
    method: "POST",
    body: { session_id: sessionId, message },
  });
}

export async function submitCode(sessionId, code) {
  return apiFetch("/api/submit_code", {
    method: "POST",
    body: { session_id: sessionId, code },
  });
}

export async function resume(sessionId, answer) {
  return apiFetch("/api/resume", {
    method: "POST",
    body: { session_id: sessionId, answer },
  });
}

export async function getProgress() {
  return apiFetch("/api/progress/me");
}

export async function getGraphSettings() {
  return apiFetch("/api/graph/settings", { auth: false });
}

export async function updateGraphSettings(values) {
  return apiFetch("/api/graph/settings", { method: "PUT", body: values, auth: false });
}

export async function getMetricsSummary() {
  return apiFetch("/api/metrics/summary", { auth: false });
}
