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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.graph.runner import resume_turn, run_turn

logger = logging.getLogger(__name__)

ws_router = APIRouter()


@ws_router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")
            user_id = data.get("user_id", "anon")
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
