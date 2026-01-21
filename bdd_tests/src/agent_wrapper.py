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
