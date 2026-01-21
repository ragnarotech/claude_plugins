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


# Data loading fixtures (Phase 5)
from src.data_loader import TestDataLoader, get_data_loader


@pytest.fixture(scope="session")
def data_loader():
    """Session-scoped test data loader."""
    return get_data_loader()


@pytest.fixture
def load_test_cases(data_loader):
    """
    Factory fixture to load test cases by dataset name.

    Usage in steps:
        test_cases = load_test_cases("weather_scenarios")
    """
    def _load(dataset_name: str):
        return data_loader.load_test_cases(dataset_name)
    return _load


@pytest.fixture
def load_expected_output(data_loader):
    """
    Factory fixture to load expected output by test ID.

    Usage in steps:
        expected = load_expected_output("weather_001")
    """
    def _load(test_id: str, dataset_name: str = "expected_outputs"):
        return data_loader.load_expected_output(test_id, dataset_name)
    return _load


# Elasticsearch reporting (Phase 6)
from src.elk_reporter import DeepEvalResultReporter


# Global reporter instance
_elk_reporter: DeepEvalResultReporter | None = None


def get_elk_reporter() -> DeepEvalResultReporter | None:
    """Get or create ELK reporter if configured."""
    global _elk_reporter

    if _elk_reporter is None and os.environ.get("ES_HOST"):
        _elk_reporter = DeepEvalResultReporter()

    return _elk_reporter


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Hook to report test results to Elasticsearch.

    Captures test outcome and DeepEval metrics.
    """
    outcome = yield
    report = outcome.get_result()

    # Only report on test completion (not setup/teardown)
    if report.when != "call":
        return

    reporter = get_elk_reporter()
    if reporter is None:
        return

    # Extract test context if available
    test_context = getattr(item, "_test_context", {})

    # Extract metrics from test context
    metrics = test_context.get("metrics", {})

    # Extract tool calls
    tool_calls = []
    if test_context.get("tool_calls"):
        tool_calls = [tc.name for tc in test_context["tool_calls"]]

    reporter.report_test_result(
        test_id=item.nodeid,
        test_name=item.name,
        outcome=report.outcome,
        duration=report.duration,
        metrics=metrics,
        tool_calls=tool_calls,
        test_context=test_context,
        error_message=str(report.longrepr) if report.failed else None,
    )


@pytest.fixture(autouse=True)
def capture_test_context(request, test_context):
    """Capture test context for ELK reporting."""
    yield
    # Store context on the test item for the hook to access
    request.node._test_context = test_context


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
