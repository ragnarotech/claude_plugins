"""
Pytest configuration and shared fixtures for BDD tests.
"""
import json
import os
import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def project_root():
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def test_data_path(project_root):
    """Return path to test data directory."""
    return project_root / "data"


@pytest.fixture(scope="session")
def load_test_cases(test_data_path):
    """
    Load test cases from JSON file (DVC-tracked data).

    In production, this would be loaded from DVC-managed storage (S3, GCS, etc).
    """
    test_cases_file = test_data_path / "test_cases.json"

    if not test_cases_file.exists():
        pytest.fail(f"Test data file not found: {test_cases_file}")

    with open(test_cases_file, 'r') as f:
        data = json.load(f)

    return data


@pytest.fixture
def test_context():
    """
    Shared state between BDD steps.

    This fixture provides a dictionary that persists across Given/When/Then steps
    within a single scenario, allowing data to flow through the test.
    """
    return {
        "threshold": 0.7,
        "model": "gpt-3.5-turbo",
        "input": None,
        "actual_output": None,
        "expected_output": None,
        "retrieval_context": [],
        "test_case": None,
        "metrics": {},
    }


@pytest.fixture
def mock_llm_client():
    """
    Mock LLM client for testing without real API calls.

    Import the mock client from src module.
    """
    from src.mock_llm import MockLLMClient
    return MockLLMClient()


@pytest.fixture(scope="session")
def s3_test_data(load_test_cases):
    """
    Simulate loading test data from S3.

    In production, this would use boto3 to fetch from actual S3:

    s3 = boto3.client('s3')
    response = s3.get_object(
        Bucket='llm-evaluation-data',
        Key='golden-datasets/customer-support-v2.json'
    )
    return json.loads(response['Body'].read().decode('utf-8'))
    """
    return load_test_cases


@pytest.fixture
def test_prompts(s3_test_data):
    """Extract test prompts for parameterized tests."""
    return s3_test_data.get('test_cases', [])


# Environment configuration
@pytest.fixture(scope="session", autouse=True)
def configure_environment():
    """
    Configure environment for testing.

    Set up environment variables and mock API keys if needed.
    """
    # Set mock API key if not present (for testing without real API calls)
    if not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "sk-mock-key-for-testing"

    yield

    # Cleanup after all tests


@pytest.fixture(autouse=True)
def reset_test_context(test_context):
    """Reset test context before each test."""
    yield
    # Context is reset by fixture scope


# Optional: Elasticsearch/ELK reporting integration
@pytest.fixture(scope="session", autouse=True)
def configure_elk_session(request):
    """
    Add session metadata to ELK reports if pytest-elk-reporter is configured.

    This requires pytest-elk-reporter plugin and Elasticsearch configuration
    in pytest.ini.
    """
    # Check if elk-reporter plugin is available
    if hasattr(request.config, 'pluginmanager'):
        elk = request.config.pluginmanager.get_plugin("elk-reporter-runtime")
        if elk:
            elk.session_data.update({
                "test_suite": "llm-evaluation",
                "framework": "pytest-bdd + deepeval",
                "model": "gpt-3.5-turbo",
            })

    yield


def pytest_configure(config):
    """
    Pytest configuration hook.

    Register custom markers and configure test environment.
    """
    # Markers are already defined in pytest.ini
    pass


def pytest_collection_modifyitems(config, items):
    """
    Modify test items after collection.

    Can be used to add markers, skip tests, etc.
    """
    for item in items:
        # Add 'bdd' marker to all BDD tests
        if 'bdd' not in [marker.name for marker in item.iter_markers()]:
            if hasattr(item, 'function') and hasattr(item.function, '__wrapped__'):
                item.add_marker(pytest.mark.bdd)
