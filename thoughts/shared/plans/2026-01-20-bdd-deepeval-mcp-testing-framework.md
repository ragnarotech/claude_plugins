# BDD DeepEval MCP Testing Framework Implementation Plan

## Overview

Build an end-to-end BDD testing framework for a Pydantic AI Agent with MCP Server using pytest-bdd and DeepEval. The framework will support MCP tool verification (including optional parameters), conversational multi-turn testing, mock date injection, and compliance-friendly test data storage via S3/DVC. Tests run locally and in Kubernetes with results stored in Elasticsearch.

## Current State Analysis

### Existing Assets
- **Sample code** (`sample_code/`) provides foundation for pytest-bdd + DeepEval integration
- **Research documents** cover Kubernetes patterns, DVC compliance architecture, and framework comparison
- **MCP capture example** (`research/mcp_capture_example.py`) demonstrates DeepEval's MCP verification classes

### What's Missing
- Agent wrapper for Pydantic AI's `result.tool_results()` integration
- MCP tool verification step definitions
- Conversational (multi-turn) testing support
- Mock date injection via prompt prefix
- S3/DVC data loading fixtures
- Elasticsearch reporting integration
- Kubernetes Job manifests

### Key Discoveries
- DeepEval provides `MCPToolCall`, `MCPServer`, `MCPUseMetric` classes for tool verification (`research/mcp_capture_example.py:46-57`)
- Pydantic AI exposes tool results via `result.tool_results()` (user confirmed)
- Date injection via system/user prompt prefix is the preferred approach
- Test data must NOT exist on shared CI/CD infrastructure (compliance requirement)

## Desired End State

A complete BDD testing framework where:

1. **Gherkin feature files** express test scenarios in business-readable format
2. **MCP tool calls** are verified including tool name, parameters (with optional params), and responses
3. **Conversational flows** test multi-turn interactions where agent asks clarifying questions
4. **Mock dates** are injected via prompt prefix for date-dependent logic
5. **Test data** is stored in S3 with DVC pointers in Git for compliance
6. **Test results** stream to Elasticsearch with DeepEval metric scores
7. **Kubernetes Jobs** execute tests in-cluster with access to production agent

### Verification
- All feature files execute successfully with `pytest tests/ -v`
- MCP tool calls match expected parameters in test assertions
- Conversational scenarios pass with correct turn sequences
- Test data loads from S3 in Kubernetes (not present on CI/CD runners)
- Elasticsearch index contains test results with metric scores
- Kubernetes Job completes with proper exit codes

## What We're NOT Doing

- **Modifying the production Pydantic AI Agent** - we wrap it for testing
- **Building a custom MCP server mock** - we test against the real MCP server
- **Creating Kibana dashboards** - out of scope (Elasticsearch index only)
- **Helm chart** - using raw Kubernetes manifests for simplicity
- **Elastic APM integration** - using pytest-elk-reporter instead

## Implementation Approach

We build incrementally in 7 phases, each producing runnable tests:

1. **Foundation** - Project structure, agent wrapper, basic fixtures
2. **MCP Verification** - Tool call assertions with date injection
3. **Conversations** - Multi-turn testing support
4. **DeepEval Metrics** - LLM-based evaluation integration
5. **S3/DVC Data** - Compliance-friendly test data loading
6. **Elasticsearch** - Result reporting
7. **Kubernetes** - In-cluster execution

---

## Phase 1: Core Test Framework Foundation

### Overview
Set up the project structure, create the Pydantic AI agent wrapper that extracts tool call history, and establish core fixtures for BDD testing.

### Changes Required:

#### 1. Project Structure
**Create directories and files:**

```
bdd_tests/
├── features/
│   ├── mcp_tools.feature
│   └── conversations.feature
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── step_defs/
│       ├── __init__.py
│       ├── common_steps.py
│       ├── mcp_steps.py
│       └── conversation_steps.py
├── src/
│   ├── __init__.py
│   ├── agent_wrapper.py
│   ├── mcp_verifier.py
│   └── data_loader.py
├── data/
│   ├── .gitignore
│   └── test_cases.json.dvc
├── k8s/
│   ├── test-job.yaml
│   └── serviceaccount.yaml
├── pyproject.toml
├── pytest.ini
└── requirements.txt
```

#### 2. Dependencies
**File**: `bdd_tests/pyproject.toml`

```toml
[project]
name = "bdd-deepeval-mcp-tests"
version = "0.1.0"
description = "BDD testing framework for Pydantic AI Agent with MCP Server"
requires-python = ">=3.11"
dependencies = [
    "pytest>=7.4.0",
    "pytest-bdd>=7.0.0",
    "pytest-asyncio>=0.23.0",
    "deepeval>=1.0.0",
    "pydantic-ai>=0.1.0",
    "boto3>=1.28.0",
    "dvc[s3]>=3.0.0",
    "pytest-elk-reporter>=0.5.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest-xdist>=3.3.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "mcp: MCP tool verification tests",
    "conversation: Multi-turn conversation tests",
    "integration: Integration tests requiring live agent",
]
bdd_features_base_dir = "features/"
```

#### 3. Pytest Configuration
**File**: `bdd_tests/pytest.ini`

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --strict-markers
    --tb=short
markers =
    mcp: MCP tool verification tests
    conversation: Multi-turn conversation tests
    integration: Integration tests requiring live agent
