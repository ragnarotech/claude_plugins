# Agent Skills Standard — Local Reference

Source: agentskills.io (adopted by Anthropic, OpenAI, Cursor, GitHub Copilot, VS Code, Amp)

## Overview

Agent Skills is an open standard for packaging AI agent capabilities as distributable, interoperable skill packages. A skill is a self-contained bundle of instructions, tool requirements, and metadata that can be activated in any compatible AI agent runtime.

The standard was developed to solve the fragmentation problem: every AI tool has its own format for "custom instructions", "agents", "personas", or "modes". A skill written for Claude Code could not be directly imported into Cursor or used from GitHub Copilot. Agent Skills provides a common format so that capabilities can be authored once and run anywhere.

## Skill Package Structure

```
skill-name/
  SKILL.md           # Required: YAML frontmatter + Markdown instructions
  templates/         # Optional: supporting prompt templates
  scripts/           # Optional: supporting scripts
  resources/         # Optional: supporting files (schemas, examples)
```

The only required file is `SKILL.md`. The optional directories allow richer skills that include example inputs, reference schemas, or executable helper scripts (where the runtime supports them).

## SKILL.md Format

```markdown
---
name: skill-name                    # Required: unique identifier
description: What this skill does   # Required: human-readable description
tools:                              # Optional: MCP tool names needed
  - tool_name_1
  - tool_name_2
tags:                               # Optional: categorization
  - category1
  - category2
model: claude-sonnet-4-5            # Optional: preferred model override
---

# Skill Title

[Markdown instructions for the agent. This is the core of the skill —
free-form instructions that guide the agent's behavior when this skill is active.]
```

### Frontmatter fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `name` | Yes | string | Unique identifier, kebab-case, no spaces |
| `description` | Yes | string | One-sentence human-readable summary |
| `tools` | No | list of strings | MCP tool names the skill depends on |
| `tags` | No | list of strings | Categorization tags for search and discovery |
| `model` | No | string | Preferred model ID to override the runtime default |
| `version` | No | string (semver) | Skill version for compatibility tracking |
| `author` | No | string | Author name or organization |

### Instruction body

The Markdown body (after the closing `---`) contains the agent instructions. These are prepended to the agent's system prompt when the skill is activated. There are no structural requirements for the body — it can be free-form prose, a bulleted checklist, a structured protocol, or a combination. The quality of the instructions directly determines the quality of the agent's behavior.

Best practices for instruction bodies:

- **Be explicit about persona:** State what the agent should act as and what perspective it should adopt.
- **Define the output format:** Specify headers, sections, or structured output the agent should produce.
- **List what to check for:** Enumerated checklists work better than vague directives like "be thorough".
- **Include anti-patterns:** Tell the agent what NOT to do. This is often more effective than positive instructions alone.
- **Keep it scannable:** The agent reads the instructions at invocation time; dense paragraphs are harder to follow than structured Markdown.

## How This MVP Uses Agent Skills

### Storage

Skills are stored as `SKILL.md` files in the `prompt-registry/src/skills/` directory, organized into one subdirectory per skill:

```
prompt-registry/src/skills/
  code-review/
    SKILL.md
  incident-response/
    SKILL.md
```

At service startup, the skill loader scans the `SKILLS_DIR` directory, parses each `SKILL.md` file, and upserts the parsed data into the SQLite `agent_skills` table. The raw `SKILL.md` text is preserved in the `raw_content` column for re-export.

### Loading

`skill_loader.py` parses `SKILL.md` files in two passes:

1. **Frontmatter extraction:** The file is split on the `---` delimiter. The content between the first and second `---` delimiters is parsed as YAML using `PyYAML`. Required fields (`name`, `description`) are validated.
2. **Body extraction:** The content after the second `---` delimiter is stored as the skill's instruction body (raw Markdown).

Parsing errors (malformed YAML, missing required fields) are logged as warnings and the skill is skipped — a bad skill file does not prevent the service from starting.

### Injection

When a request arrives at the agent middleware, `skills_context.py` determines which skills should be active for this request. Active skills are fetched from the prompt registry by name. Their instruction bodies are concatenated and prepended to the Pydantic AI agent's system prompt in the following format:

```
## Active Skills

### {skill.name}
{skill.instructions}

---

### {skill2.name}
{skill2.instructions}

---

[rest of system prompt]
```

The `## Active Skills` section is always at the top of the system prompt so it takes precedence over the base system prompt instructions.

### Invocation

Skills can be activated in two ways:

**Explicit invocation** via the `/use-skill <name>` meta-command. The user types `/use-skill code-review` in the chat, the interceptor detects the command, looks up the skill by name in the registry, and stores the skill name in the session state. All subsequent requests in the session include the skill's instructions.

**Implicit invocation** via keyword-based auto-discovery (MVP heuristic). The interceptor checks whether the user's message contains terms that match a skill's `name` or `tags`. For example, a message containing "review this code" matches the `code-review` skill's tags. The match triggers automatic skill injection for that single request (not persisted to session state).

## Differences from Full Standard

The MVP implements a subset of the Agent Skills standard:

| Feature | MVP | Status |
|---------|-----|--------|
| `SKILL.md` format with YAML frontmatter | Implemented | Done |
| Markdown instruction body | Implemented | Done |
| `tools` frontmatter field (stored) | Implemented | Done |
| `tags` frontmatter field (stored, used for matching) | Implemented | Done |
| `model` frontmatter field (stored) | Stored, not enforced | Partial |
| `scripts/` execution | Not implemented | Future |
| `templates/` directory | Not implemented | Future |
| Progressive disclosure (summarized vs. full) | Full content always loaded | Future |
| OCI packaging for distribution | Not implemented | Future |
| Version field and compatibility checking | Not implemented | Future |

Note on `tools` field: the MVP stores the `tools` list in the database but does not use it to conditionally enable or disable MCP tools. In a production implementation, the agent middleware would verify that all tools listed in `tools` are available in the current MCP tool registry before activating the skill, and would surface a warning to the user if a required tool is unavailable.

## Interoperability

Because skills are stored in the standard `SKILL.md` format and the raw content is preserved, skills in this MVP can be exchanged with other tools:

**From Claude Code:** Copy a skill directory from `.claude/commands/` into `prompt-registry/src/skills/`. Restart the prompt registry service (or wait for the inotify hot-reload in production). The skill is immediately available.

**To OpenAI Codex:** Export a skill by calling `GET /api/v1/skills/{name}/export` on the registry (returns the raw `SKILL.md` content). Save it to the appropriate directory for Codex's agents folder.

**Between teams:** Zip the skill directory and share it. The recipient drops it into their `skills/` directory. No conversion, no reformatting.

**OCI distribution (future):** Package the skill directory as an OCI artifact and push it to a container registry:

```bash
oras push ghcr.io/myorg/skills/code-review:1.0.0 \
  --artifact-type application/vnd.agentskills.skill.v1 \
  code-review/SKILL.md:application/vnd.agentskills.skill-manifest.v1
```

Pull on the receiving side:

```bash
oras pull ghcr.io/myorg/skills/code-review:1.0.0 -o ./skills/
```

The OCI packaging approach enables versioned, signed skill artifacts with the same tooling used for container images — including mirroring, air-gapped distribution, and supply chain attestation.
