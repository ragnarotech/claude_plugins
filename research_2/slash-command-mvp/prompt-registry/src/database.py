"""
Async SQLite database layer for the Prompt Registry service.

# DECISION: SQLite for MVP via aiosqlite.
# Why: Zero infrastructure to spin up; ships inside the container; sufficient for
#      hundreds of commands and a handful of concurrent reads.
# Production: PostgreSQL with asyncpg. Replace aiosqlite with asyncpg and swap the
#             CREATE TABLE DDL for proper migrations (Alembic).
# Standard: aiosqlite async context manager pattern.
# Alternative: Rejected SQLAlchemy ORM for MVP -- adds indirection and a heavier
#              dependency tree for a service with 2 tables.

# DECISION: JSON columns (variables, tools, tags, frontmatter) stored as TEXT.
# Why: SQLite has no native JSON column type; TEXT + json.loads/json.dumps is idiomatic.
# Production: PostgreSQL JSONB gives indexed querying on these fields.
# Alternative: Rejected a separate normalised rows approach -- too much schema for MVP.
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite

from src.config import settings

logger = logging.getLogger(__name__)

# INTEGRATION: All routers import `get_db` and use it as an async context manager.
#              The DB path is controlled by settings.DATABASE_URL; strip the
#              "sqlite+aiosqlite:///" prefix to get the filesystem path.

_DB_PATH: str = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")

# DDL -----------------------------------------------------------------

_CREATE_COMMANDS_TABLE = """
CREATE TABLE IF NOT EXISTS commands (
    id          TEXT PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    template    TEXT NOT NULL,
    variables   TEXT NOT NULL DEFAULT '[]',
    tools       TEXT NOT NULL DEFAULT '[]',
    tags        TEXT NOT NULL DEFAULT '[]',
    source      TEXT NOT NULL DEFAULT 'builtin',
    version     INTEGER NOT NULL DEFAULT 1,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

# DECISION: SQLite for MVP. Production: PostgreSQL with asyncpg.
_CREATE_SKILLS_TABLE = """
CREATE TABLE IF NOT EXISTS skills (
    id          TEXT PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    skill_md    TEXT NOT NULL,
    frontmatter TEXT NOT NULL DEFAULT '{}',
    tools       TEXT NOT NULL DEFAULT '[]',
    tags        TEXT NOT NULL DEFAULT '[]',
    source      TEXT NOT NULL DEFAULT 'builtin',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


async def init_db() -> None:
    """Create tables if they do not exist. Safe to call on every startup (idempotent)."""
    # Ensure parent directory exists so SQLite can create the file.
    db_dir = os.path.dirname(_DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(_CREATE_COMMANDS_TABLE)
        await db.execute(_CREATE_SKILLS_TABLE)
        await db.commit()
    logger.info("Database initialised at %s", _DB_PATH)


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Yield an open aiosqlite connection; close it when the caller's block exits.

    Usage::

        async with get_db() as db:
            rows = await db.execute("SELECT * FROM commands")

    # DECISION: One connection per request rather than a connection pool.
    # Why: SQLite has no benefit from pooling (single writer); aiosqlite serialises
    #      writes anyway.
    # Production: asyncpg uses a connection pool; replace this with
    #             asyncpg.create_pool() managed on app startup.
    """
    db = await aiosqlite.connect(_DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Helper utilities used by seed.py and routers
# ---------------------------------------------------------------------------

def row_to_dict(row: aiosqlite.Row) -> dict:
    """Convert an aiosqlite Row to a plain dict with JSON columns deserialised."""
    d = dict(row)
    for col in ("variables", "tools", "tags", "frontmatter"):
        if col in d and isinstance(d[col], str):
            d[col] = json.loads(d[col])
    return d
