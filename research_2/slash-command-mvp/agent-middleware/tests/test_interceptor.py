"""
Tests for the slash command interceptor.

# DECISION: Unit tests with no external dependencies (no network, no DB, no LLM).
# Why: The interceptor is pure Python logic; it should be fully testable in isolation.
#   Fast tests encourage running them frequently.
# Standard: pytest with plain assert statements (no unittest-style assertions).
# Coverage targets: all branches of parse_slash_command and map_positional_to_variables.
"""

import pytest

from src.interceptor import (
    InterceptResult,
    ParsedCommand,
    map_positional_to_variables,
    parse_slash_command,
)


# ---------------------------------------------------------------------------
# parse_slash_command — happy paths
# ---------------------------------------------------------------------------


def test_detect_triage_ticket_command():
    """A command with one positional argument is parsed correctly."""
    result = parse_slash_command("/triage-ticket PROJ-1234")
    assert result.is_command
    assert not result.is_meta_command
    assert result.parsed is not None
    assert result.parsed.name == "triage-ticket"
    assert result.parsed.positional_args == ["PROJ-1234"]
    assert result.parsed.raw_args == "PROJ-1234"


def test_detect_parameterless_command():
    """A command with no arguments produces an empty positional_args list."""
    result = parse_slash_command("/list-my-tickets")
    assert result.is_command
    assert not result.is_meta_command
    assert result.parsed is not None
    assert result.parsed.name == "list-my-tickets"
    assert result.parsed.positional_args == []
    assert result.parsed.raw_args == ""


def test_command_with_multiple_positional_args():
    """Multiple space-separated args are split correctly."""
    result = parse_slash_command("/create-pr main feature/branch")
    assert result.is_command
    assert result.parsed.positional_args == ["main", "feature/branch"]


def test_detect_simple_single_word_command():
    """Single-word command names (no hyphens) are valid."""
    result = parse_slash_command("/deploy")
    assert result.is_command
    assert result.parsed.name == "deploy"


def test_command_with_leading_whitespace():
    """Leading whitespace before the slash command is stripped."""
    result = parse_slash_command("  /triage-ticket PROJ-9999  ")
    assert result.is_command
    assert result.parsed.name == "triage-ticket"
    assert result.parsed.positional_args == ["PROJ-9999"]


# ---------------------------------------------------------------------------
# parse_slash_command — plain messages (no command)
# ---------------------------------------------------------------------------


def test_no_command_passthrough():
    """A plain message with no slash is not detected as a command."""
    result = parse_slash_command("Hello, how are you?")
    assert not result.is_command
    assert result.parsed is None


def test_empty_string_not_a_command():
    """An empty string is not a command."""
    result = parse_slash_command("")
    assert not result.is_command


def test_slash_only_not_a_command():
    """A bare slash (or slash followed by non-letter) is not a valid command."""
    result = parse_slash_command("/")
    assert not result.is_command


def test_slash_starting_with_digit_not_a_command():
    """Command names must start with a letter."""
    result = parse_slash_command("/123test")
    assert not result.is_command


def test_message_with_slash_in_middle_not_a_command():
    """A slash that is not at the start of the message is not a command."""
    result = parse_slash_command("Please run /deploy for me")
    assert not result.is_command


# ---------------------------------------------------------------------------
# parse_slash_command — meta-commands
# ---------------------------------------------------------------------------


def test_use_skill_meta_command():
    """The /use-skill meta-command is detected and its value extracted."""
    result = parse_slash_command("/use-skill code-review")
    assert result.is_command
    assert result.is_meta_command
    assert result.meta_action == "use-skill"
    assert result.meta_value == "code-review"


def test_use_skill_with_hyphenated_name():
    """Hyphenated skill names (e.g., incident-response) are extracted correctly."""
    result = parse_slash_command("/use-skill incident-response")
    assert result.is_command
    assert result.is_meta_command
    assert result.meta_value == "incident-response"


