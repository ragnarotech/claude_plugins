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