bdd_features_base_dir = features/
```

#### 4. Agent Wrapper
**File**: `bdd_tests/src/agent_wrapper.py`

```python
"""
Wrapper for Pydantic AI Agent that extracts MCP tool call history
for DeepEval verification.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime

from deepeval.test_case import LLMTestCase, ConversationalTestCase, Turn
from deepeval.test_case.mcp import MCPServer, MCPToolCall


@dataclass
class ToolCallRecord:
    """Record of a single MCP tool call."""
    name: str
    args: dict[str, Any]
    result: Any
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AgentResponse:
    """Response from agent execution including tool call history."""
    output: str
    tool_calls: list[ToolCallRecord]
    raw_result: Any


class PydanticAITestWrapper:
    """
    Wraps a Pydantic AI Agent for BDD testing with DeepEval.

    Extracts tool call history from agent execution for verification.
    """

    def __init__(self, agent, mcp_server_name: str = "test-mcp-server"):
        """
        Initialize wrapper with a Pydantic AI agent.

        Args:
            agent: The Pydantic AI agent instance
            mcp_server_name: Name for the MCP server in DeepEval
        """
        self.agent = agent
        self.mcp_server_name = mcp_server_name
        self._tool_calls: list[ToolCallRecord] = []
        self._mcp_servers: list[MCPServer] = []

    def _inject_date_prompt(self, prompt: str, mock_date: str | None) -> str:
        """Prepend mock date to prompt if provided."""
        if mock_date:
            return f"Today's date is {mock_date}. {prompt}"
        return prompt

    async def run(
        self,
        prompt: str,
        mock_date: str | None = None,
        **kwargs
    ) -> AgentResponse:
        """
        Run the agent and capture tool calls.

        Args:
            prompt: User prompt to send to agent
            mock_date: Optional mock date string (e.g., "1/7/2025")
            **kwargs: Additional arguments passed to agent.run()

        Returns:
            AgentResponse with output and tool call history
        """
        # Inject date into prompt
        full_prompt = self._inject_date_prompt(prompt, mock_date)

        # Run the agent
        result = await self.agent.run(full_prompt, **kwargs)

        # Extract tool calls from Pydantic AI result
        self._tool_calls = []
        if hasattr(result, 'tool_results'):
            for tool_result in result.tool_results():
                self._tool_calls.append(ToolCallRecord(
                    name=tool_result.tool_name,
                    args=tool_result.args,
                    result=tool_result.result,
                ))

        return AgentResponse(
            output=str(result.data),
            tool_calls=self._tool_calls,
            raw_result=result,
        )

    def get_mcp_tool_calls(self) -> list[MCPToolCall]:
        """Convert tool calls to DeepEval MCPToolCall format."""
        return [
            MCPToolCall(
                name=tc.name,
                args=tc.args,
                result=tc.result,
            )
            for tc in self._tool_calls
        ]

    def create_test_case(
        self,
        user_input: str,
        agent_output: str,
        expected_output: str | None = None,
        retrieval_context: list[str] | None = None,
    ) -> LLMTestCase:
        """Create a DeepEval LLMTestCase from the interaction."""
        return LLMTestCase(
            input=user_input,
            actual_output=agent_output,
            expected_output=expected_output,
            retrieval_context=retrieval_context or [],
            mcp_tools_called=self.get_mcp_tool_calls(),
            mcp_servers=self._mcp_servers,
        )

    def clear_history(self):
        """Clear tool call history for new test."""
        self._tool_calls = []
```

#### 5. Core Fixtures
**File**: `bdd_tests/tests/conftest.py`

```python
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
```

#### 6. Common Step Definitions
**File**: `bdd_tests/tests/step_defs/common_steps.py`

```python
"""
Common BDD step definitions shared across feature files.
"""
import pytest
from pytest_bdd import given, when, then, parsers


@given(parsers.parse('today is "{mock_date}"'))
def set_mock_date(test_context, mock_date):
    """Set the mock date for the test scenario."""
    test_context["mock_date"] = mock_date


@given(parsers.parse('the LLM evaluator uses model "{model}"'))
def set_evaluator_model(test_context, model):
    """Set the model for DeepEval evaluation."""
    test_context["evaluator_model"] = model


@given(parsers.parse('the default threshold is {threshold:f}'))
def set_default_threshold(test_context, threshold):
    """Set default metric threshold."""
    test_context["threshold"] = threshold
```

### Success Criteria:

#### Automated Verification:
- [x] Project structure created: `ls -la bdd_tests/`
- [x] Dependencies install cleanly: `cd bdd_tests && pip install -e .`
- [x] Pytest discovers tests: `pytest --collect-only`
- [x] Agent wrapper instantiates without errors: `python -c "from src.agent_wrapper import PydanticAITestWrapper"`

#### Manual Verification:
- [ ] Confirm agent_instance fixture points to your actual Pydantic AI agent (replace placeholder)
- [ ] Verify agent wrapper correctly extracts tool_results() from your agent's response format

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation that the agent_instance fixture is correctly configured before proceeding to Phase 2.

---

## Phase 2: MCP Tool Verification Steps

### Overview
Implement step definitions for verifying MCP tool calls including tool name, parameters (with support for optional parameters), and responses. Add date injection via prompt prefix.

### Changes Required:

#### 1. MCP Verifier Utility
**File**: `bdd_tests/src/mcp_verifier.py`

```python
"""
MCP tool call verification utilities for BDD testing.

Provides helpers for asserting tool calls match expectations,
including partial argument matching and call order verification.
"""
from typing import Any
from dataclasses import dataclass

from src.agent_wrapper import ToolCallRecord


@dataclass
class ExpectedToolCall:
    """Expected tool call specification."""
    name: str
    required_params: dict[str, Any] | None = None
    optional_params: dict[str, Any] | None = None
    response_contains: str | None = None


class MCPToolVerifier:
    """
    Verifier for MCP tool calls with flexible matching.

    Supports:
    - Exact tool name matching
    - Required parameter verification
    - Optional parameter verification (only checked if present)
    - Partial argument matching
    - Call order verification
    """

    @staticmethod
    def verify_tool_called(
        tool_calls: list[ToolCallRecord],
        expected_tool: str,
    ) -> ToolCallRecord:
        """
        Verify a specific tool was called.

        Returns the matching tool call for further verification.
        Raises AssertionError if tool was not called.
        """
        matching = [tc for tc in tool_calls if tc.name == expected_tool]

        if not matching:
            called_tools = [tc.name for tc in tool_calls]
            raise AssertionError(
                f"Tool '{expected_tool}' was not called. "
                f"Called tools: {called_tools}"
            )

        return matching[0]

    @staticmethod
    def verify_parameters(
        tool_call: ToolCallRecord,
        expected_params: dict[str, Any],
        strict: bool = False,
    ) -> None:
        """
        Verify tool was called with expected parameters.

        Args:
            tool_call: The tool call to verify
            expected_params: Parameters that must be present with these values
            strict: If True, no extra parameters allowed
        """
        actual_args = tool_call.args

        for param, expected_value in expected_params.items():
            if param not in actual_args:
                raise AssertionError(
                    f"Parameter '{param}' not found in tool call '{tool_call.name}'. "
                    f"Actual parameters: {list(actual_args.keys())}"
                )

            actual_value = actual_args[param]
            if actual_value != expected_value:
                raise AssertionError(
                    f"Parameter '{param}' has value '{actual_value}', "
                    f"expected '{expected_value}'"
                )

        if strict:
            extra_params = set(actual_args.keys()) - set(expected_params.keys())
            if extra_params:
                raise AssertionError(
                    f"Unexpected parameters in tool call: {extra_params}"
                )

    @staticmethod
    def verify_optional_parameters(
        tool_call: ToolCallRecord,
        optional_params: dict[str, Any],
    ) -> None:
        """
        Verify optional parameters IF they are present.

        Only checks parameters that exist in the actual call.
        Does not fail if optional params are missing.
        """
        actual_args = tool_call.args

        for param, expected_value in optional_params.items():
            if param in actual_args:
                actual_value = actual_args[param]
                if actual_value != expected_value:
                    raise AssertionError(
                        f"Optional parameter '{param}' has value '{actual_value}', "
                        f"expected '{expected_value}'"
                    )

    @staticmethod
    def verify_tool_not_called(
        tool_calls: list[ToolCallRecord],
        tool_name: str,
    ) -> None:
        """Verify a specific tool was NOT called."""
        called_names = [tc.name for tc in tool_calls]
        if tool_name in called_names:
            raise AssertionError(
                f"Tool '{tool_name}' should not have been called"
            )

    @staticmethod
    def verify_call_order(
        tool_calls: list[ToolCallRecord],
        expected_order: list[str],
    ) -> None:
        """Verify tools were called in a specific order."""
        actual_order = [tc.name for tc in tool_calls]

        if actual_order != expected_order:
            raise AssertionError(
                f"Tool call order mismatch.\n"
                f"Expected: {expected_order}\n"
                f"Actual: {actual_order}"
            )

    @staticmethod
    def verify_response_contains(
        tool_call: ToolCallRecord,
        expected_substring: str,
    ) -> None:
        """Verify tool response contains expected content."""
        result_str = str(tool_call.result)
        if expected_substring not in result_str:
            raise AssertionError(
                f"Tool response does not contain '{expected_substring}'. "
                f"Actual response: {result_str[:200]}..."
            )
```

#### 2. MCP Step Definitions
**File**: `bdd_tests/tests/step_defs/mcp_steps.py`

```python
"""
BDD step definitions for MCP tool verification.
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from src.mcp_verifier import MCPToolVerifier

# Load feature file
scenarios('../features/mcp_tools.feature')


# ============================================================================
# GIVEN Steps
# ============================================================================

@given(parsers.parse('the expected tool is "{tool_name}"'))
def set_expected_tool(test_context, tool_name):
    """Set the expected tool for verification."""
    test_context["expected_tool"] = tool_name


@given(parsers.parse('the expected tool parameters are:'))
def set_expected_params_table(test_context, datatable):
    """
    Set expected parameters from a Gherkin data table.

    Example:
        | city  | Ocean City |
        | state | NJ         |
    """
    params = {}
    for row in datatable:
        params[row[0]] = row[1]
    test_context["expected_params"] = params


# ============================================================================
# WHEN Steps
# ============================================================================