def test_use_skill_requires_skill_name():
    """/use-skill without a name falls back to a regular command parse."""
    # Without a skill name, USE_SKILL_PATTERN won't match; COMMAND_PATTERN will
    # match "use-skill" as the command name with no args.
    result = parse_slash_command("/use-skill")
    # It will be treated as a regular command named "use-skill" with no args.
    assert result.is_command
    assert not result.is_meta_command
    assert result.parsed.name == "use-skill"
    assert result.parsed.positional_args == []


# ---------------------------------------------------------------------------
# parse_slash_command — quoted arguments
# ---------------------------------------------------------------------------


def test_quoted_argument():
    """A quoted argument containing a URL is kept as a single token."""
    result = parse_slash_command('/summarize-thread "https://slack.com/archives/test"')
    assert result.is_command
    assert result.parsed.positional_args == ["https://slack.com/archives/test"]


def test_quoted_argument_with_spaces():
    """A quoted argument containing spaces is kept as a single token."""
    result = parse_slash_command('/my-command "hello world foo"')
    assert result.is_command
    assert result.parsed.positional_args == ["hello world foo"]


def test_mixed_quoted_and_unquoted_args():
    """Mix of quoted and unquoted args is split correctly."""
    result = parse_slash_command('/cmd PROJ-1234 "a message with spaces"')
    assert result.parsed.positional_args == ["PROJ-1234", "a message with spaces"]


def test_unclosed_quote_falls_back_to_split():
    """An unclosed quote causes shlex to fail; we fall back to whitespace split."""
    result = parse_slash_command('/cmd "unclosed')
    assert result.is_command
    # shlex fails → whitespace split → ["\"unclosed"]
    assert result.parsed.positional_args == ['"unclosed']


# ---------------------------------------------------------------------------
# map_positional_to_variables
# ---------------------------------------------------------------------------


def test_map_positional_to_variables_single():
    """Single positional arg mapped to the first required variable."""
    variables = [{"name": "ticket_number", "required": True}]
    result = map_positional_to_variables(["PROJ-1234"], variables)
    assert result == {"ticket_number": "PROJ-1234"}


def test_map_positional_to_variables_multiple():
    """Multiple positional args mapped in declaration order."""
    variables = [
        {"name": "ticket_number", "required": True},
        {"name": "priority", "required": True},
    ]
    result = map_positional_to_variables(["PROJ-1234", "High"], variables)
    assert result == {"ticket_number": "PROJ-1234", "priority": "High"}


def test_map_positional_skips_optional_variables():
    """Optional variables are excluded from positional mapping."""
    variables = [
        {"name": "ticket_number", "required": True},
        {"name": "comment", "required": False},  # optional — not mapped positionally
    ]
    result = map_positional_to_variables(["PROJ-1234"], variables)
    assert result == {"ticket_number": "PROJ-1234"}
    assert "comment" not in result


def test_map_positional_fewer_args_than_variables():
    """Fewer positional args than required variables — only provided args are mapped."""
    variables = [
        {"name": "ticket_number", "required": True},
        {"name": "assignee", "required": True},
    ]
    result = map_positional_to_variables(["PROJ-1234"], variables)
    assert result == {"ticket_number": "PROJ-1234"}
    assert "assignee" not in result


def test_map_positional_no_args():
    """No positional args → empty result dict."""
    variables = [{"name": "ticket_number", "required": True}]
    result = map_positional_to_variables([], variables)
    assert result == {}


def test_map_positional_no_variables():
    """No variables defined → empty result dict regardless of args."""
    result = map_positional_to_variables(["PROJ-1234"], [])
    assert result == {}


def test_map_positional_more_args_than_variables():
    """Extra positional args beyond declared variables are silently ignored."""
    variables = [{"name": "ticket_number", "required": True}]
    result = map_positional_to_variables(["PROJ-1234", "extra", "args"], variables)
    assert result == {"ticket_number": "PROJ-1234"}


def test_map_positional_required_defaults_to_true():
    """Variables without an explicit 'required' key are treated as required."""
    variables = [{"name": "ticket_number"}]  # no 'required' key
    result = map_positional_to_variables(["PROJ-5678"], variables)
    assert result == {"ticket_number": "PROJ-5678"}
