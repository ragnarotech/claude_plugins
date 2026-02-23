# I've created a comprehensive example demonstrating how DeepEval verifies MCP tool calls and parameters. Here's what it covers:
# Key Sections:

# MCPServer Setup - Defining available tools with their schemas (matching what session.list_tools() returns)
# MCPToolCall Tracking - Capturing tool name, arguments, and results during agent execution using DeepEval's MCPToolCall class
# Single-Turn Verification - Testing a single input/output with tool call verification
# Multi-Turn Verification - Testing conversations where tools are called across multiple turns using ConversationalTestCase and Turn objects with mcp_tools_called
# Custom Verification Helpers - A MCPToolVerifier class for detailed assertions like:

# Partial argument matching
# Call order verification
# Argument type checking
# Negative assertions (tool NOT called)


# S3/DVC Integration Pattern - A SecureTestDataManager class showing how to load test expectations from external storage for compliance requirements

# Two Evaluation Approaches:

# LLM-as-Judge (requires OPENAI_API_KEY): Uses MCPUseMetric to evaluate tool selection quality and argument correctness with scores 0-1
# Deterministic assertions: Direct Python assertions for CI/CD pipelines without API costs

# The example runs successfully and demonstrates the patterns you'd need for your Kubernetes-based MCP server testing infrastructure.
"""
DeepEval MCP Tool Verification Example

This example demonstrates how to use DeepEval to verify that MCP tools were called
with the correct parameters. This is particularly useful for testing AI agents
that interact with MCP servers in Kubernetes or other environments.

Key concepts covered:
1. Defining MCPServer with available tools
2. Tracking MCPToolCall with name, args, and result
3. Using MCPUseMetric to evaluate tool selection and argument correctness
4. Single-turn and multi-turn evaluation patterns
5. Custom assertions for parameter verification
"""

import asyncio
import json
from typing import Any
from dataclasses import dataclass
from unittest.mock import MagicMock

# DeepEval imports
from deepeval import evaluate
from deepeval.metrics import MCPUseMetric
from deepeval.test_case import (
    LLMTestCase,
    ConversationalTestCase,
    Turn,
)
from deepeval.test_case.mcp import (
    MCPServer,
    MCPToolCall,
    MCPResourceCall,
)

# For BDD-style testing with pytest-bdd (Gherkin syntax)
# from pytest_bdd import given, when, then, scenario


# =============================================================================
# SECTION 1: Mock MCP Server Definition
# =============================================================================

# Simulated MCP tool definitions (what would come from session.list_tools())
AVAILABLE_TOOLS = [
    {
        "name": "search_documents",
        "description": "Search internal documents by query string",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "default": 10},
                "filters": {
                    "type": "object",
                    "properties": {
                        "date_from": {"type": "string"},
                        "date_to": {"type": "string"},
                        "document_type": {"type": "string"}
                    }
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_task",
        "description": "Create a new task in the task management system",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "assignee": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                "due_date": {"type": "string"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "get_user_info",
        "description": "Retrieve user information by user ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "include_permissions": {"type": "boolean", "default": False}
            },
            "required": ["user_id"]
        }
    }
]


# =============================================================================
# SECTION 2: Simulated MCP Client (mimics real MCP session behavior)
# =============================================================================

class MockMCPSession:
    """
    Simulates an MCP ClientSession for testing purposes.
    In production, this would be mcp.ClientSession from the MCP SDK.
    """
    
    def __init__(self, tools: list[dict]):
        self.tools = tools
        self.call_history: list[MCPToolCall] = []
    
    async def list_tools(self):
        """Return available tools (mimics session.list_tools())"""
        from mcp.types import Tool, ListToolsResult
        
        return ListToolsResult(tools=[
            Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"]
            ) for t in self.tools
        ])
    
    async def call_tool(self, tool_name: str, tool_args: dict):
        """
        Simulate calling an MCP tool and return a result.
        In production, this returns mcp.types.CallToolResult
        """
        from mcp.types import CallToolResult, TextContent
        
        # Simulate tool execution results
        results_data = {
            "search_documents": json.dumps({
                "documents": [
                    {"id": "doc1", "title": "Q3 Report", "relevance": 0.95},
                    {"id": "doc2", "title": "Meeting Notes", "relevance": 0.87}
                ],
                "total": 2
            }),
            "create_task": json.dumps({
                "task_id": "TASK-123",
                "status": "created",
                "url": "https://tasks.example.com/TASK-123"
            }),
            "get_user_info": json.dumps({
                "user_id": tool_args.get("user_id"),
                "name": "John Doe",
                "email": "john@example.com",
                "role": "developer"
            })
        }
        
        result_text = results_data.get(tool_name, "Unknown tool")
        result = CallToolResult(
            content=[TextContent(type="text", text=result_text)]
        )
        
        # Track the call for verification
        tool_call = MCPToolCall(
            name=tool_name,
            args=tool_args,
            result=result
        )
        self.call_history.append(tool_call)
        
        return result


