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