@when(parsers.parse('the user says "{prompt}"'))
def user_sends_prompt(test_context, agent_wrapper, prompt):
    """
    Send a prompt to the agent and capture the response.

    Uses mock_date from test_context if set.
    """
    import asyncio

    mock_date = test_context.get("mock_date")

    # Run the agent
    loop = asyncio.get_event_loop()
    response = loop.run_until_complete(
        agent_wrapper.run(prompt, mock_date=mock_date)
    )

    test_context["user_prompt"] = prompt
    test_context["agent_response"] = response
    test_context["tool_calls"] = response.tool_calls


@when('the agent processes the request')
def agent_processes(test_context):
    """Placeholder for scenarios where agent already processed."""
    pass


# ============================================================================
# THEN Steps - Tool Verification
# ============================================================================

@then(parsers.parse('the agent should call "{tool_name}"'))
def verify_tool_called(test_context, tool_name):
    """Verify that a specific tool was called."""
    tool_calls = test_context.get("tool_calls", [])
    verifier = MCPToolVerifier()

    tool_call = verifier.verify_tool_called(tool_calls, tool_name)
    test_context["verified_tool_call"] = tool_call


@then(parsers.parse('the agent should not call "{tool_name}"'))
def verify_tool_not_called(test_context, tool_name):
    """Verify that a specific tool was NOT called."""
    tool_calls = test_context.get("tool_calls", [])
    verifier = MCPToolVerifier()
    verifier.verify_tool_not_called(tool_calls, tool_name)


@then('the tool parameters should include:')
def verify_tool_params_table(test_context, datatable):
    """
    Verify tool was called with expected parameters from data table.

    Example:
        | city  | Ocean City |
        | state | NJ         |
        | date  | 1/8/2025   |
    """
    tool_call = test_context.get("verified_tool_call")
    if not tool_call:
        raise AssertionError("No tool call to verify. Use 'the agent should call' step first.")

    expected_params = {}
    for row in datatable:
        expected_params[row[0]] = row[1]

    verifier = MCPToolVerifier()
    verifier.verify_parameters(tool_call, expected_params)


@then(parsers.parse('the tool parameter "{param}" should be "{value}"'))
def verify_single_param(test_context, param, value):
    """Verify a single tool parameter."""
    tool_call = test_context.get("verified_tool_call")
    if not tool_call:
        raise AssertionError("No tool call to verify.")

    verifier = MCPToolVerifier()
    verifier.verify_parameters(tool_call, {param: value})


@then(parsers.parse('the tool response should contain "{expected_text}"'))
def verify_tool_response_contains(test_context, expected_text):
    """Verify tool response contains expected text."""
    tool_call = test_context.get("verified_tool_call")
    if not tool_call:
        raise AssertionError("No tool call to verify.")

    verifier = MCPToolVerifier()
    verifier.verify_response_contains(tool_call, expected_text)


@then(parsers.parse('the tools should be called in order: {tool_list}'))
def verify_tool_order(test_context, tool_list):
    """
    Verify tools were called in specific order.

    Example: the tools should be called in order: search_tool, weather_tool
    """
    tool_calls = test_context.get("tool_calls", [])
    expected_order = [t.strip() for t in tool_list.split(",")]

    verifier = MCPToolVerifier()
    verifier.verify_call_order(tool_calls, expected_order)


# ============================================================================
# THEN Steps - Response Verification
# ============================================================================

@then(parsers.parse('the agent response should contain "{expected_text}"'))
def verify_response_contains(test_context, expected_text):
    """Verify agent response contains expected text."""
    response = test_context.get("agent_response")
    if not response:
        raise AssertionError("No agent response to verify.")

    if expected_text.lower() not in response.output.lower():
        raise AssertionError(
            f"Response does not contain '{expected_text}'. "
            f"Actual: {response.output[:200]}..."
        )


@then('the agent response should mention appropriate clothing')
def verify_clothing_mentioned(test_context):
    """Verify response mentions clothing-related terms."""
    response = test_context.get("agent_response")
    if not response:
        raise AssertionError("No agent response to verify.")

    clothing_terms = ["wear", "dress", "jacket", "coat", "shirt", "sweater",
                      "sweatshirt", "shorts", "pants", "umbrella", "warm", "cold"]

    response_lower = response.output.lower()
    found = any(term in response_lower for term in clothing_terms)

    if not found:
        raise AssertionError(
            f"Response does not mention clothing. "
            f"Actual: {response.output[:200]}..."
        )
```

#### 3. MCP Tools Feature File
**File**: `bdd_tests/features/mcp_tools.feature`

```gherkin
Feature: MCP Tool Verification
  As a developer
  I want to verify my AI agent calls MCP tools correctly
  So that I can ensure reliable tool interactions

  Background:
    Given the LLM evaluator uses model "gpt-4"
    And the default threshold is 0.7

  @mcp @weather
  Scenario: Weather tool with date calculation
    Given today is "1/7/2025"
    When the user says "What should I wear tomorrow to Ocean City, NJ"
    Then the agent should call "weather_tool"
    And the tool parameters should include:
      | city  | Ocean City |
      | state | NJ         |
      | date  | 1/8/2025   |
    And the agent response should mention appropriate clothing

  @mcp @weather
  Scenario: Weather tool with explicit date
    Given today is "1/7/2025"
    When the user says "What's the weather in Philadelphia, PA on January 10th"
    Then the agent should call "weather_tool"
    And the tool parameters should include:
      | city  | Philadelphia |
      | state | PA           |
      | date  | 1/10/2025    |

  @mcp @weather @optional_params
  Scenario: Weather tool accepts optional parameters
    Given today is "1/7/2025"
    When the user says "What should I wear tomorrow to Ocean City, NJ? Include wind info."
    Then the agent should call "weather_tool"
    And the tool parameter "city" should be "Ocean City"
    And the tool parameter "state" should be "NJ"
    # Optional parameters are verified only if present
    And the tool response should contain "wind"

  @mcp @negative
  Scenario: Agent should not call weather tool for non-weather questions
    Given today is "1/7/2025"
    When the user says "What is the capital of France?"
    Then the agent should not call "weather_tool"

  @mcp @multiple_tools
  Scenario: Multiple tool calls in sequence
    Given today is "1/7/2025"
    When the user says "Search for restaurants in Ocean City, NJ and check tomorrow's weather"
    Then the agent should call "search_tool"
    And the agent should call "weather_tool"
    And the tools should be called in order: search_tool, weather_tool
```

### Success Criteria:

#### Automated Verification:
- [x] MCP steps load without import errors: `python -c "from tests.step_defs.mcp_steps import *"`
- [x] Feature file parses correctly: `pytest --collect-only tests/step_defs/mcp_steps.py`
- [x] MCPToolVerifier unit tests pass: `pytest tests/test_mcp_verifier.py -v` (add unit tests)

#### Manual Verification:
- [ ] Run a single MCP scenario against your actual agent
- [ ] Verify tool_calls are correctly extracted from your agent's response
- [ ] Confirm date injection (prompt prefix) results in correct date calculation

**Implementation Note**: After completing this phase, run a real test scenario against your agent to verify tool call extraction works correctly. Adjust the agent_wrapper if needed based on your actual Pydantic AI agent's response format.

---

## Phase 3: Conversational Testing Support

### Overview
Implement multi-turn conversation testing where the agent asks clarifying questions and the user responds. Uses DeepEval's `ConversationalTestCase` and `Turn` classes.

### Changes Required:

#### 1. Conversation Steps
**File**: `bdd_tests/tests/step_defs/conversation_steps.py`

```python
"""
BDD step definitions for multi-turn conversation testing.
"""
import asyncio
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from deepeval.test_case import ConversationalTestCase, Turn

from src.mcp_verifier import MCPToolVerifier

# Load feature file
scenarios('../features/conversations.feature')


# ============================================================================
# GIVEN Steps
# ============================================================================

@given('a new conversation')
def start_new_conversation(test_context, agent_wrapper):
    """Initialize a new conversation."""
    test_context["conversation_turns"] = []
    test_context["tool_calls"] = []
    agent_wrapper.clear_history()


# ============================================================================
# WHEN Steps - Conversation Turns
# ============================================================================

