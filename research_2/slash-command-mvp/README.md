# Slash Command MVP

MVP reference implementation of a slash command and Agent Skills system for a CopilotKit + Pydantic AI + MCP stack. Demonstrates Pattern 2: Middleware Microservice with Prompt Template Registry.

## Architecture

```
                        ┌─────────────────────────────────────────────────────┐
                        │                  Docker Network                      │
                        │                                                      │
┌──────────┐  AG-UI     │  ┌──────────────────┐   HTTP    ┌─────────────────┐ │
│          │  SSE/HTTP  │  │                  │──────────▶│  Prompt         │ │
│ Frontend │───────────▶│  │ Agent Middleware  │           │  Registry       │ │
│ :3000    │            │  │ :8000            │◀──────────│  :8001          │ │
│          │            │  │                  │           │                 │ │
└──────────┘            │  │  ┌────────────┐  │           │  SQLite + SKILL  │ │
                        │  │  │ Pydantic   │  │           │  .md files      │ │
                        │  │  │ AI Agent   │  │           └─────────────────┘ │
                        │  │  └─────┬──────┘  │                               │
                        │  │        │          │                               │
                        │  │  ┌─────▼──────┐  │                               │
                        │  │  │ Mock MCP   │  │                               │
                        │  │  │ Tools      │  │                               │
                        │  │  │ (Jira/Git) │  │                               │
                        │  │  └────────────┘  │                               │
                        │  └──────────────────┘                               │
                        └─────────────────────────────────────────────────────┘
```

**Request flow for a slash command:**

1. User types `/triage-ticket PROJ-1234` in the chat UI
2. Frontend intercepts the `/` prefix and shows the command palette
3. On submit, frontend POSTs to `agent-middleware /copilotkit`
4. Middleware intercepts the message, detects the slash command
5. Middleware fetches the resolved prompt from the prompt registry (variables substituted)
6. Resolved prompt replaces the raw user message before reaching the Pydantic AI agent
7. Agent calls mock MCP tools (Jira, Git) and streams the response back via AG-UI SSE

## Quick Start

```bash
# 1. Clone and enter the project
git clone <repo>
cd slash-command-mvp

# 2. Set your Anthropic API key
cp .env.example .env
# Edit .env and set LLM_API_KEY=sk-ant-...

# 3. Start all services
docker-compose up --build

# 4. Open the chat UI
open http://localhost:3000
```

All three services will start in dependency order: prompt-registry first, then agent-middleware (waits for registry health check), then frontend (waits for middleware health check).

## Demo Walkthrough

Once all services are running at `http://localhost:3000`:

1. **Command palette** — Type `/` in the chat input to see the command palette appear above the input with all available commands.

2. **Ticket triage** — Type `/triage-ticket PROJ-1234` to analyze and triage a mock Jira ticket. The agent will fetch ticket details via mock MCP tools and produce a structured triage report.

3. **List tickets** — Type `/list-my-tickets` to see your open tickets returned from the mock Jira tool.

4. **Generate a PR description** — Type `/create-pr PROJ-1234` to auto-generate a pull request description based on a mock ticket and diff.

5. **Summarize a thread** — Type `/summarize-thread https://example.com/thread` to summarize a discussion thread (mock data returned for any URL).

6. **Activate a skill** — Click "Activate Skill" on `code-review` or `incident-response` in the sidebar. The skill's instructions are prepended to the agent's system prompt for the remainder of the session.

7. **Normal chat** — Type any message without a `/` prefix to talk to the agent directly without triggering a command.

## Services

| Service | Port | Purpose |
|---------|------|---------|
| **Frontend** | 3000 | React + CopilotKit chat UI with slash command palette and skills sidebar |
| **Agent Middleware** | 8000 | Intercepts AG-UI requests, resolves slash commands, runs Pydantic AI agent |
| **Prompt Registry** | 8001 | CRUD API for command definitions and Agent Skills, backed by SQLite |

## Available Commands

| Command | Parameters | Description |
|---------|-----------|-------------|
| `/triage-ticket` | `<ticket_number>` | Analyze and triage a Jira ticket |
| `/list-my-tickets` | _(none)_ | List your open tickets |
| `/create-pr` | `<ticket_number>` | Generate a PR description |
| `/summarize-thread` | `<thread_url>` | Summarize a discussion thread |
| `/use-skill` | `<skill_name>` | Activate an Agent Skill by name |

