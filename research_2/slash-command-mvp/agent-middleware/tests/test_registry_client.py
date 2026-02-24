"""
Tests for the Prompt Registry HTTP client.

Uses `respx` to mock the httpx transport layer so no real HTTP connections
are made during testing.

# DECISION: respx for HTTP mocking instead of responses or unittest.mock.
# Why: respx integrates directly with httpx (the library we use) at the transport
#   level, giving accurate request matching and response simulation without
#   monkey-patching. It supports async contexts natively.
# Standard: pytest-asyncio for async test functions.
# Alternative: Considered VCR.py (cassette-based) -- adds cassette management
#   overhead; overkill for a small number of well-defined API calls.
"""

import pytest
import respx
from httpx import Response

from src.registry_client import RegistryClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """Provide a started RegistryClient pointing at a fake base URL."""
    rc = RegistryClient(base_url="http://test-registry")
    await rc.start()
    yield rc
    await rc.stop()


# ---------------------------------------------------------------------------
# list_commands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_commands_returns_list(client):
    """list_commands() deserialises the JSON array from the registry."""
    mock_commands = [
        {
            "id": "uuid-1",
            "name": "triage-ticket",
            "display_name": "Triage Ticket",
            "description": "Triage a Jira ticket",
            "template": "Triage ticket $ticket_number",
            "variables": [{"name": "ticket_number", "required": True, "type": "string", "description": "Ticket ID"}],
            "tools": ["jira_get_ticket"],
            "tags": ["jira"],
            "source": "builtin",
            "version": 1,
            "is_active": True,
            "created_at": "2026-02-01T00:00:00Z",
            "updated_at": "2026-02-01T00:00:00Z",
        }
    ]

    with respx.mock(base_url="http://test-registry") as mock:
        mock.get("/api/v1/commands").mock(
            return_value=Response(200, json=mock_commands)
        )
        result = await client.list_commands()

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["name"] == "triage-ticket"


@pytest.mark.asyncio
async def test_list_commands_with_search_param(client):
    """list_commands() passes the search query parameter to the registry."""
    with respx.mock(base_url="http://test-registry") as mock:
        route = mock.get("/api/v1/commands").mock(return_value=Response(200, json=[]))
        await client.list_commands(search="triage")

    # Verify the search param was included in the request.
    assert route.called
    request = route.calls[0].request
    assert "search=triage" in str(request.url)


@pytest.mark.asyncio
async def test_list_commands_no_search_param_when_none(client):
    """list_commands() omits the search param when search=None."""
    with respx.mock(base_url="http://test-registry") as mock:
        route = mock.get("/api/v1/commands").mock(return_value=Response(200, json=[]))
        await client.list_commands()

    request = route.calls[0].request
    assert "search" not in str(request.url)


@pytest.mark.asyncio
async def test_list_commands_empty_registry(client):
    """list_commands() returns an empty list when the registry has no commands."""
    with respx.mock(base_url="http://test-registry") as mock:
        mock.get("/api/v1/commands").mock(return_value=Response(200, json=[]))
        result = await client.list_commands()

    assert result == []


# ---------------------------------------------------------------------------
# resolve_command — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_command_success(client):
    """resolve_command() returns the resolved payload on HTTP 200."""
    mock_resolved = {
        "command_name": "triage-ticket",
        "resolved_prompt": "Please triage ticket PROJ-1234 ...",
        "system_context": "You are a triage assistant.",
        "required_tools": ["jira_get_ticket"],
        "original_command": "Triage ticket $ticket_number",
        "metadata": {},
    }

    with respx.mock(base_url="http://test-registry") as mock:
        mock.get("/api/v1/commands/triage-ticket/resolve").mock(
            return_value=Response(200, json=mock_resolved)
        )
        result = await client.resolve_command(
            name="triage-ticket",
            arguments={"ticket_number": "PROJ-1234"},
        )

    assert "error" not in result
    assert result["command_name"] == "triage-ticket"
    assert result["resolved_prompt"] == "Please triage ticket PROJ-1234 ..."


@pytest.mark.asyncio
async def test_resolve_command_passes_arguments_as_query_params(client):
    """resolve_command() includes arguments as query parameters."""
    with respx.mock(base_url="http://test-registry") as mock:
        route = mock.get("/api/v1/commands/triage-ticket/resolve").mock(
            return_value=Response(200, json={"resolved_prompt": "ok", "command_name": "triage-ticket",
                                             "system_context": "", "required_tools": [],
                                             "original_command": "", "metadata": {}})
        )
        await client.resolve_command(
            name="triage-ticket",
            arguments={"ticket_number": "PROJ-9999"},
        )

    request = route.calls[0].request
    assert "ticket_number=PROJ-9999" in str(request.url)