# =============================================================================
# SECTION 3: Agent Wrapper (tracks MCP interactions for DeepEval)
# =============================================================================

class MCPAgentWrapper:
    """
    Wraps an AI agent to track MCP tool calls for DeepEval verification.
    This pattern allows you to capture all tool interactions during execution.
    """
    
    def __init__(self, session: MockMCPSession):
        self.session = session
        self.mcp_servers: list[MCPServer] = []
        self.tools_called: list[MCPToolCall] = []
        self.resources_called: list[MCPResourceCall] = []
    
    async def initialize(self):
        """Initialize and register MCP server with available tools"""
        tool_list = await self.session.list_tools()
        
        self.mcp_servers.append(MCPServer(
            server_name="test-mcp-server",
            transport="stdio",  # or "streamable-http" for HTTP transport
            available_tools=tool_list.tools,
        ))
    
    async def execute_tool(self, tool_name: str, tool_args: dict) -> dict:
        """
        Execute a tool and track the call for DeepEval.
        This is the key integration point for verification.
        """
        result = await self.session.call_tool(tool_name, tool_args)
        
        # Track for DeepEval verification
        self.tools_called.append(MCPToolCall(
            name=tool_name,
            args=tool_args,
            result=result
        ))
        
        return result
    
    def create_test_case(self, user_input: str, agent_output: str) -> LLMTestCase:
        """Create a DeepEval test case from the interaction"""
        return LLMTestCase(
            input=user_input,
            actual_output=agent_output,
            mcp_servers=self.mcp_servers,
            mcp_tools_called=self.tools_called,
        )


# =============================================================================
# SECTION 4: Single-Turn Evaluation Examples
# =============================================================================

async def example_single_turn_tool_verification():
    """
    Demonstrates verifying a single tool call with specific parameters.
    
    Scenario: User asks to search for Q3 reports, verify the agent called
    search_documents with correct parameters.
    """
    print("\n" + "="*70)
    print("EXAMPLE 1: Single-Turn Tool Verification")
    print("="*70)
    
    # Setup
    session = MockMCPSession(AVAILABLE_TOOLS)
    agent = MCPAgentWrapper(session)
    await agent.initialize()
    
    # Simulate agent execution
    user_input = "Find all Q3 reports from last month"
    
    # Agent decides to call search_documents (simulated decision)
    tool_args = {
        "query": "Q3 reports",
        "max_results": 10,
        "filters": {
            "date_from": "2024-09-01",
            "date_to": "2024-09-30",
            "document_type": "report"
        }
    }
    result = await agent.execute_tool("search_documents", tool_args)
    
    # Agent generates response
    agent_output = "I found 2 Q3 reports: 'Q3 Report' and 'Meeting Notes'"
    
    # Create test case for DeepEval
    test_case = agent.create_test_case(user_input, agent_output)
    
    print(f"\nUser Input: {user_input}")
    print(f"Agent Output: {agent_output}")
    print(f"\nTools Called:")
    for tc in agent.tools_called:
        print(f"  - {tc.name}: {json.dumps(tc.args, indent=4)}")
    
    # -------------------------------------------------------------------------
    # Option 1: Full LLM-based evaluation (requires OPENAI_API_KEY)
    # -------------------------------------------------------------------------
    # Uncomment to run with DeepEval's LLM-as-judge evaluation:
    #
    # mcp_use_metric = MCPUseMetric(
    #     threshold=0.5,  # Minimum score to pass (0-1)
    #     include_reason=True,  # Get explanation for the score
    # )
    # evaluate([test_case], [mcp_use_metric])
    
    # -------------------------------------------------------------------------
    # Option 2: Manual/deterministic verification (no API key needed)
    # -------------------------------------------------------------------------
    # This approach is useful for CI/CD pipelines where you want fast, 
    # deterministic tests without LLM API costs
    
    # Manual verification
    assert len(agent.tools_called) == 1, f"Expected 1 tool call, got {len(agent.tools_called)}"
    assert agent.tools_called[0].name == "search_documents", \
        f"Expected search_documents, got {agent.tools_called[0].name}"
    assert agent.tools_called[0].args["query"] == "Q3 reports", \
        f"Expected query='Q3 reports', got {agent.tools_called[0].args['query']}"
    assert agent.tools_called[0].args["filters"]["document_type"] == "report", \
        "Expected document_type filter to be 'report'"
    
    print("\n✅ Tool call verified: search_documents called with correct parameters")
    
    return test_case


