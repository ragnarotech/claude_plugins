"""
pytest configuration for the Prompt Registry test suite.

Environment variables that must be in place BEFORE src.config is first imported
are set at module level here (conftest.py is loaded before test modules are
collected).

# DECISION: Temp-file DB rather than :memory: for test isolation.
# Why: aiosqlite shares a single connection to an in-memory DB, which causes
#      interference between tests when the lifespan reseeds on each client
#      fixture creation. A temp file on disk gives each session a clean slate
#      while remaining fast.
# Alternative: Rejected monkeypatching get_db -- too much boilerplate per test;
#              rejected :memory: -- connection-sharing issues with aiosqlite.
"""

import os
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Set env vars at module level so pydantic-settings picks them up on first import.
# ---------------------------------------------------------------------------
_db_fd, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="prompt_registry_test_")
os.close(_db_fd)

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_PATH}"

# Point SKILLS_DIR at the real skills directory so skill seeding works in tests.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["SKILLS_DIR"] = os.path.join(_REPO_ROOT, "src", "skills")


# ---------------------------------------------------------------------------
# Session-scoped cleanup fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db():
    """Remove the temporary database file after the test session completes."""
    yield
    try:
        os.unlink(_DB_PATH)
    except OSError:
        pass
