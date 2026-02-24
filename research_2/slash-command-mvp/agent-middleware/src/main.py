"""
FastAPI application entry point for the Agent Middleware service.

This service is the bridge between:
  - The frontend chat UI (SSE consumer)
  - The Prompt Registry (command/skill resolution)
  - The Pydantic AI agent (LLM + tool execution)

# DECISION: Plain REST + SSE endpoint instead of CopilotKit runtime protocol.
# Why: CopilotKit 1.x runtime requires a LangGraph agent and specific SDK
#   integration. Our agent uses Pydantic AI directly, so a plain SSE chat
#   endpoint is simpler, fully testable with curl, and avoids protocol
#   mismatches.
# Production: Evaluate CopilotKit SDK once agent framework is standardised,
#   or adopt AG-UI protocol directly with proper event types.
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .agent import run_agent_with_tools
from .config import settings
from .interceptor import map_positional_to_variables, parse_slash_command
from .registry_client import registry_client
from .skills_context import skills_context


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle for the FastAPI application."""
    await registry_client.start()
    try:
        skills = await registry_client.list_skills()
        skills_context.set_available_skills(skills)
    except Exception as e:
        print(f"Warning: Could not load skills from registry: {e}")

    yield
    await registry_client.stop()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Agent Middleware", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "agent-middleware"}


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def sse_event(event_type: str, data: dict) -> str:
    """Format a single Server-Sent Event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def stream_agent_response(
    message: str,
    conversation_history: list[dict],
):
    """Stream the agent response as SSE events."""
    msg_id = str(uuid.uuid4())

    yield sse_event("message_start", {"messageId": msg_id, "role": "assistant"})

    try:
        response = await run_agent_with_tools(message, conversation_history)
        chunk_size = 50
        for i in range(0, len(response), chunk_size):
            chunk = response[i : i + chunk_size]
            yield sse_event("message_delta", {"messageId": msg_id, "delta": chunk})
            await asyncio.sleep(0.01)
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        yield sse_event("message_delta", {"messageId": msg_id, "delta": error_msg})

    yield sse_event("message_end", {"messageId": msg_id})
    yield sse_event("done", {})


async def stream_plain_text(text: str):
    """Stream a static string as SSE events (for confirmations / errors)."""
    msg_id = str(uuid.uuid4())
    yield sse_event("message_start", {"messageId": msg_id, "role": "assistant"})
    yield sse_event("message_delta", {"messageId": msg_id, "delta": text})
    yield sse_event("message_end", {"messageId": msg_id})
    yield sse_event("done", {})


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------


@app.post("/api/v1/chat")
async def chat_endpoint(request: Request):
    """Chat endpoint. Accepts messages, intercepts slash commands, streams response.

    Request body:
        {
            "messages": [
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."},
                ...
            ]
        }

    Response: SSE stream with events:
        message_start  {"messageId", "role"}
        message_delta  {"messageId", "delta"}
        message_end    {"messageId"}
        done           {}
    """
    body = await request.json()
    messages = body.get("messages", [])

    if not messages:
        return JSONResponse({"error": "No messages provided"}, status_code=400)

    # Find the last user message.
    user_messages = [m for m in messages if m.get("role") == "user"]
    if not user_messages:
        return JSONResponse({"error": "No user messages"}, status_code=400)

    last_message = user_messages[-1]
    user_content = last_message.get("content", "")
    # History = everything before the last user message.
    last_idx = len(messages) - 1 - next(
        i for i, m in enumerate(reversed(messages)) if m is last_message
    )
    conversation_history = messages[:last_idx]

    # ------------------------------------------------------------------
    # Step 1: Intercept slash commands
    # ------------------------------------------------------------------
    intercept_result = parse_slash_command(user_content)

    # ------------------------------------------------------------------
    # Branch A: Meta-command (/use-skill <name>)
    # ------------------------------------------------------------------
    if intercept_result.is_command and intercept_result.is_meta_command:
        skill_name = intercept_result.meta_value
        skill = await registry_client.get_skill(skill_name)

        if skill:
            skills_context.activate_skill(skill_name, skill["skill_md"])
            confirmation = (
                f"Activated skill: **{skill_name}**\n\n"
                f"{skill['description']}\n\n"
                f"This skill is now active and will guide my responses."
            )
        else:
            confirmation = (
                f"Skill '{skill_name}' not found. "
                f"Use `/api/v1/skills` to see available skills."
            )

        return StreamingResponse(
            stream_plain_text(confirmation),
            media_type="text/event-stream",
        )

    # ------------------------------------------------------------------
    # Branch B: Regular slash command (/command-name [args...])
    # ------------------------------------------------------------------
    elif intercept_result.is_command and intercept_result.parsed:
        cmd_name = intercept_result.parsed.name

        try:
            commands = await registry_client.list_commands()
            cmd_def = next((c for c in commands if c["name"] == cmd_name), None)
        except Exception:
            cmd_def = None

        if not cmd_def:
            error_msg = (
                f"Unknown command: `/{cmd_name}`\n\n"
                f"Type `/` to see available commands."
            )
            return StreamingResponse(
                stream_plain_text(error_msg),
                media_type="text/event-stream",
            )

        arguments = map_positional_to_variables(
            intercept_result.parsed.positional_args,
            cmd_def.get("variables", []),
        )

        resolved = await registry_client.resolve_command(
            name=cmd_name,
            arguments=arguments,
            user_context={"user": "andrew@company.com", "env": "dev"},
        )

        if "error" in resolved:
            error_info = resolved["error"]
            if isinstance(error_info, dict):
                error_msg = f"{error_info.get('message', 'Command resolution failed')}"
                if "required_variables" in error_info:
                    vars_list = ", ".join(
                        f"`{v['name']}`" for v in error_info["required_variables"]
                    )
                    error_msg += f"\n\nRequired parameters: {vars_list}"
            else:
                error_msg = str(error_info)

            return StreamingResponse(
                stream_plain_text(error_msg),
                media_type="text/event-stream",
            )

        resolved_message = resolved["resolved_prompt"]

        return StreamingResponse(
            stream_agent_response(resolved_message, conversation_history),
            media_type="text/event-stream",
        )

    # ------------------------------------------------------------------
    # Branch C: Plain text message -- pass through to the agent
    # ------------------------------------------------------------------
    else:
        matching_skills = skills_context.find_matching_skills(user_content)
        for skill_name in matching_skills:
            if skill_name not in skills_context._active_skills:
                try:
                    skill = await registry_client.get_skill(skill_name)
                    if skill:
                        skills_context.activate_skill(skill_name, skill["skill_md"])
                except Exception:
                    pass

        return StreamingResponse(
            stream_agent_response(user_content, conversation_history),
            media_type="text/event-stream",
        )
