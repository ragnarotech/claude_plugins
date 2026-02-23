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
