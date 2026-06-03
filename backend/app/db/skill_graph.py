"""Skill Graph definition and helpers.

The skill graph is a dependency DAG of atomic skills. Skills carry a ``concept``
key that is shared across languages so that mastery can be reused when a student
switches language (e.g. ``loops`` mastered in Python counts towards JS loops).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SkillDef:
    id: str
    name: str
    language: str
    concept: str
    base_difficulty: int
    order_index: int
    prerequisites: list[str] = field(default_factory=list)


# Ordered learning trajectory. Concepts are shared between languages.
_CONCEPTS = [
    ("variables", "Variables & types", 1),
    ("io", "Input / output", 1),
    ("conditions", "Conditions & branching", 1),
    ("loops", "Loops", 2),
    ("functions", "Functions", 2),
    ("collections", "Lists & collections", 2),
    ("dicts", "Dictionaries / objects", 3),
    ("strings", "String processing", 2),
    ("errors", "Error handling", 3),
    ("oop", "Object-oriented programming", 4),
    ("comprehensions", "Comprehensions / functional", 3),
    ("recursion", "Recursion", 4),
    ("modules", "Modules & imports", 2),
    ("api", "Working with APIs", 4),
    ("project", "Mini project", 5),
]


def _build_language(language: str, prefix: str) -> list[SkillDef]:
    skills: list[SkillDef] = []
    prev_id: str | None = None
    for idx, (concept, name, diff) in enumerate(_CONCEPTS):
        sid = f"{prefix}_{concept}"
        prereqs = [prev_id] if prev_id else []
        skills.append(
            SkillDef(
                id=sid,
                name=f"{name} ({language})",
                language=language,
                concept=concept,
                base_difficulty=diff,
                order_index=idx,
                prerequisites=prereqs,
            )
        )
        prev_id = sid
    return skills


PYTHON_SKILLS = _build_language("python", "py")
JS_SKILLS = _build_language("javascript", "js")
ALL_SKILLS: list[SkillDef] = PYTHON_SKILLS + JS_SKILLS


def skills_for_language(language: str) -> list[SkillDef]:
    return [s for s in ALL_SKILLS if s.language == language]


def first_skill(language: str) -> SkillDef:
    return skills_for_language(language)[0]


def next_skill(skill_id: str) -> SkillDef | None:
    """Return the next skill in the same language's trajectory, or None."""
    by_id = {s.id: s for s in ALL_SKILLS}
    current = by_id.get(skill_id)
    if not current:
        return None
    same_lang = sorted(
        skills_for_language(current.language), key=lambda s: s.order_index
    )
    for i, s in enumerate(same_lang):
        if s.id == skill_id and i + 1 < len(same_lang):
            return same_lang[i + 1]
    return None


def concept_of(skill_id: str) -> str | None:
    for s in ALL_SKILLS:
        if s.id == skill_id:
            return s.concept
    return None
