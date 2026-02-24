"""
FastAPI application entry point for the Prompt Registry service.

# DECISION: Lifespan event handler (not deprecated @app.on_event) for startup logic.
# Why: FastAPI deprecated on_event in 0.93; lifespan is the current standard.
# Production: Move heavy startup tasks (DB migrations, schema validation) to a
#             separate init container in Kubernetes so the app pod starts faster.
# Standard: FastAPI lifespan context manager (https://fastapi.tiangolo.com/advanced/events/).
# Alternative: Rejected @app.on_event("startup") -- deprecated and will be removed.

# DECISION: Allow all CORS origins for MVP.
# Why: The frontend runs on a different port during local dev; locking down origins
#      before the deployment topology is finalised wastes time.
# Production: Restrict allow_origins to the exact frontend domain(s); add
#             allow_headers and expose_headers lists.
# Standard: CORS W3C spec / FastAPI CORSMiddleware.
# Alternative: Rejected disabling CORS entirely -- browsers block cross-origin XHR.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.database import init_db
from src.routers import commands, skills
from src.seed import seed_database
from src.services.skill_loader import load_skills_from_disk, seed_skills

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks before yielding control to the request loop.

    Startup order:
    1. init_db()      -- create tables (idempotent DDL)
    2. seed_database() -- insert hardcoded commands if the table is empty
    3. load_skills_from_disk() + seed_skills() -- discover and persist SKILL.md files

    # INTEGRATION: All three steps must complete before the service is ready to serve
    #              traffic. The Kubernetes readiness probe should hit /api/v1/health
    #              which only returns 200 after lifespan completes.
    """
    logger.info("Starting Prompt Registry service...")

    await init_db()
    logger.info("Database initialised.")

    await seed_database()
    logger.info("Command seed complete.")

    skill_list = load_skills_from_disk(settings.SKILLS_DIR)
    await seed_skills(skill_list)
    logger.info("Skill seed complete (%d skills).", len(skill_list))

    logger.info("Prompt Registry ready on %s:%s", settings.HOST, settings.PORT)
    yield
    # Shutdown: nothing to clean up for SQLite MVP.


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Prompt Registry",
    description="Single source of truth for slash command definitions and skill metadata.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS -- allow all for MVP (see DECISION above).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(commands.router)
app.include_router(skills.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/v1/health", tags=["health"])
async def health():
    """Kubernetes / Docker liveness and readiness probe endpoint.

    # INTEGRATION: agent-middleware polls this endpoint at startup to confirm
    #              the registry is available before registering MCP prompts.
    """
    return {"status": "ok", "service": "prompt-registry"}
