"""
Tests for the skills endpoints and the skill loader service.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.skill_loader import parse_skill_md


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# HTTP integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_skills_returns_seeded_skills(client: AsyncClient):
    """GET /api/v1/skills/ must return the 2 built-in skills."""
    response = await client.get("/api/v1/skills/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2

    names = {s["name"] for s in data}
    assert "code-review" in names
    assert "incident-response" in names


@pytest.mark.asyncio
async def test_get_skill_returns_skill_md_content(client: AsyncClient):
    """GET /api/v1/skills/{name} must include the raw SKILL.md body."""
    response = await client.get("/api/v1/skills/code-review")
    assert response.status_code == 200
    data = response.json()

    assert data["name"] == "code-review"
    assert "skill_md" in data
    # The markdown body should contain the section heading.
    assert "# Code Review Skill" in data["skill_md"]


@pytest.mark.asyncio
async def test_skill_frontmatter_parsed_correctly(client: AsyncClient):
    """The frontmatter dict must contain the keys declared in SKILL.md."""
    response = await client.get("/api/v1/skills/incident-response")
    assert response.status_code == 200
    data = response.json()

    fm = data["frontmatter"]
    assert fm["name"] == "incident-response"
    assert "jira_get_ticket" in fm["tools"]
    assert "jira_update_ticket" in fm["tools"]
    assert "operations" in fm["tags"]
    assert "on-call" in fm["tags"]

    # These must also be promoted to top-level fields.
    assert "jira_get_ticket" in data["tools"]
    assert "operations" in data["tags"]


@pytest.mark.asyncio
async def test_get_nonexistent_skill_returns_404(client: AsyncClient):
    """GET /api/v1/skills/{name} with an unknown name must return 404."""
    response = await client.get("/api/v1/skills/does-not-exist-xyz")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Unit tests for the skill loader / parser
# ---------------------------------------------------------------------------

_SAMPLE_SKILL_MD = """\
---
name: sample-skill
description: A sample skill for testing
tools:
  - tool_a
  - tool_b
tags:
  - testing
  - sample
---

# Sample Skill

Do something useful here.
"""


@pytest.mark.asyncio
async def test_parse_skill_md_extracts_frontmatter():
    """parse_skill_md must correctly split YAML frontmatter from the markdown body."""
    skill = parse_skill_md(_SAMPLE_SKILL_MD, name="sample-skill")

    assert skill.name == "sample-skill"
    assert skill.description == "A sample skill for testing"
    assert skill.frontmatter["name"] == "sample-skill"
    assert "tool_a" in skill.tools
    assert "tool_b" in skill.tools
    assert "testing" in skill.tags


@pytest.mark.asyncio
async def test_parse_skill_md_body_does_not_contain_frontmatter():
    """The skill_md field must contain only the markdown body, not the YAML block."""
    skill = parse_skill_md(_SAMPLE_SKILL_MD, name="sample-skill")

    assert "# Sample Skill" in skill.skill_md
    # YAML delimiters and frontmatter keys must not appear in the body.
    assert "description: A sample skill" not in skill.skill_md


@pytest.mark.asyncio
async def test_parse_skill_md_no_frontmatter():
    """parse_skill_md must not crash when there is no YAML frontmatter block."""
    content = "# Just Markdown\n\nNo frontmatter here.\n"
    skill = parse_skill_md(content, name="bare-skill")

    assert skill.name == "bare-skill"
    assert skill.frontmatter == {}
    assert "# Just Markdown" in skill.skill_md


@pytest.mark.asyncio
async def test_parse_skill_md_assigns_uuid():
    """Each parsed skill must receive a unique UUID id."""
    skill1 = parse_skill_md(_SAMPLE_SKILL_MD, name="s1")
    skill2 = parse_skill_md(_SAMPLE_SKILL_MD, name="s2")

    assert skill1.id != skill2.id
    # Basic UUID format check.
    assert len(skill1.id) == 36
    assert skill1.id.count("-") == 4
