"""
Slash command interceptor: detects, parses, and structures slash commands
from raw user messages before they reach the agent.

# DECISION: Intercept at middleware (server), not in the frontend.
# Why:
#   1. Templates can contain privileged server-side context (user identity,
#      environment secrets) that must never be sent to the browser.
#   2. Tool availability can be verified against the registry before expansion.
#   3. Auth context (user identity from JWT/mTLS) can be injected server-side.
#   4. Logging / audit trail of command usage lives in one place.
# Production: Same pattern, but with JWT/mTLS identity propagation.
#   CopilotKit frontend only handles UX (autocomplete dropdown, arg hints).
# Standard: Similar to CopilotKit middleware hooks and GitHub Copilot prompt
#   rendering pipeline.
# Alternative: Considered frontend-only resolution (rejected: exposes templates
#   and potentially sensitive tool definitions to the client).

# DECISION: Positional argument parsing for MVP.
# Why: Simplest approach. First positional arg → first required variable.
#   Follows Claude Code's $1, $2 positional parameter convention.
# Production: Support named args (--variable=value) and quoted strings with
#   backslash escaping. Validate against the command's variable schema.
# Alternative: Named args from day one (rejected: over-engineering for MVP with
#   only a handful of commands).
"""

import re
import shlex
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# COMMAND_PATTERN: Matches /command-name with optional trailing arguments.
# Must anchor to start of the (stripped) string.
# Command name: starts with a letter, may contain letters, digits, and hyphens.
COMMAND_PATTERN = re.compile(r"^/([a-zA-Z][a-zA-Z0-9\-]*)\s*(.*)$", re.DOTALL)

# USE_SKILL_PATTERN: Matches the /use-skill <skill-name> meta-command.
# skill-name may contain letters, digits, hyphens (same convention as command names).
USE_SKILL_PATTERN = re.compile(r"^/use-skill\s+(\S+)$")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ParsedCommand:
    """Structured representation of a parsed slash command."""

    name: str
    raw_args: str
    positional_args: list[str] = field(default_factory=list)


@dataclass
class InterceptResult:
    """Result of attempting to parse a user message as a slash command."""

    is_command: bool
    is_meta_command: bool = False
    parsed: ParsedCommand | None = None

    # Populated only when is_meta_command is True.
    meta_action: str | None = None   # e.g. "use-skill"
    meta_value: str | None = None    # e.g. "code-review"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_slash_command(message: str) -> InterceptResult:
    """Parse a user message to detect and extract slash commands.

    Returns an InterceptResult indicating whether the message is:
      - A regular slash command (is_command=True, is_meta_command=False)
      - A meta-command like /use-skill (is_command=True, is_meta_command=True)
      - A plain message (is_command=False)

    # DECISION: Check for /use-skill before the generic command pattern.
    # Why: /use-skill is a system-level meta-command that should never be forwarded
    #   to the registry as a regular command lookup.
    """
    stripped = message.strip()

    # --- Meta-command: /use-skill ---
    skill_match = USE_SKILL_PATTERN.match(stripped)
    if skill_match:
        return InterceptResult(
            is_command=True,
            is_meta_command=True,
            meta_action="use-skill",
            meta_value=skill_match.group(1),
        )

    # --- Regular slash command ---
    cmd_match = COMMAND_PATTERN.match(stripped)
    if not cmd_match:
        return InterceptResult(is_command=False)

    name = cmd_match.group(1)
    raw_args = cmd_match.group(2).strip()

    # Parse positional args, respecting shell-style quoting.
    # DECISION: Use shlex for argument splitting.
    # Why: Handles quoted strings and escaped characters correctly, consistent
    #   with how Claude Code parses $1 … $9 positional parameters in shell prompts.
    # Production: Extend to support --name=value named args.
    try:
        positional = shlex.split(raw_args) if raw_args else []
    except ValueError:
        # shlex failed (e.g. unclosed quote) -- fall back to whitespace split.
        positional = raw_args.split() if raw_args else []

    return InterceptResult(
        is_command=True,
        is_meta_command=False,
        parsed=ParsedCommand(
            name=name,
            raw_args=raw_args,
            positional_args=positional,
        ),
    )


def map_positional_to_variables(
    positional: list[str],
    variables: list[dict],
) -> dict:
    """Map positional arguments to named variables based on declaration order.

    Only required variables are mapped; optional variables that have no
    corresponding positional argument are omitted (the registry will use
    their defaults).

    # DECISION: First positional arg → first required variable, etc.
    # This mimics how Claude Code handles $1, $2 positional parameters.
    # Production: Support named args (--var=value) alongside positional args.
    #   Validate types (string/number/select) against the variable schema.

    Example:
        variables = [{"name": "ticket_number", "required": True}]
        positional = ["PROJ-1234"]
        → {"ticket_number": "PROJ-1234"}
    """
    result: dict[str, str] = {}
    required_vars = [v for v in variables if v.get("required", True)]
    for i, var in enumerate(required_vars):
        if i < len(positional):
            result[var["name"]] = positional[i]
    return result
