"""
Aggregates all mock MCP tools into a single registry for the agentic loop.

# DECISION: Tools registered as a simple dict for MVP.
# Why: Zero framework overhead. The agentic loop in agent.py calls execute_tool()
#   by name, which dispatches directly to the Python function.
# Production: Use proper MCP tool registration with full JSON Schema definitions,
#   input validation (pydantic models per tool), auth checks per tool invocation,
#   and rate limiting. Tools would be served via MCP server processes.
# Standard: MCP tools protocol -- tool names here must match the "name" field in
#   the Anthropic API tools list passed to /v1/messages.
# Alternative: Considered a class-based registry with decorators (@tool), but
#   adds boilerplate without benefit for the 5-tool MVP scope.

# MCP_MAPPING: TOOL_REGISTRY keys are the canonical tool names.
#   These names appear in three places that must stay in sync:
#   1. This dict (dispatch)
#   2. src/agent.py tools list (Anthropic API schema)
#   3. prompt-registry command records' "tools" field (command metadata)
"""

from .mock_git import git_create_pr, git_list_commits
from .mock_jira import jira_get_ticket, jira_list_tickets, jira_update_ticket

TOOL_REGISTRY: dict[str, callable] = {
    "jira_get_ticket": jira_get_ticket,
    "jira_update_ticket": jira_update_ticket,
    "jira_list_tickets": jira_list_tickets,
    "git_list_commits": git_list_commits,
    "git_create_pr": git_create_pr,
}


def execute_tool(name: str, **kwargs) -> dict:
    """Execute a registered tool by name with keyword arguments.

    Returns the tool's result dict, or an error dict if the tool is unknown
    or raises an exception.

    # DECISION: Exceptions caught at this boundary and returned as error dicts.
    # Why: The agentic loop serialises results to JSON; unhandled exceptions would
    #   crash the loop. Surfacing errors as structured dicts lets the LLM recover.
    # Production: Add per-tool timeout, structured logging of tool calls and results,
    #   and metrics (tool_invocation_count, tool_error_count) for observability.
    """
    tool = TOOL_REGISTRY.get(name)
    if not tool:
        return {
            "error": f"Unknown tool: {name}. Available: {list(TOOL_REGISTRY.keys())}"
        }
    try:
        return tool(**kwargs)
    except Exception as e:
        return {"error": f"Tool execution failed: {str(e)}"}
