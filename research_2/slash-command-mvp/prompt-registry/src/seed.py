"""
Seed data for the Prompt Registry MVP.

# DECISION: Hardcode seed data in Python rather than a SQL dump or YAML fixture.
# Why: Python dicts are type-checked by the models; easy to extend and review in PRs.
# Production: Replace with a proper migration/fixture system (e.g. Alembic data migrations
#             or a separate seed CLI command).
# Standard: Idempotent seeding -- is_seeded() prevents duplicates on restart.
# Alternative: Rejected SQL INSERT OR IGNORE scripts -- less readable; no Pydantic validation.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

import aiosqlite

from src.database import get_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seed payload
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc).isoformat()

_COMMANDS: list[dict] = [
    {
        "id": str(uuid.uuid4()),
        "name": "triage-ticket",
        "display_name": "Triage Ticket",
        "description": "Analyze and triage a Jira ticket with AI-powered assessment",
        "template": (
            "You are triaging ticket {{ticket_number}}.\n\n"
            "First, use the `jira_get_ticket` tool to fetch the full ticket details for {{ticket_number}}.\n\n"
            "Then analyze the ticket and provide:\n"
            "1. **Priority Assessment**: Based on the ticket description, suggest a priority "
            "(Critical/High/Medium/Low) with reasoning\n"
            "2. **Component Classification**: Which system component(s) does this affect?\n"
            "3. **Suggested Assignee**: Based on the component and recent activity, who should own this?\n"
            "4. **Estimated Effort**: T-shirt size (XS/S/M/L/XL) with reasoning\n"
            "5. **Recommended Next Steps**: 2-3 concrete actions to move this forward\n\n"
            "If the ticket priority or assignee should be updated, use the `jira_update_ticket` tool "
            "to make the changes."
        ),
        "variables": json.dumps([
            {
                "name": "ticket_number",
                "type": "string",
                "required": True,
                "description": "Jira ticket number (e.g., PROJ-1234)",
                "default": None,
                "enum": None,
            }
        ]),
        "tools": json.dumps(["jira_get_ticket", "jira_update_ticket"]),
        "tags": json.dumps(["jira", "triage", "project-management"]),
        "source": "builtin",
        "version": 1,
        "is_active": True,
        "created_at": _NOW,
        "updated_at": _NOW,
    },
    {
        "id": str(uuid.uuid4()),
        "name": "list-my-tickets",
        "display_name": "List My Tickets",
        "description": "List all open tickets assigned to you",
        "template": (
            "Use the `jira_list_tickets` tool to fetch all open tickets. "
            "Show them in a formatted table with: ticket number, title, priority, and status. "
            "Group by priority (Critical first)."
        ),
        "variables": json.dumps([]),
        "tools": json.dumps(["jira_list_tickets"]),
        "tags": json.dumps(["jira", "tickets"]),
        "source": "builtin",
        "version": 1,
        "is_active": True,
        "created_at": _NOW,
        "updated_at": _NOW,
    },
    {
        "id": str(uuid.uuid4()),
        "name": "create-pr",
        "display_name": "Create Pull Request",
        "description": "Generate a PR description from ticket details and recent commits",
        "template": (
            "You are creating a pull request for ticket {{ticket_number}}.\n\n"
            "1. Use `jira_get_ticket` to fetch the ticket details for {{ticket_number}}\n"
            "2. Use `git_list_commits` to get the last 10 commits\n"
            "3. Based on the ticket requirements and commits, generate:\n"
            "   - **PR Title**: Concise, following conventional commits format (feat/fix/chore)\n"
            "   - **PR Description**: What changed and why (reference the ticket)\n"
            "   - **Testing Notes**: What to test based on the changes\n"
            "   - **Breaking Changes**: Any API or behavior changes\n"
            "4. Use `git_create_pr` to create the pull request with the generated content"
        ),
        "variables": json.dumps([
            {
                "name": "ticket_number",
                "type": "string",
                "required": True,
                "description": "Jira ticket number the PR addresses",
                "default": None,
                "enum": None,
            }
        ]),
        "tools": json.dumps(["jira_get_ticket", "git_list_commits", "git_create_pr"]),
        "tags": json.dumps(["git", "pr", "development"]),
        "source": "builtin",
        "version": 1,
        "is_active": True,
        "created_at": _NOW,
        "updated_at": _NOW,
    },
    {
        "id": str(uuid.uuid4()),
        "name": "summarize-thread",
        "display_name": "Summarize Thread",
        "description": "Summarize a discussion thread or conversation",
        "template": (
            "Please summarize the following discussion thread: {{thread_url}}\n\n"
            "Provide:\n"
            "1. **Key Points**: Main topics discussed (bullet list)\n"
            "2. **Decisions Made**: Any decisions or conclusions reached\n"
            "3. **Action Items**: Follow-up tasks identified\n"
            "4. **Open Questions**: Unresolved issues\n\n"
            "Keep the summary concise but comprehensive."
        ),
        "variables": json.dumps([
            {
                "name": "thread_url",
                "type": "string",
                "required": True,
                "description": "URL of the thread to summarize",
                "default": None,
                "enum": None,
            }
        ]),
        "tools": json.dumps([]),
        "tags": json.dumps(["communication", "summary"]),
        "source": "builtin",
        "version": 1,
        "is_active": True,
        "created_at": _NOW,
        "updated_at": _NOW,
    },
]


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------

async def is_seeded(db: aiosqlite.Connection) -> bool:
    """Return True if the commands table already contains at least one row.

    # DECISION: Single-row check rather than per-command upsert.
    # Why: Seed runs once at startup; an empty table reliably means a fresh deployment.
    # Production: Track seed version in a migrations table so individual commands can be
    #             added or updated across deployments without wiping all user data.
    """
    async with db.execute("SELECT COUNT(*) FROM commands") as cursor:
        row = await cursor.fetchone()
        return row is not None and row[0] > 0


async def seed_database() -> None:
    """Insert seed commands if the database is empty (idempotent)."""
    async with get_db() as db:
        if await is_seeded(db):
            logger.info("Database already seeded; skipping command seed.")
            return

        for cmd in _COMMANDS:
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
                ON CONFLICT(name) DO NOTHING
                """,
                cmd,
            )
        await db.commit()
        logger.info("Seeded %d commands.", len(_COMMANDS))