@when(parsers.parse('the user says "{prompt}"'))
def conversation_user_turn(test_context, agent_wrapper, prompt):
    """
    User sends a message in the conversation.

    This step captures both the user message and agent response.
    """
    loop = asyncio.get_event_loop()
    mock_date = test_context.get("mock_date")

    # Add user turn
    test_context["conversation_turns"].append(
        Turn(role="user", content=prompt)
    )

    # Get agent response
    response = loop.run_until_complete(
        agent_wrapper.run(prompt, mock_date=mock_date)
    )

    # Track tool calls for this turn
    turn_tool_calls = agent_wrapper.get_mcp_tool_calls()

    # Add assistant turn with any tool calls
    test_context["conversation_turns"].append(
        Turn(
            role="assistant",
            content=response.output,
            mcp_tools_called=turn_tool_calls if turn_tool_calls else None,
        )
    )

    # Update overall tracking
    test_context["agent_response"] = response
    test_context["tool_calls"].extend(response.tool_calls)
    test_context["last_response"] = response.output


@when(parsers.parse('the user responds "{response}"'))
def user_follow_up(test_context, agent_wrapper, response):
    """User responds to agent's clarifying question."""
    # This is essentially the same as user_says but semantically different
    conversation_user_turn(test_context, agent_wrapper, response)


# ============================================================================
# THEN Steps - Conversation Verification
# ============================================================================

@then(parsers.parse('the agent should ask about "{topic}"'))
def verify_agent_asks(test_context, topic):
    """Verify agent asks a clarifying question about a topic."""
    last_response = test_context.get("last_response", "")

    # Check for question indicators and topic
    has_question = "?" in last_response
    mentions_topic = topic.lower() in last_response.lower()

    if not (has_question and mentions_topic):
        raise AssertionError(
            f"Expected agent to ask about '{topic}'. "
            f"Actual response: {last_response[:200]}..."
        )


@then(parsers.parse('the agent should ask "{question}"'))
def verify_exact_question(test_context, question):
    """Verify agent asks a specific question (flexible matching)."""
    last_response = test_context.get("last_response", "")

    # Normalize for comparison
    question_lower = question.lower()
    response_lower = last_response.lower()

    # Check if key words from expected question appear
    key_words = [w for w in question_lower.split() if len(w) > 3]
    matches = sum(1 for w in key_words if w in response_lower)

    if matches < len(key_words) * 0.5:  # At least 50% of key words
        raise AssertionError(
            f"Expected agent to ask something like '{question}'. "
            f"Actual response: {last_response[:200]}..."
        )


@then('the conversation should have {count:d} turns')
def verify_turn_count(test_context, count):
    """Verify the conversation has expected number of turns."""
    turns = test_context.get("conversation_turns", [])
    actual_count = len(turns)

    if actual_count != count:
        raise AssertionError(
            f"Expected {count} turns, got {actual_count}. "
            f"Turns: {[t.role for t in turns]}"
        )


@then(parsers.parse('after the conversation, the tool "{tool_name}" should have been called'))
def verify_tool_called_in_conversation(test_context, tool_name):
    """Verify a tool was called at some point in the conversation."""
    tool_calls = test_context.get("tool_calls", [])
    verifier = MCPToolVerifier()

    tool_call = verifier.verify_tool_called(tool_calls, tool_name)
    test_context["verified_tool_call"] = tool_call


@then('the final tool call parameters should include:')
def verify_final_tool_params(test_context, datatable):
    """Verify the most recent tool call has expected parameters."""
    tool_calls = test_context.get("tool_calls", [])

    if not tool_calls:
        raise AssertionError("No tool calls in conversation.")

    # Get the last tool call
    last_call = tool_calls[-1]

    expected_params = {}
    for row in datatable:
        expected_params[row[0]] = row[1]

    verifier = MCPToolVerifier()
    verifier.verify_parameters(last_call, expected_params)


@then(parsers.parse('the final agent response should contain "{expected_text}"'))
def verify_final_response(test_context, expected_text):
    """Verify the final agent response contains expected text."""
    last_response = test_context.get("last_response", "")

    if expected_text.lower() not in last_response.lower():
        raise AssertionError(
            f"Final response does not contain '{expected_text}'. "
            f"Actual: {last_response[:200]}..."
        )
```

#### 2. Conversations Feature File
**File**: `bdd_tests/features/conversations.feature`

```gherkin
Feature: Conversational MCP Tool Usage
  As a developer
  I want to test multi-turn conversations where the agent gathers information
  So that I can verify correct tool usage with incomplete initial information

  Background:
    Given the LLM evaluator uses model "gpt-4"
    And the default threshold is 0.7

  @conversation @weather
  Scenario: Agent asks for location when not provided
    Given today is "1/7/2025"
    And a new conversation
    When the user says "I'm visiting my mom tomorrow, What should I wear?"
    Then the agent should ask about "location"
    When the user responds "Ocean City, NJ"
    Then after the conversation, the tool "weather_tool" should have been called
    And the final tool call parameters should include:
      | city  | Ocean City |
      | state | NJ         |
      | date  | 1/8/2025   |
    And the final agent response should mention appropriate clothing

  @conversation @weather
  Scenario: Agent asks clarifying question about date
    Given today is "1/7/2025"
    And a new conversation
    When the user says "What should I wear when I visit Philadelphia?"
    Then the agent should ask about "when"
    When the user responds "Next Monday"
    Then after the conversation, the tool "weather_tool" should have been called
    And the tool parameter "city" should be "Philadelphia"

  @conversation @multi_turn
  Scenario: Three-turn conversation with clarifications
    Given today is "1/7/2025"
    And a new conversation
    When the user says "Help me plan what to pack"
    Then the agent should ask about "destination"
    When the user responds "I'm going to the beach"
    Then the agent should ask about "location"
    When the user responds "Ocean City, NJ, this weekend"
    Then after the conversation, the tool "weather_tool" should have been called
    And the conversation should have 6 turns

  @conversation @no_tool_needed
  Scenario: Conversation resolved without tool call
    Given today is "1/7/2025"
    And a new conversation
    When the user says "What's the best way to stay warm in winter?"
    Then the agent should not call "weather_tool"
    And the final agent response should contain "layer"
