"""
Tests for the command resolution endpoint and service.

Resolution is tested both via the HTTP endpoint (integration) and directly against
the service function (unit).
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models import Command, CommandVariable
from src.services.command_resolver import resolve_command


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _make_command(**kwargs) -> Command:
    """Helper to build a minimal Command for unit tests."""
    from datetime import datetime, timezone

    defaults = dict(
        id="test-id",
        name="test-cmd",
        display_name="Test Cmd",
        description="desc",
        template="Hello {{name}}!",
        variables=[
            CommandVariable(name="name", type="string", required=True, description="a name")
        ],
        tools=[],
        tags=[],
        source="builtin",
        version=1,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return Command(**defaults)


# ---------------------------------------------------------------------------
# HTTP integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_triage_ticket_with_valid_args(client: AsyncClient):
    """GET /resolve?ticket_number=PROJ-1234 must return a ResolvedCommand."""
    response = await client.get(
        "/api/v1/commands/triage-ticket/resolve",
        params={"ticket_number": "PROJ-1234"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["command_name"] == "triage-ticket"
    assert "resolved_prompt" in data
    assert "PROJ-1234" in data["resolved_prompt"]
    assert "required_tools" in data
    assert "jira_get_ticket" in data["required_tools"]


@pytest.mark.asyncio
async def test_resolve_missing_required_variable_returns_error(client: AsyncClient):
    """GET /resolve without a required variable must return 422."""
    response = await client.get("/api/v1/commands/triage-ticket/resolve")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "MISSING_VARIABLE"
    assert detail["command_name"] == "triage-ticket"
    assert len(detail["required_variables"]) > 0


@pytest.mark.asyncio
async def test_resolve_list_my_tickets_no_args(client: AsyncClient):
    """list-my-tickets has no required variables; resolve must succeed with no params."""
    response = await client.get("/api/v1/commands/list-my-tickets/resolve")
    assert response.status_code == 200
    data = response.json()
    assert data["command_name"] == "list-my-tickets"
    assert "jira_list_tickets" in data["required_tools"]


@pytest.mark.asyncio
async def test_resolve_summarize_thread_with_url(client: AsyncClient):
    """summarize-thread must substitute {{thread_url}} in the resolved prompt."""
    url = "https://example.com/threads/42"
    response = await client.get(
        "/api/v1/commands/summarize-thread/resolve",
        params={"thread_url": url},
    )
    assert response.status_code == 200
    data = response.json()
    assert url in data["resolved_prompt"]
    assert data["required_tools"] == []


@pytest.mark.asyncio
async def test_resolve_nonexistent_command_returns_404(client: AsyncClient):
    """GET /api/v1/commands/ghost/resolve must return 404."""
    response = await client.get("/api/v1/commands/ghost/resolve")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Unit tests for the resolver service
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolved_prompt_contains_substituted_value():
    """The resolver must replace {{name}} with the supplied value."""
    command = _make_command(
        template="Hello {{name}}, your ticket is {{ticket}}!",
        variables=[
            CommandVariable(name="name", type="string", required=True, description="user name"),
            CommandVariable(name="ticket", type="string", required=True, description="ticket id"),
        ],
    )
    result = resolve_command(command, {"name": "Alice", "ticket": "ABC-99"}, {})

    from src.models import ResolvedCommand
    assert isinstance(result, ResolvedCommand)
    assert "Alice" in result.resolved_prompt
    assert "ABC-99" in result.resolved_prompt
    assert "{{name}}" not in result.resolved_prompt
    assert "{{ticket}}" not in result.resolved_prompt


@pytest.mark.asyncio
async def test_resolve_missing_required_variable_service_returns_error():
    """Resolver must return ResolutionError when a required variable is absent."""
    command = _make_command()  # requires "name"

    from src.models import ResolutionError
    result = resolve_command(command, {}, {})

    assert isinstance(result, ResolutionError)
    assert result.code == "MISSING_VARIABLE"
    assert any(v.name == "name" for v in result.required_variables)


@pytest.mark.asyncio
async def test_resolve_optional_variable_uses_default():
    """A variable with a default must not be required in arguments."""
    command = _make_command(
        template="Priority: {{priority}}",
        variables=[
            CommandVariable(
                name="priority",
                type="string",
                required=False,
                description="priority level",
                default="Medium",
            )
        ],
    )
    from src.models import ResolvedCommand
    result = resolve_command(command, {}, {})

    assert isinstance(result, ResolvedCommand)
    assert "Medium" in result.resolved_prompt


@pytest.mark.asyncio
async def test_resolve_metadata_contains_resolution_time():
    """The ResolvedCommand metadata must include resolution_time_ms."""
    command = _make_command(template="Static template with no vars.", variables=[])
    from src.models import ResolvedCommand
    result = resolve_command(command, {}, {"user": "bob", "env": "staging"})

    assert isinstance(result, ResolvedCommand)
    assert "resolution_time_ms" in result.metadata
    assert result.metadata["resolution_time_ms"] >= 0


@pytest.mark.asyncio
async def test_resolve_system_context_contains_user_and_env():
    """system_context must encode the user_context values."""
    command = _make_command(template="No vars.", variables=[])
    from src.models import ResolvedCommand
    result = resolve_command(command, {}, {"user": "carol", "env": "prod"})

    assert isinstance(result, ResolvedCommand)
    assert "carol" in result.system_context
    assert "prod" in result.system_context
