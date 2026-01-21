"""
BDD step definitions for multi-turn conversation testing.
"""
import asyncio
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from deepeval.test_case import ConversationalTestCase, Turn

from src.mcp_verifier import MCPToolVerifier

# Load feature file
scenarios('../../features/conversations.feature')


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