```

### Success Criteria:

#### Automated Verification:
- [ ] Conversation steps load: `python -c "from tests.step_defs.conversation_steps import *"`
- [ ] Feature file parses: `pytest --collect-only tests/step_defs/conversation_steps.py`
- [ ] Turn tracking works correctly (unit test)

#### Manual Verification:
- [ ] Run the "Agent asks for location" scenario against your actual agent
- [ ] Verify the agent correctly asks clarifying questions
- [ ] Confirm tool calls are captured across multiple turns

**Implementation Note**: Conversational testing depends on your agent's ability to ask clarifying questions. Test with your actual agent to verify this behavior exists before expecting all scenarios to pass.

---

## Phase 4: DeepEval Metrics Integration

### Overview
Integrate DeepEval's LLM-based evaluation metrics for comprehensive agent output assessment including answer relevancy, faithfulness, and custom criteria via GEval.

### Changes Required:

#### 1. DeepEval Step Definitions
**File**: `bdd_tests/tests/step_defs/deepeval_steps.py`

```python
"""
BDD step definitions for DeepEval metric evaluation.
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    GEval,
    MCPUseMetric,
)

scenarios('../features/deepeval_metrics.feature')


# ============================================================================
# GIVEN Steps - Evaluation Setup
# ============================================================================

@given(parsers.parse('the expected output is "{expected}"'))
def set_expected_output(test_context, expected):
    """Set expected output for comparison metrics."""
    test_context["expected_output"] = expected


@given('custom evaluation criteria:')
def set_custom_criteria(test_context, docstring):
    """
    Set custom GEval criteria from docstring.

    Example:
        Given custom evaluation criteria:
          '''
          - Provides accurate weather information
          - Suggests appropriate clothing
          - Is helpful and friendly
          '''
    """
    criteria_lines = [
        line.strip().lstrip('-').strip()
        for line in docstring.split('\n')
        if line.strip() and line.strip().startswith('-')
    ]
    test_context["custom_criteria"] = criteria_lines


@given(parsers.parse('retrieval context:'))
def set_retrieval_context(test_context, docstring):
    """Set retrieval context for faithfulness evaluation."""
    test_context["retrieval_context"] = [docstring.strip()]


# ============================================================================
# THEN Steps - DeepEval Metrics
# ============================================================================

@then(parsers.parse('the answer relevancy score should be at least {min_score:f}'))
def check_answer_relevancy(test_context, min_score, record_property):
    """
    Evaluate answer relevancy using DeepEval.

    Measures how well the response addresses the user's query.
    """
    response = test_context.get("agent_response")
    user_prompt = test_context.get("user_prompt")
    model = test_context.get("evaluator_model", "gpt-4")

    if not response or not user_prompt:
        raise AssertionError("No agent response or user prompt to evaluate.")

    test_case = LLMTestCase(
        input=user_prompt,
        actual_output=response.output,
    )

    metric = AnswerRelevancyMetric(
        threshold=min_score,
        model=model,
        include_reason=True,
    )

    metric.measure(test_case)

    # Record for reporting
    record_property("relevancy_score", metric.score)
    record_property("relevancy_reason", metric.reason)
    test_context["metrics"]["relevancy"] = metric.score

    assert metric.score >= min_score, \
        f"Relevancy {metric.score:.2f} < {min_score}: {metric.reason}"


@then(parsers.parse('the faithfulness score should be at least {min_score:f}'))
def check_faithfulness(test_context, min_score, record_property):
    """
    Evaluate faithfulness using DeepEval.

    Measures how well the response is grounded in the retrieval context.
    """
    response = test_context.get("agent_response")
    user_prompt = test_context.get("user_prompt")
    retrieval_context = test_context.get("retrieval_context", [])
    model = test_context.get("evaluator_model", "gpt-4")

    if not response or not user_prompt:
        raise AssertionError("No agent response or user prompt to evaluate.")

    if not retrieval_context:
        raise AssertionError("No retrieval context set. Use 'Given retrieval context:' step.")

    test_case = LLMTestCase(
        input=user_prompt,
        actual_output=response.output,
        retrieval_context=retrieval_context,
    )

    metric = FaithfulnessMetric(
        threshold=min_score,
        model=model,
        include_reason=True,
    )

    metric.measure(test_case)

    record_property("faithfulness_score", metric.score)
    record_property("faithfulness_reason", metric.reason)
    test_context["metrics"]["faithfulness"] = metric.score

    assert metric.score >= min_score, \
        f"Faithfulness {metric.score:.2f} < {min_score}: {metric.reason}"


@then(parsers.parse('the MCP use score should be at least {min_score:f}'))
def check_mcp_use(test_context, min_score, record_property, agent_wrapper):
    """
    Evaluate MCP tool usage using DeepEval's MCPUseMetric.

    Measures whether the agent selected appropriate tools.
    """
    response = test_context.get("agent_response")
    user_prompt = test_context.get("user_prompt")
    model = test_context.get("evaluator_model", "gpt-4")

    if not response or not user_prompt:
        raise AssertionError("No agent response or user prompt to evaluate.")

    test_case = agent_wrapper.create_test_case(
        user_input=user_prompt,
        agent_output=response.output,
    )

    metric = MCPUseMetric(
        threshold=min_score,
        include_reason=True,
    )

    metric.measure(test_case)

    record_property("mcp_use_score", metric.score)
    record_property("mcp_use_reason", metric.reason)
    test_context["metrics"]["mcp_use"] = metric.score

    assert metric.score >= min_score, \
        f"MCP Use {metric.score:.2f} < {min_score}: {metric.reason}"


@then(parsers.parse('the custom criteria score should be at least {min_score:f}'))
def check_custom_criteria(test_context, min_score, record_property):
    """
    Evaluate using custom GEval criteria.

    Requires 'Given custom evaluation criteria:' step to set criteria.
    """
    response = test_context.get("agent_response")
    user_prompt = test_context.get("user_prompt")
    criteria_steps = test_context.get("custom_criteria", [])
    model = test_context.get("evaluator_model", "gpt-4")

    if not response or not user_prompt:
        raise AssertionError("No agent response or user prompt to evaluate.")

    if not criteria_steps:
        raise AssertionError("No custom criteria set. Use 'Given custom evaluation criteria:' step.")

    test_case = LLMTestCase(
        input=user_prompt,
        actual_output=response.output,
        expected_output=test_context.get("expected_output"),
    )

    metric = GEval(
        name="Custom Criteria",
        criteria="Evaluate the response based on the following requirements",
        evaluation_steps=criteria_steps,
        threshold=min_score,
        model=model,
    )

    metric.measure(test_case)

    record_property("custom_criteria_score", metric.score)
    record_property("custom_criteria_reason", metric.reason)
    test_context["metrics"]["custom_criteria"] = metric.score

    assert metric.score >= min_score, \
        f"Custom criteria {metric.score:.2f} < {min_score}: {metric.reason}"


@then('the response should pass all quality checks')
def check_all_quality(test_context, record_property, agent_wrapper):
    """
    Run all applicable quality metrics.

    Combines relevancy, faithfulness (if context available), and MCP use.
    """
    response = test_context.get("agent_response")
    user_prompt = test_context.get("user_prompt")
    threshold = test_context.get("threshold", 0.7)
    model = test_context.get("evaluator_model", "gpt-4")

    if not response or not user_prompt:
        raise AssertionError("No agent response or user prompt to evaluate.")

    test_case = agent_wrapper.create_test_case(
        user_input=user_prompt,
        agent_output=response.output,
        retrieval_context=test_context.get("retrieval_context"),
    )

    # Always check relevancy
    relevancy = AnswerRelevancyMetric(threshold=threshold, model=model)
    relevancy.measure(test_case)
    record_property("relevancy_score", relevancy.score)

    results = {"relevancy": relevancy.score}

    # Check faithfulness if context available
    if test_context.get("retrieval_context"):
        faithfulness = FaithfulnessMetric(threshold=threshold, model=model)
        faithfulness.measure(test_case)
        record_property("faithfulness_score", faithfulness.score)
        results["faithfulness"] = faithfulness.score

    # Check MCP use if tools were available
    if agent_wrapper.get_mcp_tool_calls():
        mcp_use = MCPUseMetric(threshold=threshold)
        mcp_use.measure(test_case)
        record_property("mcp_use_score", mcp_use.score)
        results["mcp_use"] = mcp_use.score

    test_context["metrics"] = results

    # Assert all metrics pass
    for metric_name, score in results.items():
        assert score >= threshold, \
            f"{metric_name} score {score:.2f} below threshold {threshold}"
```

#### 2. DeepEval Feature File
**File**: `bdd_tests/features/deepeval_metrics.feature`

```gherkin
Feature: DeepEval Quality Metrics
  As a QA engineer
  I want to evaluate agent response quality using AI metrics
  So that I can ensure consistent, high-quality outputs

  Background:
    Given the LLM evaluator uses model "gpt-4"
    And the default threshold is 0.7

  @metrics @relevancy
  Scenario: Response relevancy for weather query
    Given today is "1/7/2025"
    When the user says "What should I wear tomorrow to Ocean City, NJ"
    Then the answer relevancy score should be at least 0.8

  @metrics @faithfulness
  Scenario: Response faithfulness to context
    Given today is "1/7/2025"
    And retrieval context:
      """
      Weather forecast for Ocean City, NJ on 1/8/2025:
      Temperature: 64F
      Wind: 10mph from Southwest
      Conditions: Partly cloudy
      """
    When the user says "What should I wear tomorrow to Ocean City, NJ"
    Then the faithfulness score should be at least 0.8
    And the agent response should contain "64"

  @metrics @mcp
  Scenario: MCP tool selection quality
    Given today is "1/7/2025"
    When the user says "What should I wear tomorrow to Ocean City, NJ"
    Then the MCP use score should be at least 0.7

  @metrics @custom
  Scenario: Custom evaluation criteria
    Given today is "1/7/2025"
    And custom evaluation criteria:
      """
      - Provides specific clothing recommendations
      - Mentions temperature or weather conditions
      - Is helpful and actionable
      - Does not include irrelevant information
      """
    When the user says "What should I wear tomorrow to Ocean City, NJ"
    Then the custom criteria score should be at least 0.75

  @metrics @comprehensive
  Scenario: All quality checks pass
    Given today is "1/7/2025"
    When the user says "What should I wear tomorrow to Ocean City, NJ"
    Then the response should pass all quality checks
```

### Success Criteria:

#### Automated Verification:
- [ ] DeepEval steps load: `python -c "from tests.step_defs.deepeval_steps import *"`
- [ ] Feature file parses: `pytest --collect-only tests/step_defs/deepeval_steps.py`
- [ ] Metrics record to pytest properties

#### Manual Verification:
- [ ] Run a metric scenario with valid OPENAI_API_KEY
- [ ] Verify scores are reasonable (0-1 range)
- [ ] Confirm metric reasons are helpful for debugging

**Implementation Note**: DeepEval metrics require an OpenAI API key (or compatible LLM endpoint). Tests will skip or use mock scores if no API key is available. Set OPENAI_API_KEY environment variable for full evaluation.

---

## Phase 5: S3/DVC Test Data Infrastructure

### Overview
Set up DVC with S3 backend for compliance-friendly test data storage. Test inputs and expected outputs are stored in S3 and fetched at runtime, with only pointer files in Git.

### Changes Required:

#### 1. Data Loader
**File**: `bdd_tests/src/data_loader.py`

```python
"""
Test data loading from S3/DVC for compliance-friendly test execution.

