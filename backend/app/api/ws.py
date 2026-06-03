"""WebSocket endpoint for streaming tutor turns.

Protocol (JSON messages):
  client → {type: "chat"|"code"|"goal"|"resume", user_id, session_id, text/code/answer, language?, topic?}
            {type: "topic", topic}            (convenience: persist the theme only)
            {type: "select_section", section_id, session_id}  (spec §3.6 parity)
            {type: "section_intro", section_id, language?}     (spec §3.6 parity)
  server → {type: "token", text}            (incremental, where applicable)
            {type: "interrupt", question}     (human-in-the-loop)
            {type: "final", response, state}  (turn complete)
            {type: "topic_ok", topic}         (theme persisted)
            {type: "intro", response, links}  ("?" intro material)
            {type: "error", message}

The optional ``topic`` (free-form theme, Group E) may ride along on any
goal/chat/code message; it is threaded into ``run_turn`` so generated tasks +
web-search queries are themed. When omitted, ``run_turn`` falls back to the
user's persisted ``User.topic``, so the theme survives across turns.

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
            # Optional free-form theme (Group E). May ride along on any turn;
            # ``None`` lets run_turn fall back to the persisted User.topic.
            topic = data.get("topic")

            if msg_type == "topic":
                # Convenience: persist the theme without running a turn.
                try:
                    from app.db.progress_repo import set_user_topic

                    stored = await asyncio.to_thread(
                        set_user_topic, user_id, data.get("topic")
                    )
                    await websocket.send_json({"type": "topic_ok", "topic": stored})
                except Exception as exc:  # noqa: BLE001
                    await websocket.send_json({"type": "error", "message": str(exc)})
                continue

            if msg_type == "select_section":
                # Spec §3.6 parity: delegate to the SAME service function the
                # REST endpoint uses, then reply with the standard streamed
                # token + final turn (theme-set line + new themed task). REST is
                # the source of truth; this only mirrors it for WS-only clients.
                try:
                    from app.api.sections import select_section_turn

                    result = await asyncio.to_thread(
                        select_section_turn,
                        user_id,
                        session_id,
                        data.get("section_id", ""),
                    )
                except Exception as exc:  # noqa: BLE001
                    await websocket.send_json({"type": "error", "message": str(exc)})
                    continue
                # Falls through to the shared interrupt/stream/final handling below.

            elif msg_type == "section_intro":
                # Spec §3.6 parity: the "?" intro material. Replies with a
                # dedicated {type:"intro", response, links} message (informational
                # turn — no graph run, no task/skill change).
                try:
                    from app.api.sections import section_intro as _section_intro

                    intro = await asyncio.to_thread(
                        _section_intro,
                        user_id,
                        data.get("section_id", ""),
                        data.get("language"),
                    )
                    await websocket.send_json(
                        {
                            "type": "intro",
                            "response": intro.get("response", ""),
                            "links": intro.get("links", []),
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    await websocket.send_json({"type": "error", "message": str(exc)})
                continue

            elif msg_type == "resume":
                result = await asyncio.to_thread(
                    resume_turn, session_id, data.get("answer", "")
                )
            elif msg_type == "code":
                result = await asyncio.to_thread(
                    run_turn, user_id, session_id, "", data.get("code", ""),
                    None, None, topic,
                )
            elif msg_type == "goal":
                result = await asyncio.to_thread(
                    run_turn, user_id, session_id, data.get("text", ""),
                    None, data.get("language"), None, topic,
                )
            else:  # chat
                result = await asyncio.to_thread(
                    run_turn, user_id, session_id, data.get("text", ""),
                    None, None, None, topic,
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
