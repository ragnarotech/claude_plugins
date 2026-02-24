"""
FastAPI router for slash command CRUD and resolution.

# DECISION: No authentication on any endpoint for MVP.
# Why: MVP runs on a private internal network; adding auth before the UX is validated
#      wastes sprint time and complicates local dev.
# Production: Add JWT middleware (Bearer token). source="user" commands are scoped to the
#             authenticated user; source="builtin" commands require an admin role.
# Standard: OAuth2 / JWT per RFC 7519.
# Alternative: Rejected API keys -- harder to rotate and audit than short-lived JWTs.

# DECISION: No pagination for list endpoints in MVP.
# Why: Seed data is 4 commands; real-world deployments are unlikely to exceed a few hundred
#      before the marketplace feature warrants proper pagination.
# Production: Cursor-based pagination (keyset) on name column; avoid OFFSET for large tables.
# Alternative: Rejected page/size params -- OFFSET pagination degrades at scale.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from src.database import get_db, row_to_dict
from src.models import (
    Command,
    CommandCreate,
    CommandVariable,
    MCPPrompt,
    ResolvedCommand,
    ResolutionError,
)
from src.services import command_resolver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/commands", tags=["commands"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_command(row_dict: dict) -> Command:
    """Deserialise a DB row dict (with JSON columns already decoded) into a Command."""
    # variables is a list[dict]; coerce each dict into a CommandVariable.
    raw_vars = row_dict.get("variables", [])
    row_dict["variables"] = [
        CommandVariable(**v) if isinstance(v, dict) else v for v in raw_vars
    ]
    return Command(**row_dict)


def command_to_mcp_prompt(command: Command) -> MCPPrompt:
    """Convert a Command to MCP prompts protocol format.

    # MCP_MAPPING: arguments list maps 1-to-1 to MCP prompt arguments.
    #              The agent-middleware forwards this directly to Claude's prompt list.
    """
    arguments = [
        {
            "name": var.name,
            "description": var.description,
            "required": var.required,
        }
        for var in command.variables
    ]
    return MCPPrompt(
        name=command.name,
        title=command.display_name,
        description=command.description,
        arguments=arguments,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[Command])
async def list_commands(search: str | None = None, tag: str | None = None):
    """Return all active commands, optionally filtered by *search* text or *tag*.

    # DECISION: is_active filter applied at DB level, not in Python.
    # Why: Prevents deleted commands leaking into list responses even if code paths change.
    # Production: Add LIMIT/OFFSET or keyset pagination.
    """
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM commands WHERE is_active = TRUE ORDER BY name"
        )

    commands = [_row_to_command(row_to_dict(r)) for r in rows]

    if search:
        search_lower = search.lower()
        commands = [
            c for c in commands
            if search_lower in c.name.lower() or search_lower in c.description.lower()
        ]

    if tag:
        commands = [c for c in commands if tag in c.tags]

    return commands


@router.get("/{name}/mcp", response_model=MCPPrompt)
async def get_command_mcp(name: str):
    """Return the MCP prompts protocol representation of a command.

    # MCP_MAPPING: Used by agent-middleware to register commands as MCP prompts.
    #              Must be called before the /resolve endpoint to get argument schema.
    """
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM commands WHERE name = ? AND is_active = TRUE", (name,)
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Command '{name}' not found")

    command = _row_to_command(row_to_dict(row))
    return command_to_mcp_prompt(command)


@router.get("/{name}/resolve")
async def resolve_command(name: str, request: Request):
    """Resolve a command template with values supplied as query parameters.

    All query params beyond ``name`` itself are treated as variable substitutions.

    # DECISION: Query params rather than a POST body for resolution.
    # Why: GET + query params means the resolve URL is bookmarkable and testable
    #      directly from a browser address bar -- crucial for rapid MVP iteration.
    # Production: Also accept a POST /resolve with a JSON body for long/complex values.
    # Alternative: Rejected POST-only -- hurts developer experience during debugging.

    # INTEGRATION: The agent-middleware calls this endpoint and forwards
    #              ResolvedCommand.resolved_prompt as the user message to Claude.
    """
    # Collect all query params as potential variable arguments.
    arguments = dict(request.query_params)

    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM commands WHERE name = ? AND is_active = TRUE", (name,)
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Command '{name}' not found")

    command = _row_to_command(row_to_dict(row))

    # Build minimal user context from request headers (X-User, X-Env).
    user_context = {
        "user": request.headers.get("X-User", "anonymous"),
        "env": request.headers.get("X-Env", "unknown"),
    }

    result = command_resolver.resolve_command(command, arguments, user_context)

    if isinstance(result, ResolutionError):
        # 422 Unprocessable Entity: the request was well-formed but semantically invalid.
        raise HTTPException(status_code=422, detail=result.model_dump())

    return result


@router.get("/{name}", response_model=Command)
async def get_command(name: str):
    """Return a single command by name, or 404 if not found."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM commands WHERE name = ? AND is_active = TRUE", (name,)
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Command '{name}' not found")

    return _row_to_command(row_to_dict(row))


