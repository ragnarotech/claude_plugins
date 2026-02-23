"""
BDD step definitions for MCP tool verification.
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from src.mcp_verifier import MCPToolVerifier

# Load feature file
scenarios('../../features/mcp_tools.feature')


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
