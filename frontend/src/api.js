// Backend client for the Adaptive AI Coding Tutor.
// REST calls go through the nginx /api proxy; WebSocket via /ws.

const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export async function setGoal(userId, sessionId, goal, language) {
  const r = await fetch(
    "/api/goal",
    json("POST", { user_id: userId, session_id: sessionId, goal, language })
  );
  return r.json();
}

export async function sendChat(userId, sessionId, message) {
  const r = await fetch(
    "/api/chat",
    json("POST", { user_id: userId, session_id: sessionId, message })
  );
  return r.json();
}

export async function submitCode(userId, sessionId, code) {
  const r = await fetch(
    "/api/submit_code",
    json("POST", { user_id: userId, session_id: sessionId, code })
  );
  return r.json();
}

export async function resume(sessionId, answer) {
  const r = await fetch("/api/resume", json("POST", { session_id: sessionId, answer }));
  return r.json();
}

export async function getProgress(userId) {
  const r = await fetch(`/api/progress/${userId}`);
  return r.json();
}