@router.post("/", response_model=Command, status_code=201)
async def create_command(command: CommandCreate):
    """Create a new command.

    # DECISION: Auto-generate UUID and timestamps server-side.
    # Why: Clients should not be trusted to supply canonical IDs or timestamps.
    # Production: Set source based on the authenticated user's role.
    # Alternative: Rejected client-supplied IDs -- collision risk; harder to audit.
    """
    now = datetime.now(timezone.utc).isoformat()
    cmd_id = str(uuid.uuid4())

    row = {
        "id": cmd_id,
        "name": command.name,
        "display_name": command.display_name,
        "description": command.description,
        "template": command.template,
        "variables": json.dumps([v.model_dump() for v in command.variables]),
        "tools": json.dumps(command.tools),
        "tags": json.dumps(command.tags),
        "source": "user",
        "version": 1,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }

    try:
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO commands
                    (id, name, display_name, description, template,
                     variables, tools, tags, source, version,
                     is_active, created_at, updated_at)
                VALUES
                    (:id, :name, :display_name, :description, :template,
                     :variables, :tools, :tags, :source, :version,
                     :is_active, :created_at, :updated_at)
                """,
                row,
            )
            await db.commit()
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(
                status_code=409, detail=f"Command '{command.name}' already exists"
            )
        raise

    # Re-fetch the row from the DB so the return value goes through the same
    # deserialisation path as all other endpoints (consistent datetime parsing etc.).
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM commands WHERE id = ?", (cmd_id,)
        ) as cursor:
            created_row = await cursor.fetchone()

    return _row_to_command(row_to_dict(created_row))


@router.put("/{name}", response_model=Command)
async def update_command(name: str, command: CommandCreate):
    """Update an existing command and increment its version.

    # DECISION: Soft versioning -- increment the integer version column in place.
    # Why: Trivial to implement; the current version is always the live row.
    # Production: Immutable version history table (command_versions) with a foreign key
    #             to commands.id so any version can be retrieved or rolled back.
    # Alternative: Rejected semver strings -- adds parsing complexity for no MVP benefit.
    """
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        async with db.execute(
            "SELECT version FROM commands WHERE name = ? AND is_active = TRUE", (name,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail=f"Command '{name}' not found")

        new_version = row["version"] + 1

        await db.execute(
            """
            UPDATE commands
            SET display_name = ?,
                description  = ?,
                template     = ?,
                variables    = ?,
                tools        = ?,
                tags         = ?,
                version      = ?,
                updated_at   = ?
            WHERE name = ? AND is_active = TRUE
            """,
            (
                command.display_name,
                command.description,
                command.template,
                json.dumps([v.model_dump() for v in command.variables]),
                json.dumps(command.tools),
                json.dumps(command.tags),
                new_version,
                now,
                name,
            ),
        )
        await db.commit()

        async with db.execute(
            "SELECT * FROM commands WHERE name = ?", (name,)
        ) as cursor:
            updated_row = await cursor.fetchone()

    return _row_to_command(row_to_dict(updated_row))


@router.delete("/{name}", status_code=204)
async def delete_command(name: str):
    """Soft-delete a command by setting is_active=False.

    # DECISION: Soft delete rather than hard DELETE.
    # Why: Preserves audit trail; the agent-middleware may have cached the command ID.
    #      Allows recovery without a DB restore.
    # Production: Add a deleted_at timestamp column and a separate purge job.
    # Alternative: Rejected hard DELETE -- unrecoverable; breaks any logs referencing the ID.
    """
    async with get_db() as db:
        async with db.execute(
            "SELECT id FROM commands WHERE name = ? AND is_active = TRUE", (name,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail=f"Command '{name}' not found")

        await db.execute(
            "UPDATE commands SET is_active = FALSE WHERE name = ?", (name,)
        )
        await db.commit()

    # 204 No Content -- return nothing.
    return None
