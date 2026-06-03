"""WebSocket endpoint for streaming tutor turns.

Protocol (JSON messages):
  client → {type: "chat"|"code"|"goal"|"resume", user_id, session_id, text/code/answer, language?}
  server → {type: "token", text}            (incremental, where applicable)
            {type: "interrupt", question}     (human-in-the-loop)
            {type: "final", response, state}  (turn complete)
            {type: "error", message}

For simplicity the graph runs synchronously per turn; the final answer is also
streamed token-by-token for a responsive UI.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.auth.deps import authenticate_token
from app.graph.runner import resume_turn, run_turn

logger = logging.getLogger(__name__)

ws_router = APIRouter()


@ws_router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    # Authenticate the socket. The token may come as a ?token=... query param or
    # as the first message {type: "auth", token: ...}. The resolved user id is
    # then used for EVERY turn — clients cannot spoof another user_id in the body.
    await websocket.accept()

    token = websocket.query_params.get("token")
    auth_user = authenticate_token(token) if token else None

    if auth_user is None:
        # Allow an initial auth message before closing.
        try:
            first = await websocket.receive_json()
        except Exception:  # noqa: BLE001
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if first.get("type") == "auth":
            auth_user = authenticate_token(first.get("token"))
        if auth_user is None:
            await websocket.send_json(
                {"type": "error", "message": "Unauthorized: invalid or missing token"}
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        else:
            await websocket.send_json({"type": "auth_ok"})

    authed_user_id = auth_user["id"]

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")
            if msg_type == "auth":
                # Re-auth / keepalive — already authenticated.
                continue
            # Always use the authenticated user id (ignore any body user_id).
            user_id = authed_user_id
            session_id = data.get("session_id", "default")

            if msg_type == "resume":
                result = await asyncio.to_thread(
                    resume_turn, session_id, data.get("answer", "")
                )
            elif msg_type == "code":
                result = await asyncio.to_thread(
                    run_turn, user_id, session_id, "", data.get("code", ""), None
                )
            elif msg_type == "goal":
                result = await asyncio.to_thread(
                    run_turn, user_id, session_id, data.get("text", ""),
                    None, data.get("language"),
                )
            else:  # chat
                result = await asyncio.to_thread(
                    run_turn, user_id, session_id, data.get("text", "")
                )

            if result.get("interrupted"):
                await websocket.send_json(
                    {"type": "interrupt", "question": result.get("question", "")}
                )
                continue

            response = result.get("response", "")
            # Stream the final answer token-ish by words for a live feel.
            for word in response.split(" "):
                await websocket.send_json({"type": "token", "text": word + " "})
                await asyncio.sleep(0.005)

            await websocket.send_json(
                {"type": "final", "response": response, "state": result.get("state", {})}
            )
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as exc:  # noqa: BLE001
        logger.exception("WebSocket error")
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
