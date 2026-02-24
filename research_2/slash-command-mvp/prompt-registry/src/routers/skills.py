"""
FastAPI router for skill retrieval.

# DECISION: Read-only skill endpoints for MVP.
# Why: Skills are loaded from filesystem; there is no user story for creating skills
#      via the API yet. The filesystem workflow (edit SKILL.md -> restart) is sufficient.
# Production: Add POST /skills and PUT /skills/{name} for user-authored skills, guarded
#             by admin JWT. Store uploaded skills under a /user-skills directory.
# Standard: REST resource naming -- /api/v1/skills/{name}.
# Alternative: Rejected /api/v1/skill (singular) -- REST convention uses plural resources.
"""

import logging

from fastapi import APIRouter, HTTPException

from src.database import get_db, row_to_dict
from src.models import Skill

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


def _row_to_skill(row_dict: dict) -> Skill:
    """Coerce a DB row dict (JSON columns already decoded) into a Skill model."""
    return Skill(**row_dict)


@router.get("/", response_model=list[Skill])
async def list_skills():
    """Return all active skills.

    # DECISION: No search/filter params on MVP skill list.
    # Why: Only 2 built-in skills at launch; filtering adds complexity with no user benefit.
    # Production: Add search and tag filter query params (same pattern as /commands).
    # INTEGRATION: agent-middleware fetches this list at startup to build the system prompt.
    """
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM skills WHERE is_active = TRUE ORDER BY name"
        )

    return [_row_to_skill(row_to_dict(r)) for r in rows]


@router.get("/{name}", response_model=Skill)
async def get_skill(name: str):
    """Return a single skill including the full raw SKILL.md content.

    # INTEGRATION: The agent-middleware injects skill_md verbatim into Claude's system
    #              prompt. Do not strip or reformat the markdown body.
    """
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM skills WHERE name = ? AND is_active = TRUE", (name,)
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    return _row_to_skill(row_to_dict(row))