@pytest.mark.asyncio
async def test_resolve_command_injects_user_context(client):
    """resolve_command() appends _user and _env when user_context is provided."""
    with respx.mock(base_url="http://test-registry") as mock:
        route = mock.get("/api/v1/commands/triage-ticket/resolve").mock(
            return_value=Response(200, json={"resolved_prompt": "ok", "command_name": "triage-ticket",
                                             "system_context": "", "required_tools": [],
                                             "original_command": "", "metadata": {}})
        )
        await client.resolve_command(
            name="triage-ticket",
            arguments={"ticket_number": "PROJ-1234"},
            user_context={"user": "alice@company.com", "env": "staging"},
        )

    request = route.calls[0].request
    url_str = str(request.url)
    assert "_user=alice%40company.com" in url_str or "_user=alice@company.com" in url_str
    assert "_env=staging" in url_str


# ---------------------------------------------------------------------------
# resolve_command — error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_command_returns_error_on_404(client):
    """resolve_command() returns a COMMAND_NOT_FOUND error dict on HTTP 404."""
    with respx.mock(base_url="http://test-registry") as mock:
        mock.get("/api/v1/commands/nonexistent/resolve").mock(
            return_value=Response(404, json={"detail": "Not found"})
        )
        result = await client.resolve_command(
            name="nonexistent",
            arguments={},
        )

    assert "error" in result
    error = result["error"]
    assert error["code"] == "COMMAND_NOT_FOUND"
    assert "nonexistent" in error["message"]


@pytest.mark.asyncio
async def test_resolve_command_returns_error_body_on_422(client):
    """resolve_command() returns the registry's error body on HTTP 422."""
    error_body = {
        "code": "MISSING_VARIABLE",
        "message": "Missing required variable: ticket_number",
        "command_name": "triage-ticket",
        "required_variables": [
            {"name": "ticket_number", "required": True, "type": "string", "description": "Ticket ID"}
        ],
    }

    with respx.mock(base_url="http://test-registry") as mock:
        mock.get("/api/v1/commands/triage-ticket/resolve").mock(
            return_value=Response(422, json=error_body)
        )
        result = await client.resolve_command(
            name="triage-ticket",
            arguments={},  # Missing ticket_number
        )

    assert "error" in result
    assert result["error"]["code"] == "MISSING_VARIABLE"
    assert result["error"]["required_variables"][0]["name"] == "ticket_number"


# ---------------------------------------------------------------------------
# get_skill
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_skill_found(client):
    """get_skill() returns the skill dict when found."""
    mock_skill = {
        "id": "uuid-skill-1",
        "name": "code-review",
        "description": "Assists with code reviews",
        "skill_md": "# Code Review\n\nHelp review code.",
        "frontmatter": {"name": "code-review"},
        "tools": ["git_list_commits"],
        "tags": ["git"],
        "source": "builtin",
        "is_active": True,
        "created_at": "2026-02-01T00:00:00Z",
        "updated_at": "2026-02-01T00:00:00Z",
    }

    with respx.mock(base_url="http://test-registry") as mock:
        mock.get("/api/v1/skills/code-review").mock(
            return_value=Response(200, json=mock_skill)
        )
        result = await client.get_skill("code-review")

    assert result is not None
    assert result["name"] == "code-review"
    assert "skill_md" in result


@pytest.mark.asyncio
async def test_get_skill_not_found_returns_none(client):
    """get_skill() returns None when the skill does not exist (HTTP 404)."""
    with respx.mock(base_url="http://test-registry") as mock:
        mock.get("/api/v1/skills/nonexistent-skill").mock(
            return_value=Response(404, json={"detail": "Not found"})
        )
        result = await client.get_skill("nonexistent-skill")

    assert result is None


# ---------------------------------------------------------------------------
# list_skills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_skills_returns_list(client):
    """list_skills() returns the list of skill metadata dicts."""
    mock_skills = [
        {
            "id": "uuid-skill-1",
            "name": "code-review",
            "description": "Assists with code reviews",
            "skill_md": "# Code Review",
            "frontmatter": {},
            "tools": [],
            "tags": [],
            "source": "builtin",
            "is_active": True,
            "created_at": "2026-02-01T00:00:00Z",
            "updated_at": "2026-02-01T00:00:00Z",
        },
        {
            "id": "uuid-skill-2",
            "name": "incident-response",
            "description": "Incident response runbook",
            "skill_md": "# Incident Response",
            "frontmatter": {},
            "tools": [],
            "tags": [],
            "source": "builtin",
            "is_active": True,
            "created_at": "2026-02-01T00:00:00Z",
            "updated_at": "2026-02-01T00:00:00Z",
        },
    ]

    with respx.mock(base_url="http://test-registry") as mock:
        mock.get("/api/v1/skills").mock(return_value=Response(200, json=mock_skills))
        result = await client.list_skills()

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["name"] == "code-review"
    assert result[1]["name"] == "incident-response"


@pytest.mark.asyncio
async def test_list_skills_empty(client):
    """list_skills() returns an empty list when no skills exist."""
    with respx.mock(base_url="http://test-registry") as mock:
        mock.get("/api/v1/skills").mock(return_value=Response(200, json=[]))
        result = await client.list_skills()

    assert result == []
