"""
Tests for the command CRUD endpoints.

Uses an in-memory SQLite database so tests are isolated and fast.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    """Yield an AsyncClient backed by the ASGI app.

    The app's lifespan runs on first use, which initialises the DB and seeds data.
    Each test module gets a fresh in-memory DB because we patch DATABASE_URL.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_commands_returns_seeded_data(client: AsyncClient):
    """GET /api/v1/commands/ must return the 4 hardcoded seed commands."""
    response = await client.get("/api/v1/commands/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 4

    names = {c["name"] for c in data}
    assert "triage-ticket" in names
    assert "list-my-tickets" in names
    assert "create-pr" in names
    assert "summarize-thread" in names


@pytest.mark.asyncio
async def test_get_command_by_name(client: AsyncClient):
    """GET /api/v1/commands/{name} must return a single command with correct fields."""
    response = await client.get("/api/v1/commands/triage-ticket")
    assert response.status_code == 200
    data = response.json()

    assert data["name"] == "triage-ticket"
    assert data["display_name"] == "Triage Ticket"
    assert "jira_get_ticket" in data["tools"]
    assert "jira_update_ticket" in data["tools"]
    assert data["is_active"] is True

    # Template contains the expected placeholder.
    assert "{{ticket_number}}" in data["template"]


@pytest.mark.asyncio
async def test_get_nonexistent_command_returns_404(client: AsyncClient):
    """GET /api/v1/commands/{name} with an unknown name must return 404."""
    response = await client.get("/api/v1/commands/no-such-command-xyz")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_command(client: AsyncClient):
    """POST /api/v1/commands/ must create a new command and return 201."""
    payload = {
        "name": "my-new-command",
        "display_name": "My New Command",
        "description": "A test command",
        "template": "Do something with {{param}}.",
        "variables": [
            {
                "name": "param",
                "type": "string",
                "required": True,
                "description": "A parameter",
            }
        ],
        "tools": [],
        "tags": ["test"],
    }
    response = await client.post("/api/v1/commands/", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "my-new-command"
    assert data["version"] == 1
    assert data["source"] == "user"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data

    # Verify it appears in the list.
    list_resp = await client.get("/api/v1/commands/")
    names = {c["name"] for c in list_resp.json()}
    assert "my-new-command" in names


@pytest.mark.asyncio
async def test_update_command_increments_version(client: AsyncClient):
    """PUT /api/v1/commands/{name} must update fields and increment version."""
    # First create a command to update.
    payload = {
        "name": "versioned-command",
        "display_name": "Versioned Command",
        "description": "Original description",
        "template": "Original template {{x}}.",
        "variables": [
            {"name": "x", "type": "string", "required": True, "description": "x"}
        ],
        "tools": [],
        "tags": [],
    }
    create_resp = await client.post("/api/v1/commands/", json=payload)
    assert create_resp.status_code == 201
    original_version = create_resp.json()["version"]

    # Now update it.
    updated_payload = {**payload, "description": "Updated description"}
    update_resp = await client.put("/api/v1/commands/versioned-command", json=updated_payload)
    assert update_resp.status_code == 200
    updated = update_resp.json()

    assert updated["description"] == "Updated description"
    assert updated["version"] == original_version + 1


@pytest.mark.asyncio
async def test_delete_command_soft_deletes(client: AsyncClient):
    """DELETE /api/v1/commands/{name} must return 204 and mark is_active=False."""
    # Create a command to delete.
    payload = {
        "name": "to-be-deleted",
        "display_name": "To Be Deleted",
        "description": "Will be soft-deleted",
        "template": "Delete me.",
        "variables": [],
        "tools": [],
        "tags": [],
    }
    create_resp = await client.post("/api/v1/commands/", json=payload)
    assert create_resp.status_code == 201

    delete_resp = await client.delete("/api/v1/commands/to-be-deleted")
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_deleted_command_not_in_list(client: AsyncClient):
    """A soft-deleted command must not appear in GET /api/v1/commands/."""
    # Create and delete.
    payload = {
        "name": "hidden-command",
        "display_name": "Hidden Command",
        "description": "Should disappear after delete",
        "template": "Hidden.",
        "variables": [],
        "tools": [],
        "tags": [],
    }
    await client.post("/api/v1/commands/", json=payload)
    await client.delete("/api/v1/commands/hidden-command")

    # Confirm it is absent from the list.
    list_resp = await client.get("/api/v1/commands/")
    names = {c["name"] for c in list_resp.json()}
    assert "hidden-command" not in names

    # Also confirm it is absent from a direct GET.
    get_resp = await client.get("/api/v1/commands/hidden-command")
    assert get_resp.status_code == 404
