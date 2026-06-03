"""REST API endpoints: goal, chat, submit_code, progress, uniqueness audit."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.db.models import SkillProgress
from app.db.progress_repo import get_or_create_user, get_solve_count
from app.db.session import get_session
from app.db.skill_graph import skills_for_language
from app.graph.runner import resume_turn, run_turn
from app.settings_store import get_runtime_settings, update_runtime_settings
from app.tasks.uniqueness import violates_cooldown

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class GoalRequest(BaseModel):
    user_id: str
    session_id: str
    goal: str
    language: str | None = None


class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


class CodeRequest(BaseModel):
    user_id: str
    session_id: str
    code: str


class ResumeRequest(BaseModel):
    session_id: str
    answer: str


class GraphSettingsUpdate(BaseModel):
    """All fields optional — only provided ones are updated."""

    COOLDOWN_SOLVES: int | None = None
    MAX_REGEN_ATTEMPTS: int | None = None
    MASTERY_SUCCESS_STREAK: int | None = None
    ADVANCED_SUCCESS_STREAK: int | None = None


@router.post("/goal")
def set_goal(req: GoalRequest):
    get_or_create_user(req.user_id, req.language)
    return run_turn(
        req.user_id, req.session_id, req.goal, language=req.language
    )


@router.post("/chat")
def chat_endpoint(req: ChatRequest):
    return run_turn(req.user_id, req.session_id, req.message)


@router.post("/submit_code")
def submit_code(req: CodeRequest):
    return run_turn(
        req.user_id, req.session_id, user_message="", submitted_code=req.code
    )


@router.post("/resume")
def resume(req: ResumeRequest):
    return resume_turn(req.session_id, req.answer)


@router.get("/progress/{user_id}")
def progress(user_id: str):
    with get_session() as session:
        rows = session.execute(
            select(SkillProgress).where(SkillProgress.user_id == user_id)
        ).scalars().all()
        items = [
            {
                "skill_id": r.skill_id,
                "state": r.state,
                "mastery": r.mastery,
                "attempts": r.attempts,
                "consecutive_successes": r.consecutive_successes,
            }
            for r in rows
        ]
    return {"user_id": user_id, "solve_count": get_solve_count(user_id), "skills": items}


@router.get("/skills/{language}")
def skills(language: str):
    return {
        "language": language,
        "skills": [
            {"id": s.id, "name": s.name, "concept": s.concept, "order": s.order_index}
            for s in skills_for_language(language)
        ],
    }


@router.get("/graph/settings")
def get_graph_settings():
    """Return the current runtime-editable adaptive graph parameters."""
    return get_runtime_settings()


@router.put("/graph/settings")
def put_graph_settings(req: GraphSettingsUpdate):
    """Update runtime graph parameters (applied without a restart).

    Validates positive integers within sane bounds and returns the updated set.
    """
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No settings provided")
    try:
        return update_runtime_settings(updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/uniqueness/audit")
def uniqueness_audit(user_id: str, task_id: str):
    """Audit endpoint for req. 5: check whether re-serving would violate cooldown."""
    sc = get_solve_count(user_id)
    return {
        "user_id": user_id,
        "task_id": task_id,
        "solve_count": sc,
        "would_violate_cooldown": violates_cooldown(user_id, task_id, sc),
    }
