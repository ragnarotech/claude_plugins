"""
Template resolution service for slash commands.

# DECISION: {{variable}} syntax for template placeholders (Handlebars-style).
# Why: Double-braces are visually distinct in prose, unlikely to appear in normal text,
#      and familiar to engineers who have used Helm, Ansible, or Handlebars.
# Production: Evaluate Jinja2 if control flow (loops, conditionals) is ever needed in
#             templates. For now simple substitution avoids pulling in a template engine.
# Standard: Handlebars / Mustache convention.
# Alternative: Rejected Jinja2 -- {%...%} blocks conflict with code snippets in templates;
#              rejected $VAR / ${VAR} -- looks like shell expansion, confuses users.
"""

import logging
import time
from datetime import datetime, timezone

from src.models import Command, CommandVariable, ResolvedCommand, ResolutionError

logger = logging.getLogger(__name__)

# INTEGRATION: Called by GET /api/v1/commands/{name}/resolve.
#              The agent-middleware forwards the ResolvedCommand directly to Claude's
#              /v1/messages endpoint; changes here affect the live agent behaviour.


def resolve_command(
    command: Command,
    arguments: dict,
    user_context: dict,
) -> ResolvedCommand | ResolutionError:
    """Resolve a command template with concrete arguments.

    Args:
        command:      The full Command record retrieved from the database.
        arguments:    Dict of variable_name -> value supplied by the caller (query params).
        user_context: Dict with at least ``user`` and ``env`` keys injected by the router.

    Returns:
        ResolvedCommand on success, ResolutionError if a required variable is missing.

    # DECISION: Return a union type rather than raising an exception.
    # Why: The router needs to distinguish resolution errors from unexpected 500s; a typed
    #      return value makes branching explicit and testable.
    # Production: Add a structured audit log entry for each resolution (user, command, args).
    # Alternative: Rejected HTTPException from this service layer -- violates separation of
    #              concerns; the service layer should not know about HTTP status codes.
    """
    t_start = time.monotonic()

    # ------------------------------------------------------------------
    # 1. Validate required variables
    # ------------------------------------------------------------------
    missing: list[CommandVariable] = []
    for var in command.variables:
        if var.required and var.name not in arguments:
            if var.default is None:
                missing.append(var)

    if missing:
        logger.warning(
            "Resolution failed for %s: missing variables %s",
            command.name,
            [v.name for v in missing],
        )
        return ResolutionError(
            code="MISSING_VARIABLE",
            message=(
                f"Required variable(s) not provided: "
                f"{', '.join(v.name for v in missing)}"
            ),
            command_name=command.name,
            required_variables=missing,
        )

    # ------------------------------------------------------------------
    # 2. Build the substitution map (explicit args override defaults)
    # ------------------------------------------------------------------
    # DECISION: Defaults from the variable definition are applied when the caller omits
    #           an optional variable. Explicit args always win.
    sub_map: dict[str, str] = {}
    for var in command.variables:
        if var.name in arguments:
            sub_map[var.name] = str(arguments[var.name])
        elif var.default is not None:
            sub_map[var.name] = var.default

    # ------------------------------------------------------------------
    # 3. Substitute {{variable}} placeholders
    # ------------------------------------------------------------------
    resolved_prompt = command.template
    for var_name, value in sub_map.items():
        resolved_prompt = resolved_prompt.replace(f"{{{{{var_name}}}}}", value)

    # ------------------------------------------------------------------
    # 4. Build system context string
    # ------------------------------------------------------------------
    user = user_context.get("user", "anonymous")
    env = user_context.get("env", "unknown")
    timestamp = datetime.now(timezone.utc).isoformat()

    # MCP_MAPPING: system_context is injected as the system prompt prefix when the
    #              agent-middleware calls Claude's /v1/messages.
    system_context = f"User: {user} | Env: {env} | Time: {timestamp}"

    # ------------------------------------------------------------------
    # 5. Build metadata
    # ------------------------------------------------------------------
    resolution_time_ms = round((time.monotonic() - t_start) * 1000, 2)
    metadata: dict = {
        "resolution_time_ms": resolution_time_ms,
        "command_id": command.id,
        "command_version": command.version,
        "variables_provided": list(sub_map.keys()),
        "resolved_at": timestamp,
    }

    logger.info(
        "Resolved command %s in %.2f ms", command.name, resolution_time_ms
    )

    return ResolvedCommand(
        command_name=command.name,
        resolved_prompt=resolved_prompt,
        system_context=system_context,
        required_tools=command.tools,
        original_command=command.template,
        metadata=metadata,
    )
