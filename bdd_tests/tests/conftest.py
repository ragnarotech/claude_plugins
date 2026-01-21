"""
Pytest configuration and shared fixtures for BDD tests.
"""
import os
import pytest
from pathlib import Path

# Import your actual agent - adjust path as needed
# from your_agent_package import YourPydanticAgent

from src.agent_wrapper import PydanticAITestWrapper


@pytest.fixture(scope="session")
def project_root():
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def test_data_path(project_root):
    """Return path to test data directory."""
    return project_root / "data"


@pytest.fixture
def test_context():
    """
    Shared state between BDD steps within a single scenario.

    This dictionary persists across Given/When/Then steps,
    allowing data to flow through the test.
    """
    return {
        "mock_date": None,
        "user_prompt": None,
        "agent_response": None,
        "expected_tool": None,
        "expected_params": {},
        "conversation_turns": [],
        "metrics": {},
    }


@pytest.fixture(scope="session")
def agent_instance():
    """
    Create the actual Pydantic AI agent instance.

    TODO: Replace with your actual agent initialization.
    """
    # Example - replace with your actual agent:
    # from your_agent_package import create_agent
    # return create_agent()

    # Placeholder for testing the framework itself
    from unittest.mock import AsyncMock, MagicMock

    mock_agent = MagicMock()
    mock_result = MagicMock()
    mock_result.data = "Mock response"
    mock_result.tool_results = MagicMock(return_value=[])

    async def mock_run(prompt, **kwargs):
        return mock_result

    mock_agent.run = mock_run
    return mock_agent


@pytest.fixture
def agent_wrapper(agent_instance):
    """
    Create a fresh agent wrapper for each test.

    The wrapper captures tool calls for DeepEval verification.
    """
    wrapper = PydanticAITestWrapper(agent_instance)
    yield wrapper
    wrapper.clear_history()


@pytest.fixture(scope="session", autouse=True)
def configure_environment():
    """
    Configure environment for testing.
    """
    # Set mock API key if not present (for testing without real API)
    if not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "sk-mock-key-for-testing"

    yield


# Elasticsearch reporting hook (configured in Phase 6)
@pytest.fixture(scope="session", autouse=True)
def configure_elk_session(request):
    """Add session metadata to ELK reports if configured."""
    if hasattr(request.config, 'pluginmanager'):
        elk = request.config.pluginmanager.get_plugin("elk-reporter-runtime")
        if elk:
            elk.session_data.update({
                "test_suite": "bdd-deepeval-mcp",
                "framework": "pytest-bdd + deepeval",
            })
    yield
