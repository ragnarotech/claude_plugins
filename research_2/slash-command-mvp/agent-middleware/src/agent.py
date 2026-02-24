"""
Pydantic AI agent definition and agentic loop implementation.

# DECISION: Pydantic AI agent with Anthropic model.
# Why: Pydantic AI provides a clean async agent interface, structured outputs,
#   and tool registration. Anthropic Claude is the underlying LLM.
# Production: Same, but with model selection per command type -- some commands
#   (e.g., summarisation) may use a smaller/faster model (Haiku) to reduce cost,
#   while reasoning-heavy commands (e.g., incident analysis) use Sonnet or Opus.
# Standard: AG-UI compatible via CopilotKit Python SDK wrapper.
# Alternative: Considered LangChain (too heavy, abstractions leak), direct
#   Anthropic SDK only (too low-level, no structured output support), and
#   LlamaIndex (no native CopilotKit integration).

# DECISION: Simple tool-calling loop instead of full Pydantic AI agent for MVP.
# Why: Full Pydantic AI + CopilotKit integration requires significant boilerplate
#   and version-specific adapter code. For MVP, a direct Anthropic API call with
#   a manual tool-calling loop is simpler, more transparent for documentation,
#   and easier to test.
# Production: Use the full Pydantic AI agent with pydantic_ai.tools decorators,
#   a proper AG-UI streaming adapter, and structured result types (pydantic models).
# Standard: Follows Anthropic tool_use pattern documented at:
#   https://docs.anthropic.com/en/docs/build-with-claude/tool-use

# MCP_MAPPING: The tools list passed to client.messages.create() is the
#   Anthropic-side representation of MCP tool definitions.
#   tool["name"] must match a key in TOOL_REGISTRY (src/mcp_tools/tool_registry.py).
#   In production with real MCP servers, this list is generated dynamically by
#   calling tools/list on each MCP server at agent startup.
"""

import anthropic
import json

from .config import settings
from .mcp_tools.tool_registry import execute_tool
from .skills_context import skills_context

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """You are a helpful development assistant integrated into an engineering team's workflow.

You have access to mock Jira and Git tools for development tasks. When you receive a structured task prompt, execute it faithfully using the available tools.

Available tools:
- jira_get_ticket(ticket_number): Fetch Jira ticket details
- jira_update_ticket(ticket_number, fields): Update Jira ticket fields
- jira_list_tickets(): List open tickets
- git_list_commits(limit): List recent git commits
- git_create_pr(title, description, base_branch, head_branch): Create a pull request

Always be concise but thorough. Format responses with clear headings and bullet points where appropriate."""

# Anthropic API tool schema definitions.
# DECISION: Tool schemas defined statically in agent.py.
# Why: The mock tool set is fixed for MVP; static definitions are easier to read
#   than dynamically generated ones.
# Production: Generate these schemas from MCP server tools/list responses at startup,
#   cache them, and refresh when the MCP server version changes.
TOOLS: list[dict] = [
    {
        "name": "jira_get_ticket",
        "description": "Fetch details of a Jira ticket by ticket number",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_number": {
                    "type": "string",
                    "description": "Jira ticket ID (e.g., PROJ-1234)",
                }
            },
            "required": ["ticket_number"],
        },
    },
    {
        "name": "jira_update_ticket",
        "description": "Update fields on a Jira ticket",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_number": {"type": "string"},
                "fields": {
                    "type": "object",
                    "description": "Fields to update (e.g., priority, assignee)",
                },
            },
            "required": ["ticket_number", "fields"],
        },
    },
    {
        "name": "jira_list_tickets",
        "description": "List open Jira tickets assigned to the current user",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "git_list_commits",
        "description": "List recent git commits",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max commits to return",
                    "default": 10,
                }
            },
            "required": [],
        },
    },
    {
        "name": "git_create_pr",
        "description": "Create a pull request",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "base_branch": {"type": "string", "default": "main"},
                "head_branch": {
                    "type": "string",
                    "default": "feature/auto-generated",
                },
            },
            "required": ["title", "description"],
        },
    },
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_system_prompt() -> str:
    """Build the full system prompt including any active skill context."""
    return BASE_SYSTEM_PROMPT + skills_context.get_system_prompt_addendum()


async def run_agent_with_tools(
    message: str,
    conversation_history: list[dict],
) -> str:
    """Run the agent with the given message using a manual Anthropic tool-calling loop.

    Args:
        message: The current user message (may be a resolved command prompt).
        conversation_history: Previous messages in the conversation (role/content pairs).

    Returns:
        The agent's final text response as a string.

    # DECISION: Agentic loop capped at 10 iterations.
    # Why: Prevents runaway loops if the model repeatedly calls tools without
    #   reaching a conclusion. In practice, the mock tools always return useful
    #   data, so 2-3 iterations is the norm.
    # Production: Make the limit configurable per command type; add telemetry
    #   (iteration count histogram) to detect pathological cases.

    # DECISION: Last 10 conversation messages included for context.
    # Why: Balances context richness against token cost. Older messages are
    #   usually irrelevant to the current command.
    # Production: Implement a sliding window or summarisation strategy
    #   (summarise messages older than N turns with a cheap model).
    """
    client = anthropic.Anthropic(api_key=settings.LLM_API_KEY)

    messages: list[dict] = []

    # Add recent conversation history (last 10 messages).
    for msg in conversation_history[-10:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    # Append the current (possibly resolved) message.
    messages.append({"role": "user", "content": message})

    system_prompt = get_system_prompt()

    # Agentic tool-calling loop.
    max_iterations = 10
    for _ in range(max_iterations):
        response = client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            tools=TOOLS,
        )

        if response.stop_reason == "end_turn":
            # Collect and concatenate all text blocks.
            text_content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text_content += block.text
            return text_content

        elif response.stop_reason == "tool_use":
            # Append the assistant turn (may contain text + tool_use blocks).
            messages.append({"role": "assistant", "content": response.content})

            # Execute all tool calls and collect results.
            # DECISION: Execute tool calls sequentially within each iteration.
            # Why: Mock tools are synchronous and fast; parallel execution would
            #   require async wrappers without meaningful benefit for MVP.
            # Production: Execute independent tool calls in parallel (asyncio.gather).
            tool_results: list[dict] = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, **block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )

            messages.append({"role": "user", "content": tool_results})

        else:
            # Unexpected stop reason (e.g. "max_tokens") -- exit the loop.
            break

    return "I encountered an issue processing your request. Please try again."
