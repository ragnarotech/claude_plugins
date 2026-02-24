"""
Filesystem skill loader for the Prompt Registry service.

# DECISION: Skills loaded from filesystem at startup rather than from a database-only store.
# Why: Skills are developer artefacts (markdown files); keeping them in the repo means
#     they are version-controlled, code-reviewed, and diff-able like any other source file.
# Production: Add a hot-reload watcher (watchfiles) so skills update without a restart.
#             Also support uploading skills via the API to a /user-skills directory.
# Standard: Convention-over-configuration -- each subdirectory of SKILLS_DIR with a
#           SKILL.md file is auto-discovered.
# Alternative: Rejected a database-only store for skill content -- editing skills would
#              require an API call or direct DB surgery rather than a simple text editor.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.database import get_db
from src.models import Skill

logger = logging.getLogger(__name__)


def parse_skill_md(content: str, name: str) -> Skill:
    """Parse a SKILL.md file into a Skill model.

    The file format is::

        ---
        <YAML frontmatter>
        ---

        <Markdown body>

    The first pair of ``---`` delimiters delimits the YAML block.  Everything
    after the closing ``---`` is treated as the markdown body (skill_md).

    # DECISION: Manual frontmatter split rather than a library like python-frontmatter.
    # Why: Avoids an extra dependency; the format is simple and stable.
    # Production: Switch to python-frontmatter if we add more complex YAML features.
    # Alternative: Rejected regex-based parsing -- brittle against edge-cases like
    #              ``---`` appearing inside a code block in the markdown body.
    """
    lines = content.splitlines(keepends=True)

    frontmatter_dict: dict = {}
    skill_md = content

    if lines and lines[0].strip() == "---":
        # Find the closing delimiter
        close_idx: int | None = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                close_idx = i
                break

        if close_idx is not None:
            yaml_block = "".join(lines[1:close_idx])
            skill_md = "".join(lines[close_idx + 1 :])
            try:
                frontmatter_dict = yaml.safe_load(yaml_block) or {}
            except yaml.YAMLError as exc:
                logger.warning("Failed to parse YAML frontmatter for skill %s: %s", name, exc)
                frontmatter_dict = {}

    now = datetime.now(timezone.utc).isoformat()

    # Extract tools and tags from frontmatter for DB-level filtering.
    tools: list[str] = frontmatter_dict.get("tools", [])
    tags: list[str] = frontmatter_dict.get("tags", [])
    description: str = frontmatter_dict.get("description", "")

    return Skill(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
        skill_md=skill_md.strip(),
        frontmatter=frontmatter_dict,
        tools=tools,
        tags=tags,
        source="builtin",
        is_active=True,
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
    )


def load_skills_from_disk(skills_dir: str) -> list[Skill]:
    """Discover and parse all SKILL.md files under *skills_dir*.

    Each immediate subdirectory of *skills_dir* that contains a ``SKILL.md``
    file is treated as one skill.  The directory name becomes the skill name
    if the frontmatter does not specify one.

    # DECISION: Directory name as fallback skill name.
    # Why: Makes it trivial to add a new skill by creating a directory.
    # Production: Validate skill names against a regex to prevent injection.
    """
    skills: list[Skill] = []
    base = Path(skills_dir)

    if not base.exists():
        logger.warning("Skills directory %s does not exist; no skills loaded.", skills_dir)
        return skills

    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        skill_file = entry / "SKILL.md"
        if not skill_file.exists():
            continue

        try:
            content = skill_file.read_text(encoding="utf-8")
            # Use the frontmatter name if present, otherwise the directory name.
            skill = parse_skill_md(content, name=entry.name)
            # Prefer the name declared in frontmatter.
            if skill.frontmatter.get("name"):
                skill = skill.model_copy(update={"name": skill.frontmatter["name"]})
            skills.append(skill)
            logger.debug("Loaded skill: %s", skill.name)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load skill from %s: %s", skill_file, exc)

    logger.info("Loaded %d skill(s) from %s", len(skills), skills_dir)
    return skills


async def seed_skills(skills: list[Skill]) -> None:
    """Insert skills into the database if they do not already exist (idempotent).

    # DECISION: ON CONFLICT(name) DO NOTHING for idempotent upserts.
    # Why: Skills on disk are the source of truth; we never overwrite user edits made
    #      via the API.
    # Production: Add a source column check -- only overwrite rows where source='builtin'.
    """
    async with get_db() as db:
        for skill in skills:
            await db.execute(
                """
                INSERT INTO skills
                    (id, name, description, skill_md, frontmatter,
                     tools, tags, source, is_active, created_at, updated_at)
                VALUES
                    (:id, :name, :description, :skill_md, :frontmatter,
                     :tools, :tags, :source, :is_active, :created_at, :updated_at)
                ON CONFLICT(name) DO NOTHING
                """,
                {
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description,
                    "skill_md": skill.skill_md,
                    "frontmatter": json.dumps(skill.frontmatter),
                    "tools": json.dumps(skill.tools),
                    "tags": json.dumps(skill.tags),
                    "source": skill.source,
                    "is_active": skill.is_active,
                    "created_at": skill.created_at.isoformat(),
                    "updated_at": skill.updated_at.isoformat(),
                },
            )
        await db.commit()
    logger.info("Seeded %d skill(s) into the database.", len(skills))