# =============================================================================
# SECTION 5: Multi-Turn Evaluation Examples
# =============================================================================

async def example_multi_turn_tool_verification():
    """
    Demonstrates verifying tool calls across a multi-turn conversation.
    
    Scenario: User asks to create a task, then looks up assignee info.
    """
    print("\n" + "="*70)
    print("EXAMPLE 2: Multi-Turn Tool Verification")
    print("="*70)
    
    session = MockMCPSession(AVAILABLE_TOOLS)
    agent = MCPAgentWrapper(session)
    await agent.initialize()
    
    turns: list[Turn] = []
    
    # Turn 1: User requests task creation
    turns.append(Turn(role="user", content="Create a high priority task to review the Q3 budget"))
    
    # Agent calls create_task
    create_result = await agent.execute_tool("create_task", {
        "title": "Review Q3 budget",
        "priority": "high",
        "description": "Complete review of Q3 budget report"
    })
    
    turns.append(Turn(
        role="assistant",
        content="I've created task TASK-123 for reviewing the Q3 budget.",
        mcp_tools_called=[agent.tools_called[-1]]  # Attach tool call to this turn
    ))
    
    # Turn 2: User asks about a potential assignee
    turns.append(Turn(role="user", content="Who is user-456? Can they handle this?"))
    
    # Agent calls get_user_info
    user_result = await agent.execute_tool("get_user_info", {
        "user_id": "user-456",
        "include_permissions": True
    })
    
    turns.append(Turn(
        role="assistant", 
        content="User-456 is John Doe (john@example.com), a developer. They should be able to handle this task.",
        mcp_tools_called=[agent.tools_called[-1]]
    ))
    
    # Create ConversationalTestCase
    convo_test_case = ConversationalTestCase(
        turns=turns,
        mcp_servers=agent.mcp_servers
    )
    
    print("\nConversation Flow:")
    for i, turn in enumerate(turns):
        tools = getattr(turn, 'mcp_tools_called', [])
        tool_info = f" [Called: {[t.name for t in tools]}]" if tools else ""
        print(f"  {turn.role}: {turn.content}{tool_info}")
    
    # Verify tool calls
    assert len(agent.tools_called) == 2
    assert agent.tools_called[0].name == "create_task"
    assert agent.tools_called[0].args["priority"] == "high"
    assert agent.tools_called[1].name == "get_user_info"
    assert agent.tools_called[1].args["user_id"] == "user-456"
    
    print("\n✅ Multi-turn tool calls verified")
    
    return convo_test_case


# =============================================================================
# SECTION 6: Custom Parameter Verification Helpers
# =============================================================================