Test data is stored in S3 with DVC pointers in Git. This module handles
fetching data at runtime, caching, and providing fixtures for tests.
"""
import os
import json
from pathlib import Path
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError


class TestDataLoader:
    """
    Loads test data from S3 or local cache.

    Supports:
    - Direct S3 loading for Kubernetes execution
    - Local file loading for development
    - DVC-managed data versioning
    """

    def __init__(
        self,
        s3_bucket: str | None = None,
        s3_prefix: str = "test-data",
        local_data_path: Path | None = None,
    ):
        """
        Initialize data loader.

        Args:
            s3_bucket: S3 bucket name (from env var TEST_DATA_BUCKET if not provided)
            s3_prefix: Prefix/folder in S3 bucket
            local_data_path: Path to local data directory for development
        """
        self.s3_bucket = s3_bucket or os.environ.get("TEST_DATA_BUCKET")
        self.s3_prefix = s3_prefix
        self.local_data_path = local_data_path or Path("data")
        self._s3_client = None

    @property
    def s3_client(self):
        """Lazy-load S3 client."""
        if self._s3_client is None:
            self._s3_client = boto3.client("s3")
        return self._s3_client

    def _load_from_s3(self, key: str) -> dict[str, Any]:
        """Load JSON data from S3."""
        if not self.s3_bucket:
            raise ValueError(
                "S3 bucket not configured. Set TEST_DATA_BUCKET environment variable."
            )

        full_key = f"{self.s3_prefix}/{key}"

        try:
            response = self.s3_client.get_object(
                Bucket=self.s3_bucket,
                Key=full_key,
            )
            content = response["Body"].read().decode("utf-8")
            return json.loads(content)
        except ClientError as e:
            raise RuntimeError(
                f"Failed to load test data from S3: s3://{self.s3_bucket}/{full_key}"
            ) from e

    def _load_from_local(self, filename: str) -> dict[str, Any]:
        """Load JSON data from local file."""
        file_path = self.local_data_path / filename

        if not file_path.exists():
            raise FileNotFoundError(
                f"Test data file not found: {file_path}. "
                f"Run 'dvc pull' to fetch test data."
            )

        with open(file_path, "r") as f:
            return json.load(f)

    @lru_cache(maxsize=50)
    def load_test_cases(self, dataset_name: str) -> list[dict[str, Any]]:
        """
        Load test cases from a dataset.

        Args:
            dataset_name: Name of dataset file (without .json extension)

        Returns:
            List of test case dictionaries
        """
        filename = f"{dataset_name}.json"

        # Try S3 first (for Kubernetes), fall back to local
        if self.s3_bucket and os.environ.get("KUBERNETES_SERVICE_HOST"):
            data = self._load_from_s3(filename)
        else:
            data = self._load_from_local(filename)

        return data.get("test_cases", [])

    def load_expected_output(
        self,
        test_id: str,
        dataset_name: str = "expected_outputs",
    ) -> dict[str, Any]:
        """
        Load expected output for a specific test.

        Args:
            test_id: Unique identifier for the test case
            dataset_name: Name of expected outputs dataset

        Returns:
            Expected output dictionary
        """
        all_expectations = self.load_test_cases(dataset_name)

        for expectation in all_expectations:
            if expectation.get("id") == test_id:
                return expectation

        raise KeyError(f"No expected output found for test_id: {test_id}")

    def get_golden_dataset(self, category: str) -> list[dict[str, Any]]:
        """
        Load a golden dataset for a specific category.

        Golden datasets contain verified input/output pairs for regression testing.

        Args:
            category: Category name (e.g., "weather", "search", "conversation")

        Returns:
            List of golden test cases
        """
        return self.load_test_cases(f"golden/{category}")


# Singleton instance for convenience
_default_loader: TestDataLoader | None = None


def get_data_loader() -> TestDataLoader:
    """Get or create the default data loader instance."""
    global _default_loader
    if _default_loader is None:
        _default_loader = TestDataLoader()
    return _default_loader
```

#### 2. Data Loading Fixtures
**File**: `bdd_tests/tests/conftest.py` (add to existing)

```python
# Add to existing conftest.py

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
```

#### 3. Data Loading Steps
**File**: `bdd_tests/tests/step_defs/data_steps.py`

```python
"""
BDD step definitions for loading test data from S3/DVC.
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios


@given(parsers.parse('test cases are loaded from dataset "{dataset_name}"'))
def load_dataset(test_context, load_test_cases, dataset_name):
    """Load test cases from a named dataset."""
    test_cases = load_test_cases(dataset_name)
    test_context["test_cases"] = test_cases
    test_context["current_test_index"] = 0


@given(parsers.parse('expected output is loaded for test "{test_id}"'))
def load_expected(test_context, load_expected_output, test_id):
    """Load expected output for a specific test."""
    expected = load_expected_output(test_id)
    test_context["expected_output"] = expected.get("expected_output")
    test_context["expected_tool"] = expected.get("expected_tool")
    test_context["expected_params"] = expected.get("expected_params", {})


@when('the next test case is processed')
def process_next_test_case(test_context, agent_wrapper):
    """Process the next test case from the loaded dataset."""
    import asyncio

    test_cases = test_context.get("test_cases", [])
    index = test_context.get("current_test_index", 0)

    if index >= len(test_cases):
        raise AssertionError("No more test cases to process.")

    test_case = test_cases[index]
    test_context["current_test_case"] = test_case
    test_context["current_test_index"] = index + 1

    # Set up context from test case
    test_context["mock_date"] = test_case.get("mock_date")
    test_context["user_prompt"] = test_case.get("input")
    test_context["expected_output"] = test_case.get("expected_output")
    test_context["expected_tool"] = test_case.get("expected_tool")
    test_context["expected_params"] = test_case.get("expected_params", {})

    # Run the agent
    loop = asyncio.get_event_loop()
    response = loop.run_until_complete(
        agent_wrapper.run(
            test_case["input"],
            mock_date=test_case.get("mock_date"),
        )
    )

    test_context["agent_response"] = response
    test_context["tool_calls"] = response.tool_calls
