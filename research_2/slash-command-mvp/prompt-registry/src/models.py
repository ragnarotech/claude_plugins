"""
Pydantic v2 models for the Prompt Registry service.

# DECISION: Single models.py for all data shapes rather than per-router model files.
# Why: MVP has few models; colocation makes inter-model relationships obvious.
# Production: Split into commands/skills/resolution sub-modules as the schema grows.
# Standard: Pydantic v2 with strict typing.
# Alternative: Rejected dataclasses -- weaker validation and no JSON schema generation.

# MCP_MAPPING: MCPPrompt mirrors the MCP prompts protocol shape so the agent-middleware can
#              forward it directly to Claude's /v1/messages prompt list without transformation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Command models
# ---------------------------------------------------------------------------

class CommandVariable(BaseModel):
    """A single template variable declared by a command."""

    name: str
    # DECISION: type is a plain string enum rather than a Python Enum.
    # Why: Simpler JSON roundtrip; the set of types is small and stable for MVP.
    # Production: Convert to a proper Enum and add validation on create/update.
    type: str  # "string" | "number" | "select"
    required: bool = True
    description: str
    default: str | None = None
    enum: list[str] | None = None  # populated when type == "select"


class Command(BaseModel):
    """Full command record as stored in the database."""

    id: str  # UUID string
    name: str
    display_name: str
    description: str
    template: str

    # INTEGRATION: variables, tools, and tags are stored as JSON TEXT in SQLite.
    #              Deserialised to Python lists before constructing this model.
    variables: list[CommandVariable] = []
    tools: list[str] = []
    tags: list[str] = []

    # DECISION: source tracks provenance so the UI can distinguish built-in vs user commands.
    # Why: Needed for the marketplace roadmap without a schema migration.
    # Production: Enforce source via auth -- only admins may set source="builtin".
    # Alternative: Rejected a separate provenance table for MVP simplicity.
    source: str = "builtin"  # "builtin" | "user" | "marketplace"

    # DECISION: Soft integer versioning on the row itself.
    # Why: Zero extra tables; trivial to increment on PUT.
    # Production: Immutable version history table with foreign key to command id.
    # Alternative: Rejected semver strings -- overkill for MVP; harder to sort.
    version: int = 1
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class CommandCreate(BaseModel):
    """Request body for POST /commands and PUT /commands/{name}."""

    name: str
    display_name: str
    description: str
    template: str
    variables: list[CommandVariable] = []
    tools: list[str] = []
    tags: list[str] = []


# ---------------------------------------------------------------------------
# Resolution models
# ---------------------------------------------------------------------------

class ResolvedCommand(BaseModel):
    """Successful result of resolving a command template with concrete arguments.

    # MCP_MAPPING: resolved_prompt maps to MCP message content; required_tools maps to
    #              the tools array passed to claude /v1/messages.
    """

    command_name: str
    resolved_prompt: str
    system_context: str
    required_tools: list[str]
    original_command: str  # the raw template before substitution
    metadata: dict


class ResolutionError(BaseModel):
    """Returned when template resolution fails (e.g. missing required variable).

    # MCP_MAPPING: code and message surface directly in the agent-middleware error response
    #              so the UI can render a targeted "fill in this field" prompt.
    """

    code: str   # e.g. "MISSING_VARIABLE", "COMMAND_NOT_FOUND"
    message: str
    command_name: str
    required_variables: list[CommandVariable] = []


# ---------------------------------------------------------------------------
# Skill models
# ---------------------------------------------------------------------------

class Skill(BaseModel):
    """Full skill record as stored in the database and returned by the API."""

    id: str  # UUID string
    name: str
    description: str

    # DECISION: Store raw SKILL.md as a TEXT blob rather than parsed fragments.
    # Why: The agent-middleware injects the raw markdown directly into the system prompt;
    #      preserving the original formatting is important for Claude to parse it reliably.
    # Production: Add a rendered_html column for frontend display.
    skill_md: str

    # INTEGRATION: frontmatter dict is parsed YAML; tools and tags are also extracted from it
    #              for efficient DB-level filtering without reparsing the markdown blob.
    frontmatter: dict
    tools: list[str] = []
    tags: list[str] = []
    source: str = "builtin"
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# MCP protocol models
# ---------------------------------------------------------------------------

class MCPPrompt(BaseModel):
    """MCP prompts protocol representation of a command.

    # MCP_MAPPING: Follows the Model Context Protocol prompts schema so the agent-middleware
    #              can serve commands as MCP prompts without any transformation layer.
    #              See: https://modelcontextprotocol.io/docs/concepts/prompts
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    title: str
    description: str
    # Each argument: {"name": str, "description": str, "required": bool}
    arguments: list[dict]

    # DECISION: _meta carries resolution and tool hints for the agent-middleware.
    # Why: MCP spec allows opaque _meta; we use it to avoid a separate API call.
    # Production: Formalise _meta schema and version it alongside the command schema.
    # NOTE: Pydantic v2 forbids leading-underscore field names; alias preserves MCP wire format.
    meta: dict = Field(default_factory=dict, serialization_alias="_meta")