class MCPToolVerifier:
    """
    Custom helper class for detailed parameter verification.
    Useful when MCPUseMetric doesn't provide granular enough checks.
    """
    
    @staticmethod
    def verify_tool_called(
        tools_called: list[MCPToolCall],
        expected_tool: str,
        expected_args: dict | None = None,
        strict: bool = False
    ) -> bool:
        """
        Verify a specific tool was called with expected arguments.
        
        Args:
            tools_called: List of MCPToolCall from agent execution
            expected_tool: Name of tool that should have been called
            expected_args: Expected arguments (partial match by default)
            strict: If True, args must match exactly
        
        Returns:
            True if verification passes
        """
        matching_calls = [tc for tc in tools_called if tc.name == expected_tool]
        
        if not matching_calls:
            raise AssertionError(f"Tool '{expected_tool}' was not called. "
                               f"Called tools: {[tc.name for tc in tools_called]}")
        
        if expected_args is None:
            return True
        
        for call in matching_calls:
            if strict:
                if call.args == expected_args:
                    return True
            else:
                # Partial match - expected args should be subset
                if all(call.args.get(k) == v for k, v in expected_args.items()):
                    return True
        
        raise AssertionError(
            f"Tool '{expected_tool}' called but arguments don't match.\n"
            f"Expected: {expected_args}\n"
            f"Actual calls: {[tc.args for tc in matching_calls]}"
        )
    
    @staticmethod
    def verify_tool_not_called(
        tools_called: list[MCPToolCall],
        tool_name: str
    ) -> bool:
        """Verify a specific tool was NOT called"""
        called_names = [tc.name for tc in tools_called]
        if tool_name in called_names:
            raise AssertionError(f"Tool '{tool_name}' should not have been called")
        return True
    
    @staticmethod
    def verify_call_order(
        tools_called: list[MCPToolCall],
        expected_order: list[str]
    ) -> bool:
        """Verify tools were called in a specific order"""
        actual_order = [tc.name for tc in tools_called]
        
        if actual_order != expected_order:
            raise AssertionError(
                f"Tool call order mismatch.\n"
                f"Expected: {expected_order}\n"
                f"Actual: {actual_order}"
            )
        return True
    
    @staticmethod
    def verify_arg_type(
        tools_called: list[MCPToolCall],
        tool_name: str,
        arg_name: str,
        expected_type: type
    ) -> bool:
        """Verify an argument has the expected type"""
        for call in tools_called:
            if call.name == tool_name:
                arg_value = call.args.get(arg_name)
                if not isinstance(arg_value, expected_type):
                    raise AssertionError(
                        f"Argument '{arg_name}' in tool '{tool_name}' "
                        f"has type {type(arg_value).__name__}, expected {expected_type.__name__}"
                    )
        return True


async def example_custom_verification():
    """
    Demonstrates using custom verification helpers for detailed assertions.
    """
    print("\n" + "="*70)
    print("EXAMPLE 3: Custom Parameter Verification")
    print("="*70)
    
    session = MockMCPSession(AVAILABLE_TOOLS)
    agent = MCPAgentWrapper(session)
    await agent.initialize()
    
    # Simulate a workflow with multiple tool calls
    await agent.execute_tool("search_documents", {"query": "budget", "max_results": 5})
    await agent.execute_tool("create_task", {"title": "Review findings", "priority": "medium"})
    await agent.execute_tool("get_user_info", {"user_id": "user-123"})
    
    verifier = MCPToolVerifier()
    
    # Verify specific tool was called with partial args
    verifier.verify_tool_called(
        agent.tools_called,
        "search_documents",
        {"query": "budget"}  # Only check query, ignore max_results
    )
    print("✅ Verified: search_documents called with query='budget'")
    
    # Verify call order
    verifier.verify_call_order(
        agent.tools_called,
        ["search_documents", "create_task", "get_user_info"]
    )
    print("✅ Verified: Tools called in correct order")
    
    # Verify argument types
    verifier.verify_arg_type(
        agent.tools_called,
        "search_documents",
        "max_results",
        int
    )
    print("✅ Verified: max_results is an integer")
    
    # Verify tool NOT called
    verifier.verify_tool_not_called(agent.tools_called, "delete_user")
    print("✅ Verified: delete_user was NOT called")
    
    return agent.tools_called


# =============================================================================
# SECTION 7: pytest-bdd Integration (Gherkin/BDD Style)
# =============================================================================

# Example Gherkin feature file content (test_mcp.feature):
"""
Feature: MCP Tool Call Verification
  As a developer
  I want to verify my AI agent calls MCP tools correctly
  So that I can ensure reliable tool interactions

  Scenario: Search for documents
    Given an MCP agent with document search capabilities
    When the user asks "Find Q3 budget reports"
    Then the agent should call "search_documents"
    And the query parameter should contain "Q3 budget"
    And the max_results should be at most 20

  Scenario: Create task with priority
    Given an MCP agent with task management capabilities
    When the user asks "Create urgent task to fix the login bug"
    Then the agent should call "create_task"
    And the priority should be "high"
    And the title should contain "login bug"
"""

