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

scenarios('../../features/deepeval_metrics.feature')


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