Commands are defined in the prompt registry and can be added, updated, or deleted via the registry API at `http://localhost:8001/docs`.

## Available Skills

### `code-review`
Activates a code review assistant persona. When active, the agent applies structured code review practices: checking for correctness, test coverage, security issues, and adherence to conventions. Useful when pasting code snippets or asking for feedback on a diff.

**Tags:** `code`, `review`, `quality`

### `incident-response`
Activates an incident response coordinator persona. When active, the agent follows structured incident management: identifying severity, suggesting immediate mitigations, drafting status updates, and tracking action items. Useful during on-call situations.

**Tags:** `ops`, `incident`, `reliability`

Skills are stored as `SKILL.md` files in `prompt-registry/src/skills/` and loaded into the database at startup. See `docs/AGENT_SKILLS_SPEC.md` for the full format specification.

## Development

### Running tests

```bash
# Run prompt-registry tests
cd prompt-registry && pip install -e ".[dev]" && pytest

# Run agent-middleware tests
cd agent-middleware && pip install -e ".[dev]" && pytest

# Run frontend tests
cd frontend && npm install && npm test
```

### Running services individually

```bash
# Run prompt registry (port 8001)
cd prompt-registry && uvicorn src.main:app --reload --port 8001

# Run agent middleware (port 8000)
cd agent-middleware && uvicorn src.main:app --reload --port 8000

# Run frontend dev server (port 3000)
cd frontend && npm run dev
```

When running services individually, ensure the prompt registry is running before starting the agent middleware (the middleware fetches command definitions from the registry on each request).

### Environment variables

| Variable | Service | Default | Description |
|----------|---------|---------|-------------|
| `LLM_API_KEY` | agent-middleware | _(required)_ | Anthropic API key |
| `LLM_MODEL` | agent-middleware | `claude-sonnet-4-5-20250929` | Model ID |
| `REGISTRY_URL` | agent-middleware | `http://localhost:8001` | Prompt registry base URL |
| `DATABASE_URL` | prompt-registry | `sqlite+aiosqlite:///./data/commands.db` | Database connection string |
| `SKILLS_DIR` | prompt-registry | `./src/skills` | Path to SKILL.md files |
| `LOG_LEVEL` | both backends | `INFO` | Logging verbosity |

## API Reference

Both backend services expose interactive Swagger UIs:

- **Prompt Registry** — `http://localhost:8001/docs`
  - `GET /api/v1/commands` — list all commands
  - `POST /api/v1/commands` — create a command
  - `GET /api/v1/commands/{name}/resolve` — resolve a command with variable substitution
  - `GET /api/v1/skills` — list all skills
  - `GET /api/v1/health` — health check

- **Agent Middleware** — `http://localhost:8000/docs`
  - `POST /copilotkit` — main AG-UI endpoint (used by frontend)
  - `GET /api/v1/health` — health check

## Code Tour

Start here to understand the system:

1. **`prompt-registry/src/models.py`** — Data models for `SlashCommand` and `AgentSkill`. Defines the shape of everything stored in SQLite.

2. **`prompt-registry/src/services/command_resolver.py`** — The `{{variable}}` template substitution engine. Simple string replacement with validation.

3. **`prompt-registry/src/services/skill_loader.py`** — Parses `SKILL.md` files using PyYAML for YAML frontmatter extraction, loads skills into the database at startup.

4. **`agent-middleware/src/interceptor.py`** — Slash command detection logic. Parses the raw user message, identifies `/command args` patterns, and triggers registry lookup.

5. **`agent-middleware/src/main.py`** — The central request handler. The `copilotkit_endpoint` function shows how a slash command message is intercepted, resolved, and replaced before reaching the Pydantic AI agent.

6. **`agent-middleware/src/skills_context.py`** — Injects active skill instructions into the agent's system prompt.

7. **`agent-middleware/src/mcp_tools/`** — Mock MCP tool implementations (`mock_jira.py`, `mock_git.py`). In production these would be replaced with real MCP server connections.

8. **`frontend/src/hooks/useSlashCommands.ts`** — Custom React hook that detects `/` input, fetches command definitions from the registry, and manages palette state.

9. **`frontend/src/components/CommandPalette.tsx`** — The command palette UI component rendered above the chat input.