# pytest-bdd step definitions (would be in conftest.py or steps file):
"""
from pytest_bdd import given, when, then, parsers

@given('an MCP agent with document search capabilities')
def mcp_agent_with_search(request):
    session = MockMCPSession(AVAILABLE_TOOLS)
    agent = MCPAgentWrapper(session)
    asyncio.get_event_loop().run_until_complete(agent.initialize())
    request.node.agent = agent
    return agent

@when(parsers.parse('the user asks "{query}"'))
def user_asks(request, query):
    agent = request.node.agent
    # Simulate agent processing and tool selection
    # In real tests, this would call your actual agent
    pass

@then(parsers.parse('the agent should call "{tool_name}"'))
def verify_tool_called(request, tool_name):
    agent = request.node.agent
    called_tools = [tc.name for tc in agent.tools_called]
    assert tool_name in called_tools

@then(parsers.parse('the {param_name} parameter should contain "{expected_value}"'))
def verify_param_contains(request, param_name, expected_value):
    agent = request.node.agent
    # Find the parameter in the most recent call
    last_call = agent.tools_called[-1]
    actual_value = str(last_call.args.get(param_name, ""))
    assert expected_value in actual_value
"""


# =============================================================================
# SECTION 8: Integration with S3/DVC for Test Data (Compliance-Friendly)
# =============================================================================

class SecureTestDataManager:
    """
    Helper for loading test expectations from S3/DVC when you can't
    store sensitive test data in source control.
    
    This addresses compliance requirements by keeping test expectations
    (expected tool calls, parameters, etc.) in secure external storage.
    """
    
    def __init__(self, s3_bucket: str | None = None, dvc_remote: str | None = None):
        self.s3_bucket = s3_bucket
        self.dvc_remote = dvc_remote
    
    def load_expected_tool_calls(self, test_name: str) -> list[dict]:
        """
        Load expected tool calls from secure storage.
        
        In production, this would:
        1. Check DVC for tracked test data
        2. Pull from S3 if not cached locally
        3. Return expected tool call specifications
        """
        # Placeholder - in real implementation, load from S3/DVC
        expected_calls = {
            "test_document_search": [
                {
                    "tool": "search_documents",
                    "required_args": ["query"],
                    "expected_values": {"max_results": 10}
                }
            ],
            "test_task_creation": [
                {
                    "tool": "create_task",
                    "required_args": ["title", "priority"],
                    "expected_values": {}
                }
            ]
        }
        return expected_calls.get(test_name, [])
    
    def verify_against_expectations(
        self,
        tools_called: list[MCPToolCall],
        test_name: str
    ) -> bool:
        """Verify tool calls match stored expectations"""
        expectations = self.load_expected_tool_calls(test_name)
        
        for exp in expectations:
            matching_calls = [tc for tc in tools_called if tc.name == exp["tool"]]
            
            if not matching_calls:
                raise AssertionError(f"Expected tool '{exp['tool']}' was not called")
            
            for call in matching_calls:
                # Verify required args are present
                for required_arg in exp.get("required_args", []):
                    if required_arg not in call.args:
                        raise AssertionError(
                            f"Required argument '{required_arg}' missing from {exp['tool']}"
                        )
                
                # Verify expected values
                for arg_name, expected_val in exp.get("expected_values", {}).items():
                    actual_val = call.args.get(arg_name)
                    if actual_val != expected_val:
                        raise AssertionError(
                            f"Argument '{arg_name}' has value {actual_val}, expected {expected_val}"
                        )
        
        return True


# =============================================================================
# SECTION 9: Complete Test Suite Example
# =============================================================================

async def run_complete_test_suite():
    """
    Demonstrates running a complete test suite with DeepEval.
    """
    print("\n" + "="*70)
    print("COMPLETE TEST SUITE")
    print("="*70)
    
    test_cases = []
    
    # Collect test cases
    test_cases.append(await example_single_turn_tool_verification())
    test_cases.append(await example_multi_turn_tool_verification())
    await example_custom_verification()
    
    print("\n" + "-"*70)
    print("TEST SUMMARY")
    print("-"*70)
    print(f"Total test cases collected: {len(test_cases)}")
    print("\nTo run with DeepEval evaluation (requires OPENAI_API_KEY):")
    print("  from deepeval import evaluate")
    print("  from deepeval.metrics import MCPUseMetric")
    print("  evaluate(test_cases, [MCPUseMetric()])")
    
    # Example of full evaluation (commented - requires API key)
    """
    from deepeval.metrics import MCPUseMetric, MCPTaskCompletionMetric
    
    metrics = [
        MCPUseMetric(threshold=0.5, include_reason=True),
        MCPTaskCompletionMetric(threshold=0.5),
    ]
    
    # Run evaluation
    evaluate(test_cases, metrics)
    """
    
    print("\n✅ All verification examples completed successfully!")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    asyncio.run(run_complete_test_suite())