```

#### 4. Sample Test Data Schema
**File**: `bdd_tests/data/test_cases_schema.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "test_cases": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "input"],
        "properties": {
          "id": {
            "type": "string",
            "description": "Unique test case identifier"
          },
          "input": {
            "type": "string",
            "description": "User prompt/input"
          },
          "mock_date": {
            "type": "string",
            "description": "Mock current date (e.g., '1/7/2025')"
          },
          "expected_tool": {
            "type": "string",
            "description": "Expected MCP tool to be called"
          },
          "expected_params": {
            "type": "object",
            "description": "Expected tool parameters"
          },
          "expected_output": {
            "type": "string",
            "description": "Expected agent response (for comparison)"
          },
          "retrieval_context": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Context for faithfulness evaluation"
          },
          "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Test tags for filtering"
          }
        }
      }
    }
  }
}
```

#### 5. DVC Configuration
**File**: `bdd_tests/.dvc/config`

```ini
[core]
    remote = s3remote
[remote "s3remote"]
    url = s3://your-bucket-name/dvc-cache
    region = us-east-1
```

**File**: `bdd_tests/data/.gitignore`

```
# Ignore actual data files (tracked by DVC)
*.json
!*_schema.json
```

#### 6. Sample DVC File
**File**: `bdd_tests/data/test_cases.json.dvc`

```yaml
outs:
- md5: abc123def456...
  size: 12345
  hash: md5
  path: test_cases.json
```

### Success Criteria:

#### Automated Verification:
- [ ] DVC initializes: `cd bdd_tests && dvc init`
- [ ] Data loader imports: `python -c "from src.data_loader import TestDataLoader"`
- [ ] Local data loading works: Create sample `data/test_cases.json` and load it
- [ ] S3 loading works with TEST_DATA_BUCKET set (integration test)

#### Manual Verification:
- [ ] Configure DVC remote: `dvc remote add -d s3remote s3://your-bucket/dvc-cache`
- [ ] Push sample test data: `dvc add data/test_cases.json && dvc push`
- [ ] Pull data on another machine: `dvc pull`
- [ ] Verify data loads correctly in test

**Implementation Note**: Replace `your-bucket-name` with your actual S3 bucket. Ensure IAM permissions allow the Kubernetes service account to read from the bucket.

---

## Phase 6: Elasticsearch Reporting

### Overview
Configure pytest-elk-reporter to stream test results to Elasticsearch with custom DeepEval metric scores for dashboard creation.

### Changes Required:

#### 1. Elasticsearch Configuration
**File**: `bdd_tests/pytest.ini` (update)

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --strict-markers
    --tb=short
markers =
    mcp: MCP tool verification tests
    conversation: Multi-turn conversation tests
    integration: Integration tests requiring live agent
bdd_features_base_dir = features/

# Elasticsearch reporting (enable when ES is available)
# es_address = elasticsearch.monitoring:9200
# es_index_name = bdd-test-results
# es_username = test_reporter
# es_password = ${ES_PASSWORD}
```

#### 2. Custom Result Reporter
**File**: `bdd_tests/src/elk_reporter.py`

```python
"""
Custom Elasticsearch reporter for DeepEval metrics.

Extends pytest-elk-reporter to include DeepEval metric scores in test results.
"""
import os
import json
from datetime import datetime
from typing import Any

from elasticsearch import Elasticsearch


class DeepEvalResultReporter:
    """
    Reports test results with DeepEval metrics to Elasticsearch.

    Complements pytest-elk-reporter by adding structured metric data.
    """

    def __init__(
        self,
        es_host: str | None = None,
        es_index: str = "bdd-test-results",
        es_username: str | None = None,
        es_password: str | None = None,
    ):
        """
        Initialize reporter.

        Args:
            es_host: Elasticsearch host (from ES_HOST env if not provided)
            es_index: Index name for test results
            es_username: Optional username for authentication
            es_password: Optional password for authentication
        """
        self.es_host = es_host or os.environ.get("ES_HOST", "localhost:9200")
        self.es_index = es_index
        self.es_username = es_username or os.environ.get("ES_USERNAME")
        self.es_password = es_password or os.environ.get("ES_PASSWORD")
        self._client = None

    @property
    def client(self) -> Elasticsearch:
        """Lazy-load Elasticsearch client."""
        if self._client is None:
            auth = None
            if self.es_username and self.es_password:
                auth = (self.es_username, self.es_password)

            self._client = Elasticsearch(
                [f"http://{self.es_host}"],
                basic_auth=auth,
            )
        return self._client

    def ensure_index_exists(self):
        """Create index with proper mapping if it doesn't exist."""
        if not self.client.indices.exists(index=self.es_index):
            mapping = {
                "mappings": {
                    "properties": {
                        "@timestamp": {"type": "date"},
                        "test_id": {"type": "keyword"},
                        "test_name": {"type": "keyword"},
                        "feature": {"type": "keyword"},
                        "scenario": {"type": "keyword"},
                        "outcome": {"type": "keyword"},
                        "duration_seconds": {"type": "float"},
                        "error_message": {"type": "text"},

                        # DeepEval metrics
                        "metrics": {
                            "type": "object",
                            "properties": {
                                "relevancy_score": {"type": "float"},
                                "faithfulness_score": {"type": "float"},
                                "mcp_use_score": {"type": "float"},
                                "custom_criteria_score": {"type": "float"},
                            }
                        },

                        # MCP tool tracking
                        "tools_called": {"type": "keyword"},
                        "tool_call_count": {"type": "integer"},

                        # Test metadata
                        "mock_date": {"type": "keyword"},
                        "user_prompt": {"type": "text"},
                        "agent_response": {"type": "text"},

                        # Execution context
                        "environment": {"type": "keyword"},
                        "git_commit": {"type": "keyword"},
                        "branch": {"type": "keyword"},
                    }
                }
            }
            self.client.indices.create(index=self.es_index, body=mapping)

    def report_test_result(
        self,
        test_id: str,
        test_name: str,
        outcome: str,
        duration: float,
        metrics: dict[str, float] | None = None,
        tool_calls: list[str] | None = None,
        test_context: dict[str, Any] | None = None,
        error_message: str | None = None,
    ):
        """
        Report a single test result to Elasticsearch.

        Args:
            test_id: Unique test identifier
            test_name: Human-readable test name
            outcome: Test outcome (passed, failed, skipped)
            duration: Test duration in seconds
            metrics: DeepEval metric scores
            tool_calls: List of MCP tools called
            test_context: Additional test context
            error_message: Error message if test failed
        """
        self.ensure_index_exists()

        context = test_context or {}

        doc = {
            "@timestamp": datetime.utcnow().isoformat(),
            "test_id": test_id,
            "test_name": test_name,
            "outcome": outcome,
            "duration_seconds": duration,
            "error_message": error_message,

            "metrics": metrics or {},
            "tools_called": tool_calls or [],
            "tool_call_count": len(tool_calls) if tool_calls else 0,

            "mock_date": context.get("mock_date"),
            "user_prompt": context.get("user_prompt"),
            "agent_response": context.get("agent_response", {}).get("output") if context.get("agent_response") else None,

            "environment": os.environ.get("TEST_ENV", "local"),
            "git_commit": os.environ.get("GIT_COMMIT"),
            "branch": os.environ.get("GIT_BRANCH"),
        }

        self.client.index(index=self.es_index, document=doc)

    def report_batch(self, results: list[dict[str, Any]]):
        """Report multiple test results in a single batch."""
        self.ensure_index_exists()

        actions = []
        for result in results:
            actions.append({"index": {"_index": self.es_index}})
            actions.append(result)

        if actions:
            self.client.bulk(body=actions)
