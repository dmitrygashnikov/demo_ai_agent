"""Seed the Skill Graph into PostgreSQL (idempotent)."""
from __future__ import annotations

import logging

from app.db.models import Skill
from app.db.session import get_session
from app.db.skill_graph import ALL_SKILLS

logger = logging.getLogger(__name__)


def seed_skills() -> int:
    """Insert/refresh all skills. Returns number of skills present."""
    with get_session() as session:
        for sd in ALL_SKILLS:
            existing = session.get(Skill, sd.id)
            if existing is None:
                session.add(
                    Skill(
                        id=sd.id,
                        name=sd.name,
                        language=sd.language,
                        base_difficulty=sd.base_difficulty,
                        order_index=sd.order_index,
                        prerequisites=",".join(sd.prerequisites),
                        concept=sd.concept,
                    )
                )
            else:
                existing.name = sd.name
                existing.language = sd.language
                existing.base_difficulty = sd.base_difficulty
                existing.order_index = sd.order_index
                existing.prerequisites = ",".join(sd.prerequisites)
                existing.concept = sd.concept
    logger.info("Seeded %d skills", len(ALL_SKILLS))
    return len(ALL_SKILLS)
