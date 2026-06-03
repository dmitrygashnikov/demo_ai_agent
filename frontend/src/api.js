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

export async function submitCode(sessionId, code, taskId) {
  return apiFetch("/api/submit_code", {
    method: "POST",
    // Include the current task id when known so the backend can recover the
    // active task even if its checkpointed session state was lost.
    body: { session_id: sessionId, code, task_id: taskId || null },
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

// ----------------------------- Topic / theme -----------------------------
// Free-form THEME ("тематика") that biases generated tasks + web-search
// queries. Orthogonal to language/skill — switching it never resets progress.

// Suggested themes for the dropdown (public, fail-open: returns [] on error).
export async function getTopics() {
  try {
    const data = await apiFetch("/api/topics", { auth: false });
    return data?.topics || [];
  } catch {
    return [];
  }
}

// Current user's persisted theme → { topic: string | null }.
export async function getTopic() {
  return apiFetch("/api/topic");
}

// Set/clear the theme (empty string clears it) → { topic: string | null }.
export async function setTopic(topic) {
  return apiFetch("/api/topic", {
    method: "PUT",
    body: { topic: topic || "" },
  });
}

// ----------------------------- Sections / themes -------------------------
// Human-readable learning sections shown in the sidebar (req #6). Selecting a
// section sets the topic AND serves a fresh themed task (mirrors /api/chat);
// the "?" intro flow returns intro articles/videos for the section.

// Available learning languages → [{ id, label }]. Public (static list).
// Fail-open: returns the MVP set on any error so the dropdown always renders.
export async function getLanguages() {
  try {
    const data = await apiFetch("/api/languages", { auth: false });
    return data?.languages || [];
  } catch {
    return [
      { id: "python", label: "Python" },
      { id: "javascript", label: "JavaScript" },
    ];
  }
}

// List sections for a language (global seeded + the current user's own) →
// { language, current_section_id, sections: [...] }.
export async function getSections(language) {
  return apiFetch(`/api/sections?language=${encodeURIComponent(language)}`);
}

// Create a user-owned section → the created section object.
// Throws (Error.message carries backend detail) on 400 (empty/oversized
// title; 120-char limit) and 409 (duplicate) so the UI can show inline errors.
export async function createSection(payload) {
  return apiFetch("/api/sections", {
    method: "POST",
    body: payload,
  });
}

// Select the current section → mirrors /api/chat:
// { interrupted, response, state } where state.current_task_id is the NEW
// themed task, state.cancelled_task_id is the discarded task, state.topic is
// the new theme and state.current_section_id is the selected section.
export async function selectSection(sessionId, sectionId) {
  return apiFetch("/api/sections/select", {
    method: "POST",
    body: { session_id: sessionId, section_id: sectionId },
  });
}

// Intro material for a section ("?" pictogram) →
// { response, links: [{ title, url, snippet, kind: "article"|"video" }], section_id }.
export async function getSectionIntro(sectionId, { sessionId, language } = {}) {
  return apiFetch(`/api/sections/${encodeURIComponent(sectionId)}/intro`, {
    method: "POST",
    body: { session_id: sessionId || null, language: language || null },
  });
}