```

#### 3. Pytest Hook for Reporting
**File**: `bdd_tests/tests/conftest.py` (add to existing)

```python
# Add to existing conftest.py

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
```

### Success Criteria:

#### Automated Verification:
- [ ] ELK reporter imports: `python -c "from src.elk_reporter import DeepEvalResultReporter"`
- [ ] Index creation works with local Elasticsearch
- [ ] Test results are indexed correctly

#### Manual Verification:
- [ ] Run tests with ES_HOST set and verify documents appear in Elasticsearch
- [ ] Verify metric scores are correctly captured
- [ ] Create a simple Kibana dashboard showing test results

**Implementation Note**: Elasticsearch must be accessible from the test environment. For Kubernetes, configure the ES_HOST to point to your Elasticsearch service.

---

## Phase 7: Kubernetes Deployment

### Overview
Create Kubernetes Job manifest for running tests in-cluster with proper access to S3, Elasticsearch, and the production agent.

### Changes Required:

#### 1. Test Job Manifest
**File**: `bdd_tests/k8s/test-job.yaml`

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: bdd-deepeval-tests
  labels:
    app: bdd-tests
    test-type: integration
spec:
  backoffLimit: 1
  activeDeadlineSeconds: 1800  # 30 minute timeout
  ttlSecondsAfterFinished: 3600  # Cleanup after 1 hour
  template:
    metadata:
      labels:
        app: bdd-tests
    spec:
      restartPolicy: Never
      serviceAccountName: test-runner

      containers:
      - name: pytest-runner
        image: your-registry/bdd-deepeval-tests:latest
        imagePullPolicy: Always

        command: ["pytest"]
        args:
          - "tests/"
          - "-v"
          - "--tb=short"
          - "--junitxml=/results/junit.xml"
          - "-m"
          - "not slow"

        env:
        # S3 test data access
        - name: TEST_DATA_BUCKET
          value: "your-test-data-bucket"
        - name: AWS_REGION
          value: "us-east-1"

        # Elasticsearch reporting
        - name: ES_HOST
          value: "elasticsearch.monitoring:9200"
        - name: ES_USERNAME
          valueFrom:
            secretKeyRef:
              name: elasticsearch-credentials
              key: username
        - name: ES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: elasticsearch-credentials
              key: password

        # OpenAI API for DeepEval metrics
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: openai-credentials
              key: api-key

        # Git metadata for reporting
        - name: GIT_COMMIT
          value: "${GIT_COMMIT}"
        - name: GIT_BRANCH
          value: "${GIT_BRANCH}"
        - name: TEST_ENV
          value: "kubernetes"

        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"

        volumeMounts:
        - name: results
          mountPath: /results

      volumes:
      - name: results
        emptyDir: {}
```

#### 2. Service Account
**File**: `bdd_tests/k8s/serviceaccount.yaml`

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: test-runner
  annotations:
    # For AWS IRSA (IAM Roles for Service Accounts)
    eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT_ID:role/test-runner-role
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: test-runner-role
rules:
# Add permissions to access agent service if needed
- apiGroups: [""]
  resources: ["services", "endpoints"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: test-runner-binding
subjects:
- kind: ServiceAccount
  name: test-runner
roleRef:
  kind: Role
  name: test-runner-role
  apiGroup: rbac.authorization.k8s.io
```

#### 3. Dockerfile
**File**: `bdd_tests/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy test code (no test data - loaded from S3)
COPY features/ ./features/
COPY tests/ ./tests/
COPY src/ ./src/
COPY pytest.ini ./

# Create results directory
RUN mkdir -p /results

# Default command
CMD ["pytest", "tests/", "-v", "--junitxml=/results/junit.xml"]
```

#### 4. CI/CD Integration (GitHub Actions)
**File**: `bdd_tests/.github/workflows/test.yaml`

```yaml
name: BDD DeepEval Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 3 * * *'  # Daily at 3 AM UTC

jobs:
  test-local:
    name: Run Local Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd bdd_tests
          pip install -e .

      - name: Run tests (mock mode)
        run: |
          cd bdd_tests
          pytest tests/ -v -m "not integration" --junitxml=results/junit.xml

      - name: Upload test results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: test-results
          path: bdd_tests/results/

  test-kubernetes:
    name: Run Kubernetes Tests
    runs-on: ubuntu-latest
    needs: test-local
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - name: Configure kubectl
        run: |
          echo "${{ secrets.KUBECONFIG }}" | base64 -d > $HOME/.kube/config

      - name: Build and push test image
        run: |
          cd bdd_tests
          docker build -t ${{ secrets.REGISTRY }}/bdd-deepeval-tests:${{ github.sha }} .
          docker push ${{ secrets.REGISTRY }}/bdd-deepeval-tests:${{ github.sha }}

      - name: Deploy test job
        run: |
          cd bdd_tests
          # Substitute environment variables
          export GIT_COMMIT=${{ github.sha }}
          export GIT_BRANCH=${{ github.ref_name }}
          envsubst < k8s/test-job.yaml | kubectl apply -f -

      - name: Wait for job completion
        run: |
          kubectl wait --for=condition=complete job/bdd-deepeval-tests --timeout=1800s &
          completion_pid=$!
          kubectl wait --for=condition=failed job/bdd-deepeval-tests --timeout=1800s && exit 1 &
          failure_pid=$!

          # Stream logs while waiting
          kubectl logs -f job/bdd-deepeval-tests &

          wait -n $completion_pid $failure_pid

      - name: Cleanup
        if: always()
        run: |
          kubectl delete job bdd-deepeval-tests --ignore-not-found
```

### Success Criteria:

#### Automated Verification:
- [ ] Dockerfile builds: `docker build -t bdd-tests:test bdd_tests/`
- [ ] Kubernetes manifests are valid: `kubectl apply --dry-run=client -f bdd_tests/k8s/`
- [ ] GitHub Actions workflow syntax is valid

#### Manual Verification:
- [ ] Deploy to test Kubernetes cluster and verify job runs
- [ ] Confirm S3 test data is accessible from the Job
- [ ] Verify Elasticsearch receives test results
- [ ] Check agent is accessible from the Job pod

**Implementation Note**: Replace placeholder values (`your-registry`, `ACCOUNT_ID`, `your-test-data-bucket`) with your actual infrastructure values. Ensure IAM role has S3 read permissions for the test data bucket.

---

## Testing Strategy

### Unit Tests
- `MCPToolVerifier` assertion methods
- `TestDataLoader` S3/local loading
- `PydanticAITestWrapper` tool call extraction
- Date injection prompt formatting

### Integration Tests
- Full BDD scenarios against mock agent
- S3 data loading with moto mock
- Elasticsearch reporting with test instance

### End-to-End Tests (Kubernetes)
- Full scenarios against production agent
- Real S3 data loading
- Real Elasticsearch reporting
- CI/CD pipeline execution

### Manual Testing Steps
1. Run single MCP tool scenario: `pytest tests/step_defs/mcp_steps.py -k "weather" -v`
2. Run conversation scenario: `pytest tests/step_defs/conversation_steps.py -k "location" -v`
3. Run with DeepEval metrics: `OPENAI_API_KEY=sk-xxx pytest tests/ -m "metrics" -v`
4. Verify Elasticsearch results in Kibana
5. Deploy to Kubernetes and run full suite

## Performance Considerations

- **DeepEval metrics require API calls**: Each metric evaluation calls OpenAI API. Consider batching or running metric tests separately.
- **S3 data loading**: Use LRU cache to avoid repeated downloads. Session-scoped fixtures help.
- **Elasticsearch bulk indexing**: Batch test results for better performance.
- **Test parallelism**: Use `pytest-xdist` for parallel execution, but be careful with shared agent state.

## Migration Notes

- **From sample_code**: The sample code can be used as reference but should not be directly copied. This plan provides updated patterns.
- **Agent wrapper**: Must be customized based on your actual Pydantic AI agent's interface.
- **Test data**: Existing test data should be migrated to the new JSON schema and uploaded to S3.

## References

- Original requirements: `initial_prompt.md`
- Research document: `thoughts/shared/research/2026-01-20-bdd-deepeval-testing-framework.md`
- MCP capture example: `research/mcp_capture_example.py`
- Sample code: `sample_code/`
- DeepEval documentation: https://docs.confident-ai.com/
- pytest-bdd documentation: https://pytest-bdd.readthedocs.io/
- DVC documentation: https://dvc.org/doc
