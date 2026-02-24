# MVP Software Plan: Slash Command System with Prompt Template Registry

## 1. Executive Summary

This plan describes an MVP implementation of **Pattern 2: Middleware Microservice with Prompt Template Registry** for a slash command / skills system integrated with an AG-UI CopilotKit frontend, Pydantic AI agent backend, and MCP tool ecosystem. The MVP produces a **fully working reference implementation** with inline code comments explaining every architectural decision, so it can serve as a blueprint for integration into the production company stack.

The MVP proves out three things: (1) slash command interception and resolution at the middleware layer, (2) a CRUD-capable prompt registry service, and (3) Agent Skills packaging as a first-class concept alongside explicit slash commands.

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        User's Browser                                │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │              React + CopilotKit Frontend                       │  │
│  │  ┌──────────────┐  ┌──────────────────┐  ┌────────────────┐   │  │
│  │  │ Chat Panel   │  │ Slash Command    │  │ Param Form     │   │  │
│  │  │ (CopilotChat)│  │ Autocomplete     │  │ Modal          │   │  │
│  │  └──────┬───────┘  └────────┬─────────┘  └───────┬────────┘   │  │
│  │         │                   │                     │            │  │
│  │         └───────────────────┼─────────────────────┘            │  │
│  │                             │                                  │  │
│  │                    useCopilotChat +                            │  │
│  │                    custom /command hook                        │  │
│  └─────────────────────────────┼──────────────────────────────────┘  │
└────────────────────────────────┼─────────────────────────────────────┘
                                 │ AG-UI SSE stream
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    CopilotKit Runtime Middleware                      │
│                    (Node.js or Python FastAPI)                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                  Command Interceptor Layer                       │ │
│  │                                                                  │ │
│  │  1. Detect "/command" prefix in user message                     │ │
│  │  2. Parse command name + arguments                               │ │
│  │  3. Call Prompt Registry Service to resolve                      │ │
│  │  4. Substitute variables, inject context                         │ │
│  │  5. Forward resolved prompt to agent                             │ │
│  └──────────┬──────────────────────────────┬────────────────────────┘ │
│             │                              │                          │
│             ▼                              ▼                          │
│  ┌──────────────────┐          ┌──────────────────────┐              │
│  │ Prompt Registry   │          │ Pydantic AI Agent     │              │
│  │ Service (HTTP)    │          │ (AG-UI compatible)    │              │
│  │                   │          │                       │              │
│  │ GET /commands     │          │ Receives resolved     │              │
│  │ GET /commands/:id │          │ prompt as normal      │              │
│  │ POST /commands    │          │ user message          │              │
│  │ PUT /commands/:id │          │                       │              │
│  │ DELETE /commands  │          │ Has MCP tools         │              │
│  │                   │          │ available for         │              │
│  │ GET /skills       │          │ tool calls            │              │
│  │ GET /skills/:id   │          │                       │              │
│  └──────────────────┘          └───────────┬───────────┘              │
│                                            │                          │
└────────────────────────────────────────────┼──────────────────────────┘
                                             │ MCP protocol
                                             ▼
                                  ┌──────────────────────┐
                                  │   MCP Tool Servers    │
                                  │                       │
                                  │  - mock-jira-server   │
                                  │  - mock-git-server    │
                                  │  - mock-ticket-server │
                                  └──────────────────────┘
```

### Key Architectural Decisions (documented in code)

Every component in the MVP will contain `# DECISION:` comments explaining:
- Why this layer handles this responsibility (and not another)
- What changes for production (mTLS, real DB, K8s deployment)
- Where the Agent Skills standard applies
- How MCP prompts protocol maps to this design
- What CopilotKit hooks/patterns are used and their limitations

---

## 3. Component Breakdown

### 3.1 Prompt Registry Service

**Purpose:** Single source of truth for all slash command definitions and skill metadata. Initially serves hardcoded commands; designed to evolve into a full CRUD store with user-custom commands and marketplace.

**Technology:** Python FastAPI + SQLite (MVP) → PostgreSQL (production)

**Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/commands` | List all commands (with optional `?search=` and `?tag=` filters) |
| `GET` | `/api/v1/commands/{name}` | Get single command definition |
| `GET` | `/api/v1/commands/{name}/resolve` | Resolve a command with provided arguments, returns expanded prompt |
| `POST` | `/api/v1/commands` | Create a new command (future: user-custom) |
| `PUT` | `/api/v1/commands/{name}` | Update a command |
| `DELETE` | `/api/v1/commands/{name}` | Soft-delete a command |
| `GET` | `/api/v1/skills` | List all registered skills |
| `GET` | `/api/v1/skills/{name}` | Get skill definition (returns SKILL.md content + metadata) |
| `GET` | `/api/v1/health` | Health check |

**Data Model (SQLite for MVP):**

```
Table: commands
  - id: TEXT (UUID, primary key)
  - name: TEXT (unique, e.g., "triage-ticket")
  - display_name: TEXT (e.g., "Triage Ticket")
  - description: TEXT
  - template: TEXT (the prompt template with {{variable}} placeholders)
  - variables: JSON (array of {name, type, required, description, default, enum})
  - tools: JSON (array of MCP tool names this command expects)
  - tags: JSON (array of strings)
  - source: TEXT ("builtin" | "user" | "marketplace")
  - version: INTEGER (auto-incremented on update)
  - is_active: BOOLEAN
  - created_at: DATETIME
  - updated_at: DATETIME

Table: skills
  - id: TEXT (UUID, primary key)
  - name: TEXT (unique, e.g., "code-review")
  - description: TEXT
  - skill_md: TEXT (full SKILL.md content)
  - frontmatter: JSON (parsed YAML frontmatter)
  - tools: JSON (array of MCP tool names)
  - tags: JSON (array of strings)
  - source: TEXT ("builtin" | "user" | "marketplace")
  - is_active: BOOLEAN
  - created_at: DATETIME
  - updated_at: DATETIME
```

**Seed Data (hardcoded commands for MVP):**

1. `/triage-ticket <ticket_number>` — Fetches ticket details via mock Jira MCP tool, analyzes priority, suggests assignee
2. `/list-my-tickets` — Lists open tickets assigned to the current user
3. `/create-pr <ticket_number>` — Generates a PR description from ticket details and recent commits
4. `/summarize-thread <thread_url>` — Summarizes a discussion thread

**Seed Skills:**

1. `code-review` — Agent Skill for reviewing code changes (SKILL.md format)
2. `incident-response` — Agent Skill for triaging production incidents

**Resolution Logic:**
The `/resolve` endpoint performs:
1. Look up command by name
2. Validate all required arguments are provided
3. Substitute `{{variable}}` placeholders with argument values
4. Inject system context (user identity placeholder, timestamp, environment)
5. Return a structured response with the expanded prompt and metadata

```json
// Example: GET /api/v1/commands/triage-ticket/resolve?ticket_number=PROJ-1234
{
  "command_name": "triage-ticket",
  "resolved_prompt": "You are triaging ticket PROJ-1234. Use the jira_get_ticket tool to fetch the ticket details...",
  "system_context": "User: andrew@company.com | Environment: dev | Time: 2026-02-23T10:00:00Z",
  "required_tools": ["jira_get_ticket", "jira_update_ticket"],
  "metadata": {
    "version": 1,
    "source": "builtin",
    "resolved_at": "2026-02-23T10:00:00Z"
  }
}
```

### 3.2 CopilotKit Middleware with Command Interceptor

**Purpose:** Sits between the CopilotKit frontend and the Pydantic AI agent. Intercepts messages beginning with `/`, resolves them via the Prompt Registry, and forwards the expanded prompt to the agent as if the user had typed it directly.

**Technology:** Python FastAPI (CopilotKit Python SDK remote endpoint)

**Why middleware, not frontend?**
- Frontend slash command detection is for **autocomplete UX only** (showing the dropdown, collecting parameters)
- The actual resolution happens server-side so that: templates can contain secrets/context the frontend shouldn't see, tool availability can be verified, auth context can be injected, and the agent receives a clean prompt without knowing about the command system

**Interceptor Logic (pseudocode):**

```python
async def handle_message(request: CopilotKitRequest):
    user_message = request.messages[-1].content

    # DECISION: Detect slash commands by "/" prefix
    # This is intentionally simple for MVP. Production should use
    # a more robust parser that handles edge cases like "/" in URLs.
    if user_message.strip().startswith("/"):
        command_name, args = parse_slash_command(user_message)

        # DECISION: Resolve via HTTP call to Prompt Registry Service
        # In production, this could use gRPC or even in-process resolution
        # if co-located. HTTP chosen for MVP simplicity and service independence.
        resolved = await registry_client.resolve_command(
            name=command_name,
            arguments=args,
            user_context=extract_user_context(request)
        )

        if resolved.error:
            # Return error to user via AG-UI text event
            return error_response(resolved.error)

        # DECISION: Replace the user message with the resolved prompt
        # The agent never sees the raw "/command" — it receives a fully
        # expanded prompt. This keeps the agent implementation clean and
        # means any agent can work with this system.
        request.messages[-1].content = resolved.resolved_prompt

        # DECISION: Add system message with tool hints
        # This nudges the agent to use the right MCP tools without
        # hardcoding tool knowledge into the agent itself.
        if resolved.required_tools:
            request.messages.insert(-1, SystemMessage(
                content=f"The following tools are relevant: {resolved.required_tools}"
            ))

    # Forward to Pydantic AI agent as normal
    return await agent.handle(request)
```

### 3.3 Pydantic AI Agent (AG-UI Compatible)

**Purpose:** The LLM-powered agent that receives resolved prompts and executes them using MCP tools. Intentionally knows nothing about the slash command system — it just processes well-formed prompts.

**Technology:** Pydantic AI with AG-UI adapter

**Agent Design:**
- System prompt establishes the agent as a helpful development assistant
- MCP tools are registered at startup (mock tools for MVP)
- Agent uses structured output for certain command patterns (e.g., ticket triage returns a structured assessment)
- Skills are loaded as additional system context when the agent detects a skill-relevant task

**MCP Tools (mock implementations for MVP):**

| Tool Name | Purpose | Mock Behavior |
|-----------|---------|---------------|
| `jira_get_ticket` | Fetch ticket details | Returns hardcoded ticket JSON |
| `jira_update_ticket` | Update ticket fields | Logs update, returns success |
| `jira_list_tickets` | List tickets for a user | Returns hardcoded list |
| `git_list_commits` | List recent commits | Returns hardcoded commit list |
| `git_create_pr` | Create a pull request | Logs PR details, returns mock PR URL |

### 3.4 React Frontend with CopilotKit

**Purpose:** Chat interface with slash command autocomplete, parameter collection forms, and standard CopilotKit chat functionality.

**Technology:** React + TypeScript + CopilotKit + Tailwind CSS

**Slash Command UX Flow:**

1. User types `/` in the chat input
2. Frontend queries Prompt Registry `GET /api/v1/commands?search=<partial>` for autocomplete
3. Dropdown shows matching commands with descriptions
4. User selects a command
5. If command has required variables → show parameter form modal
6. User fills parameters → form submits
7. Frontend sends `/<command_name> <serialized_args>` as a chat message
8. Middleware intercepts, resolves, agent processes, response streams back

**Key CopilotKit Integration Points:**

- `useCopilotChat` — main chat hook; we wrap the `append` function to detect and handle `/` commands before sending
- `CopilotKit` provider — configured to point at our custom middleware endpoint
- Custom `useSlashCommands` hook — manages autocomplete state, parameter forms, and command submission
- Custom `CommandPalette` component — the autocomplete dropdown rendered above the chat input

### 3.5 Skills Integration

**Purpose:** Support Agent Skills (SKILL.md format) as a companion to explicit slash commands. Skills are agent-discoverable capabilities that can be invoked implicitly or explicitly.

**How skills differ from slash commands in the MVP:**

| Aspect | Slash Commands | Skills |
|--------|---------------|--------|
| Invocation | Explicit: user types `/command` | Implicit: agent discovers, or user browses skill catalog |
| Resolution | Middleware intercepts and resolves before agent | Agent receives skill context in system prompt |
| Parameters | User provides via form | Agent extracts from conversation context |
| Template | Rigid `{{variable}}` substitution | Free-form SKILL.md instructions |
| MCP tools | Declared, verified at resolve time | Declared, loaded at agent startup |

**Skills in the MVP are stored in the Prompt Registry** alongside commands, with a separate `/skills` endpoint. The middleware loads relevant skills into the agent's system prompt based on the user's current context or explicit skill selection.

**Agent Skills packaging format (following the open standard):**

```
skills/
  code-review/
    SKILL.md          # YAML frontmatter + Markdown instructions
    templates/
      pr-template.md  # Supporting templates
    scripts/
      lint-check.sh   # Supporting scripts (not executed in MVP)
```

**SKILL.md example:**

```markdown
---
name: code-review
description: Review code changes for quality, security, and best practices
tools:
  - git_list_commits
  - jira_get_ticket
tags:
  - development
  - quality
---

# Code Review Skill

When asked to review code, follow these steps:

1. Use the `git_list_commits` tool to fetch recent changes
2. Analyze the diff for:
   - Security vulnerabilities
   - Performance issues
   - Code style violations
   - Missing tests
3. If a ticket number is mentioned, use `jira_get_ticket` to understand requirements
4. Provide a structured review with severity ratings
```

---

## 4. Project Structure

```
slash-command-mvp/
├── README.md                          # Setup and run instructions
├── docker-compose.yml                 # Local dev environment
│
├── prompt-registry/                   # Prompt Registry Service
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── src/
│   │   ├── main.py                    # FastAPI app entry point
│   │   ├── config.py                  # Settings and environment config
│   │   ├── database.py                # SQLite setup, migrations
│   │   ├── models.py                  # Pydantic models for commands & skills
│   │   ├── seed.py                    # Hardcoded command/skill definitions
│   │   ├── routers/
│   │   │   ├── commands.py            # /api/v1/commands endpoints
│   │   │   └── skills.py             # /api/v1/skills endpoints
│   │   ├── services/
│   │   │   ├── command_resolver.py    # Template resolution logic
│   │   │   └── skill_loader.py        # SKILL.md parsing logic
│   │   └── skills/                    # Built-in SKILL.md files
│   │       ├── code-review/
│   │       │   └── SKILL.md
│   │       └── incident-response/
│   │           └── SKILL.md
│   └── tests/
│       ├── test_commands.py
│       ├── test_resolution.py
│       └── test_skills.py
│
├── agent-middleware/                   # CopilotKit Middleware + Agent
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── src/
│   │   ├── main.py                    # FastAPI app with CopilotKit endpoint
│   │   ├── config.py                  # Settings
│   │   ├── interceptor.py             # Slash command interceptor logic
│   │   ├── registry_client.py         # HTTP client for Prompt Registry
│   │   ├── agent.py                   # Pydantic AI agent definition
│   │   ├── skills_context.py          # Skills injection into agent context
│   │   └── mcp_tools/
│   │       ├── mock_jira.py           # Mock Jira MCP tool server
│   │       ├── mock_git.py            # Mock Git MCP tool server
│   │       └── tool_registry.py       # MCP tool registration
│   └── tests/
│       ├── test_interceptor.py
│       ├── test_agent.py
│       └── test_registry_client.py
│
├── frontend/                          # React CopilotKit Frontend
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── App.tsx                    # Main app with CopilotKit provider
│   │   ├── main.tsx                   # Entry point
│   │   ├── components/
│   │   │   ├── ChatPanel.tsx          # CopilotChat wrapper
│   │   │   ├── CommandPalette.tsx     # Slash command autocomplete dropdown
│   │   │   ├── ParamFormModal.tsx     # Parameter collection form
│   │   │   ├── SkillCatalog.tsx       # Browsable skill list (sidebar)
│   │   │   └── CommandInput.tsx       # Enhanced chat input with "/" detection
│   │   ├── hooks/
│   │   │   ├── useSlashCommands.ts    # Command autocomplete + submission
│   │   │   └── useSkills.ts           # Skill catalog fetching
│   │   ├── services/
│   │   │   └── registryApi.ts         # HTTP client for Prompt Registry
│   │   └── types/
│   │       └── commands.ts            # TypeScript types for commands/skills
│   └── tests/
│       ├── CommandPalette.test.tsx
│       └── useSlashCommands.test.ts
│
└── docs/
    ├── ARCHITECTURE.md                # Detailed architecture decisions
    ├── PRODUCTION_NOTES.md            # What changes for production deployment
    └── AGENT_SKILLS_SPEC.md           # Local copy of Agent Skills format spec
```

---

## 5. Implementation Phases

### Phase 1: Prompt Registry Service (Days 1-3)

**Goal:** Fully functional CRUD API with hardcoded seed data, template resolution, and skill serving.

**Tasks:**

1. **Scaffold FastAPI project** with pyproject.toml, Dockerfile, and config
2. **Define Pydantic models** for `Command`, `CommandVariable`, `Skill`, `ResolvedCommand`
3. **Implement SQLite database layer** with aiosqlite
   - Schema creation on startup
   - Seed data insertion (idempotent)
4. **Implement command CRUD endpoints** (`/api/v1/commands`)
   - List with search/tag filtering
   - Get by name
   - Create, update, soft-delete
5. **Implement resolution endpoint** (`/api/v1/commands/{name}/resolve`)
   - Variable substitution with `{{var}}` syntax
   - Required variable validation
   - System context injection stub
   - Tool requirement passthrough
6. **Implement skills endpoints** (`/api/v1/skills`)
   - Load SKILL.md files from disk at startup
   - Parse YAML frontmatter
   - Serve skill metadata and content
7. **Write seed data module** with 4 commands + 2 skills
8. **Write tests** for resolution logic, CRUD operations, edge cases
9. **Add comprehensive `# DECISION:` comments** throughout

**Key comments to include:**
- `# DECISION: SQLite for MVP. Production: PostgreSQL with connection pooling via asyncpg.`
- `# DECISION: {{variable}} syntax chosen for simplicity. Production could support Jinja2 or Handlebars for conditionals/loops.`
- `# DECISION: Skills loaded from filesystem at startup. Production: store in DB with hot-reload via filesystem watcher or webhook.`
- `# DECISION: No auth on MVP endpoints. Production: JWT validation middleware, RBAC per-command.`
- `# DECISION: Soft delete to preserve audit trail. Production: add version history table.`
- `# DECISION: In-memory cache for command lookups. Production: Redis with TTL and cache invalidation on write.`

### Phase 2: Agent Middleware with Command Interceptor (Days 3-5)

**Goal:** CopilotKit-compatible middleware that intercepts slash commands, resolves them via the registry, and forwards expanded prompts to the Pydantic AI agent.

**Tasks:**

1. **Scaffold FastAPI project** with CopilotKit Python SDK
2. **Implement CopilotKit remote endpoint** using the SDK's `CopilotKitRemoteEndpoint`
3. **Build command interceptor** as middleware/pre-processor
   - Slash command detection (regex: `/^\/([a-z\-]+)(\s+.*)?$/`)
   - Argument parsing (positional for MVP, named for future)
   - Registry client HTTP calls
   - Message rewriting before agent invocation
4. **Build Prompt Registry HTTP client** with httpx
   - Async client with connection pooling
   - Retry logic with exponential backoff
   - Timeout handling
5. **Implement Pydantic AI agent**
   - System prompt with role definition
   - MCP tool registration (mock tools)
   - AG-UI event streaming
   - Skills context injection
6. **Implement mock MCP tool servers** (in-process for MVP)
   - `mock_jira.py`: `jira_get_ticket`, `jira_update_ticket`, `jira_list_tickets`
   - `mock_git.py`: `git_list_commits`, `git_create_pr`
7. **Implement skills context injection**
   - Fetch relevant skills from registry on agent startup
   - Inject SKILL.md content as system prompt addendum
   - Support explicit skill activation via `/use-skill <name>` meta-command
8. **Write tests** for interceptor, agent, and integration
9. **Add comprehensive `# DECISION:` comments**

**Key comments to include:**
- `# DECISION: Intercept at middleware, not frontend. Frontend only handles UX (autocomplete). Server handles resolution so templates can contain privileged context.`
- `# DECISION: Replace user message content, don't add new message. Agent should not know about the command abstraction.`
- `# DECISION: Mock MCP tools are in-process for MVP. Production: separate MCP servers with stdio or SSE transport, registered via mcp.json.`
- `# DECISION: Skills injected as system prompt addenda. Production: use dynamic system prompt composition based on conversation context analysis.`
- `# DECISION: httpx async client for registry calls. Production: consider gRPC for lower latency, or in-process resolution if co-deployed.`
- `# DECISION: CopilotKit Python SDK endpoint. This maps to the AG-UI protocol SSE stream. The SDK handles event serialization.`
- `# DECISION: Positional argument parsing for MVP (e.g., /triage-ticket PROJ-1234). Production: support named args (/triage-ticket --number=PROJ-1234) and interactive parameter collection.`

### Phase 3: React Frontend with CopilotKit (Days 5-7)

**Goal:** Chat interface with slash command autocomplete, parameter forms, skill catalog sidebar, and streaming responses.

**Tasks:**

1. **Scaffold React project** with Vite + TypeScript + Tailwind
2. **Install and configure CopilotKit** (`@copilotkit/react-core`, `@copilotkit/react-ui`)
3. **Build `useSlashCommands` hook**
   - Detects `/` in input field
   - Debounced search against registry API
   - Returns matching commands for autocomplete
   - Handles command selection and argument collection
4. **Build `CommandPalette` component**
   - Positioned above chat input (like Discord/Slack command menus)
   - Shows command name, description, required params
   - Keyboard navigable (arrow keys + Enter)
   - Dismissible (Escape, click outside)
5. **Build `ParamFormModal` component**
   - Dynamically generated from command variable definitions
   - Type-aware inputs (text, number, select for enum variables)
   - Validation against required/type constraints
   - Submit constructs the full `/command arg1 arg2` string
6. **Build `CommandInput` component**
   - Wraps CopilotKit's chat input
   - Integrates slash command detection with autocomplete
   - Passes non-command messages through normally
7. **Build `SkillCatalog` component**
   - Sidebar listing available skills
   - Click to activate a skill (sends `/use-skill <name>` to chat)
   - Shows skill description and required tools
8. **Build `ChatPanel` component**
   - Wraps `CopilotChat` with custom message rendering
   - Shows command resolution indicator (e.g., "Resolved /triage-ticket → ...")
   - Streams agent responses
9. **Write tests** for hooks and critical components
10. **Add comprehensive `// DECISION:` comments**

**Key comments to include:**
- `// DECISION: Autocomplete queries the Prompt Registry directly, not the middleware. This is a read-only operation that doesn't need agent involvement.`
- `// DECISION: Parameter form is rendered client-side from variable definitions. Production: support complex form schemas (conditional fields, file uploads).`
- `// DECISION: Command submission sends the raw "/command args" string to the middleware. The middleware, not the frontend, resolves the template. This prevents template leakage to the client.`
- `// DECISION: useCopilotChat is the primary integration point. CopilotKit doesn't have native slash command support, so we intercept at the message submission layer.`
- `// DECISION: Skill catalog is a simple list for MVP. Production: categorized, searchable, with usage analytics.`
- `// DECISION: No CopilotKit useCopilotAction for commands. Actions are model-controlled (LLM decides when to call them). Slash commands are user-controlled (user explicitly invokes). Different interaction paradigm.`

### Phase 4: Integration, Testing, and Documentation (Days 7-9)

**Goal:** End-to-end working system with docker-compose, integration tests, and reference documentation.

**Tasks:**

1. **docker-compose.yml** with all three services + networking
2. **End-to-end integration tests**
   - User types `/triage-ticket PROJ-1234` → sees triage analysis
   - User types `/list-my-tickets` → sees ticket list
   - User types `/create-pr PROJ-1234` → sees PR description
   - User types normal message → agent responds normally (no interception)
   - User browses skill catalog → activates code-review skill → agent uses it
   - Invalid command → user sees helpful error
   - Missing required parameter → user sees parameter form
3. **ARCHITECTURE.md** — detailed decision log referencing code comments
4. **PRODUCTION_NOTES.md** — what changes for K8s, mTLS, real DB, real MCP tools
5. **README.md** — quick start, demo walkthrough, code tour

---

## 6. Detailed Technical Specifications

### 6.1 Prompt Registry API Contracts

**Command Model:**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "triage-ticket",
  "display_name": "Triage Ticket",
  "description": "Analyze and triage a Jira ticket with AI-powered assessment",
  "template": "You are triaging ticket {{ticket_number}}.\n\nFirst, use the `jira_get_ticket` tool to fetch the full ticket details for {{ticket_number}}.\n\nThen analyze the ticket and provide:\n1. **Priority Assessment**: Based on the ticket description, suggest a priority (Critical/High/Medium/Low) with reasoning\n2. **Component Classification**: Which system component(s) does this affect?\n3. **Suggested Assignee**: Based on the component and recent activity, who should own this?\n4. **Estimated Effort**: T-shirt size (XS/S/M/L/XL) with reasoning\n5. **Recommended Next Steps**: 2-3 concrete actions to move this forward\n\nIf the ticket priority or assignee should be updated, use the `jira_update_ticket` tool to make the changes.",
  "variables": [
    {
      "name": "ticket_number",
      "type": "string",
      "required": true,
      "description": "Jira ticket number (e.g., PROJ-1234)",
      "default": null,
      "enum": null
    }
  ],
  "tools": ["jira_get_ticket", "jira_update_ticket"],
  "tags": ["jira", "triage", "project-management"],
  "source": "builtin",
  "version": 1,
  "is_active": true,
  "created_at": "2026-02-23T00:00:00Z",
  "updated_at": "2026-02-23T00:00:00Z"
}
```

**Resolved Command Response:**

```json
{
  "command_name": "triage-ticket",
  "resolved_prompt": "You are triaging ticket PROJ-1234.\n\nFirst, use the `jira_get_ticket` tool...",
  "system_context": "User: andrew@company.com | Env: dev | Time: 2026-02-23T10:30:00Z",
  "required_tools": ["jira_get_ticket", "jira_update_ticket"],
  "original_command": "/triage-ticket PROJ-1234",
  "metadata": {
    "version": 1,
    "source": "builtin",
    "resolved_at": "2026-02-23T10:30:00Z",
    "resolution_time_ms": 12
  }
}
```

**Error Response:**

```json
{
  "error": {
    "code": "MISSING_REQUIRED_VARIABLE",
    "message": "Command 'triage-ticket' requires variable 'ticket_number'",
    "command_name": "triage-ticket",
    "required_variables": [
      {
        "name": "ticket_number",
        "type": "string",
        "description": "Jira ticket number (e.g., PROJ-1234)"
      }
    ]
  }
}
```

### 6.2 Slash Command Parsing Specification

The middleware parses user messages according to these rules:

```
COMMAND_PATTERN = /^\/([a-zA-Z][a-zA-Z0-9\-]*)\s*(.*)$/

Captures:
  Group 1: command name (letters, digits, hyphens; must start with letter)
  Group 2: arguments (everything after the first whitespace)

Argument parsing (MVP — positional):
  Arguments are split by whitespace.
  First positional arg maps to first required variable, etc.
  Quoted strings ("hello world") are treated as a single argument.

Argument parsing (future — named):
  --variable_name=value
  --variable_name "value with spaces"
  Mixed positional + named supported

Examples:
  /triage-ticket PROJ-1234
    → command: "triage-ticket", args: {"ticket_number": "PROJ-1234"}

  /list-my-tickets
    → command: "list-my-tickets", args: {}

  /create-pr PROJ-1234
    → command: "create-pr", args: {"ticket_number": "PROJ-1234"}

  /summarize-thread "https://slack.com/archives/C123/p456"
    → command: "summarize-thread", args: {"thread_url": "https://slack.com/archives/C123/p456"}
```

### 6.3 Skills Loading and Injection

**Startup behavior:**
1. Agent middleware calls `GET /api/v1/skills` at startup
2. Caches skill metadata (name, description, tools) in memory
3. Does NOT load full SKILL.md content until needed

**Runtime behavior (implicit discovery):**
1. User sends a message
2. Middleware checks if message matches any skill keywords (simple heuristic for MVP)
3. If match, fetches full SKILL.md via `GET /api/v1/skills/{name}`
4. Injects SKILL.md content as a system prompt addendum before the user message
5. Agent receives augmented context

**Runtime behavior (explicit activation):**
1. User sends `/use-skill code-review`
2. Middleware treats this as a meta-command (not resolved as a template)
3. Fetches full SKILL.md, adds to agent system prompt
4. Returns confirmation to user: "Activated code-review skill. I'll use code review best practices in our conversation."
5. Subsequent messages benefit from skill context

### 6.4 MCP Prompts Protocol Mapping

Every slash command in the registry can also be expressed as an MCP prompt. The MVP includes a mapping layer that demonstrates this equivalence:

```python
# DECISION: MCP prompts mapping is included to show how this system
# can expose commands via the MCP protocol for compatibility with
# Claude Desktop, VS Code, and other MCP clients. The MVP doesn't
# run a full MCP server, but the data model supports it.

def command_to_mcp_prompt(command: Command) -> MCPPrompt:
    """Convert a registry command to an MCP prompt definition."""
    return MCPPrompt(
        name=command.name,
        title=command.display_name,
        description=command.description,
        arguments=[
            MCPPromptArgument(
                name=var.name,
                description=var.description,
                required=var.required,
            )
            for var in command.variables
        ],
        # DECISION: MCP prompts don't have a 'tools' field.
        # We carry tool requirements in the _meta extension field.
        _meta={
            "tools": command.tools,
            "tags": command.tags,
            "version": command.version,
            "source": command.source,
        },
    )
```

### 6.5 Agent Skills Packaging Mapping

Every skill in the registry follows the Agent Skills open standard format:

```python
# DECISION: Agent Skills format (SKILL.md with YAML frontmatter) is
# the packaging standard adopted by Claude Code, OpenAI Codex, Cursor,
# and others. By storing skills in this format natively, our system
# can import/export skills to/from these platforms.

def parse_skill_md(content: str) -> Skill:
    """Parse a SKILL.md file into our internal Skill model.

    The Agent Skills standard defines SKILL.md as:
    - YAML frontmatter (between --- delimiters) with metadata
    - Markdown body with instructions for the agent

    Our internal model adds: id, source, is_active, timestamps.
    These are not part of the standard but needed for registry management.
    """
    frontmatter, body = split_frontmatter(content)
    return Skill(
        name=frontmatter["name"],
        description=frontmatter.get("description", ""),
        skill_md=content,  # Store the raw SKILL.md for re-export
        frontmatter=frontmatter,
        tools=frontmatter.get("tools", []),
        tags=frontmatter.get("tags", []),
    )
```

---

## 7. Code Comment Convention

All source files in the MVP must follow this comment convention to serve as a reference implementation:

### Decision Comments

```python
# DECISION: <What was decided>
# Why: <Rationale>
# Production: <What changes in production>
# Standard: <Which standard this follows, if any>
# Alternative: <What was considered and rejected>
```

**Example:**

```python
# DECISION: SQLite with aiosqlite for the command store
# Why: Zero-dependency, file-based, perfect for MVP. No need to run PostgreSQL.
# Production: Replace with asyncpg + PostgreSQL for concurrent access, JSONB columns,
#   full-text search, and connection pooling. Schema stays the same.
# Standard: N/A (data layer is implementation detail)
# Alternative: Considered in-memory dict (too simple, no persistence) and
#   TinyDB (lacks async support).
```

### Integration Point Comments

```python
# INTEGRATION: <What this connects to>
# Protocol: <Wire protocol used>
# Contract: <API contract reference>
# Production change: <What changes>
```

**Example:**

```python
# INTEGRATION: Prompt Registry Service
# Protocol: HTTP/REST (JSON)
# Contract: See prompt-registry/src/routers/commands.py
# Production change: Consider gRPC for lower latency. If co-located in same
#   pod, could use in-process function call. If using service mesh (Istio),
#   mTLS is handled transparently.
```

### Standards Mapping Comments

```python
# MCP_MAPPING: <How this maps to MCP>
# AGUI_MAPPING: <How this maps to AG-UI>
# AGENT_SKILLS: <How this maps to Agent Skills standard>
# COPILOTKIT: <How this uses CopilotKit APIs>
```

---

## 8. Testing Strategy

### Unit Tests (per component)

| Component | Test Focus | Framework |
|-----------|-----------|-----------|
| Prompt Registry | CRUD operations, resolution logic, variable validation, skill parsing | pytest + httpx (async) |
| Interceptor | Command detection, argument parsing, message rewriting, error handling | pytest |
| Registry Client | HTTP calls, retry logic, error mapping | pytest + respx (mocking) |
| Agent | Prompt processing, tool calling, response formatting | pytest + pydantic-ai test utils |
| Frontend hooks | Slash command detection, autocomplete filtering, form generation | Vitest + React Testing Library |
| Frontend components | Rendering, keyboard navigation, form submission | Vitest + React Testing Library |

### Integration Tests

| Scenario | Verifies |
|----------|----------|
| `/triage-ticket PROJ-1234` → triage response | Full pipeline: parse → resolve → agent → mock tool → response |
| `/list-my-tickets` → ticket list | Parameterless command resolution |
| `/create-pr PROJ-1234` → PR description | Multi-tool orchestration (git + jira) |
| `/nonexistent-command` → error message | Error propagation from registry to UI |
| `/triage-ticket` (missing arg) → param form prompt | Variable validation and error response |
| Normal chat message → agent response | Non-command messages pass through unmodified |
| Skill activation → enriched responses | System prompt injection with skill context |

### Test Comment Convention

```python
def test_triage_ticket_resolution():
    """
    SCENARIO: User invokes /triage-ticket with a valid ticket number
    VERIFIES: Template resolution with variable substitution
    PRODUCTION_NOTE: In production, the jira_get_ticket tool call would
      hit a real Jira API. The resolution logic remains the same.
    """
```

---

## 9. Configuration and Environment

### Environment Variables

```bash
# Prompt Registry Service
REGISTRY_HOST=0.0.0.0
REGISTRY_PORT=8001
DATABASE_URL=sqlite+aiosqlite:///./commands.db
SKILLS_DIR=./src/skills
LOG_LEVEL=INFO

# Agent Middleware
MIDDLEWARE_HOST=0.0.0.0
MIDDLEWARE_PORT=8000
REGISTRY_URL=http://prompt-registry:8001
LLM_MODEL=claude-sonnet-4-5-20250929
LLM_API_KEY=your-api-key-here
# DECISION: LLM_API_KEY is an env var for MVP.
# Production: Use K8s Secret mounted as a volume, or Vault.

# Frontend
VITE_COPILOTKIT_RUNTIME_URL=http://localhost:8000/copilotkit
VITE_REGISTRY_URL=http://localhost:8001
```

### docker-compose.yml Structure

```yaml
services:
  prompt-registry:
    build: ./prompt-registry
    ports: ["8001:8001"]
    volumes:
      - ./prompt-registry/src/skills:/app/skills:ro
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///./data/commands.db

  agent-middleware:
    build: ./agent-middleware
    ports: ["8000:8000"]
    depends_on: [prompt-registry]
    environment:
      - REGISTRY_URL=http://prompt-registry:8001
      - LLM_API_KEY=${LLM_API_KEY}

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    depends_on: [agent-middleware, prompt-registry]
```

---

## 10. Production Migration Notes (to be included in PRODUCTION_NOTES.md)

Each of these is also called out in code via `# DECISION:` and `# Production:` comments:

| MVP Choice | Production Replacement | Rationale |
|------------|----------------------|-----------|
| SQLite | PostgreSQL (asyncpg) | Concurrent access, JSONB, full-text search |
| In-process mock MCP tools | Separate MCP servers (stdio/SSE) | Real tool isolation, independent scaling |
| HTTP between services | gRPC or in-process (if co-located) | Lower latency for high-frequency resolution |
| No auth | JWT + mTLS (Istio) | Government security requirements |
| No RBAC | Per-command role-based access | Multi-tenant, least-privilege |
| Env var for API key | K8s Secret or Vault | Secrets management |
| docker-compose | Helm chart + K8s | Production orchestration |
| Filesystem skills | DB-stored skills + hot reload | Dynamic skill management |
| Simple keyword skill matching | Embedding-based skill discovery | Intelligent skill activation |
| No versioning | Command version history table | Audit trail, rollback |
| No caching | Redis cache with TTL | Performance at scale |
| CopilotKit cloud | Self-hosted CopilotKit runtime | Air-gapped deployment |
| Single agent | Agent routing based on command type | Specialized agents per domain |

---

## 11. Success Criteria

The MVP is complete when:

1. A user can type `/triage-ticket PROJ-1234` in the chat UI and receive a structured triage analysis that used mock Jira data
2. A user can type `/list-my-tickets` and see a formatted list of mock tickets
3. A user can type `/create-pr PROJ-1234` and receive a generated PR description
4. A user can type a normal message (no `/` prefix) and receive a standard agent response
5. The slash command autocomplete dropdown appears when the user types `/` and filters as they type
6. Missing required parameters trigger a parameter form or a helpful error message
7. The skill catalog sidebar shows available skills
8. Activating a skill enriches subsequent agent responses
9. All code files contain `# DECISION:` comments documenting every architectural choice
10. `docker-compose up` starts the entire stack and all integration tests pass
11. ARCHITECTURE.md documents the full decision tree with references to code
12. PRODUCTION_NOTES.md provides a clear migration path to K8s deployment

---

## 12. Estimated Timeline

| Phase | Duration | Deliverables |
|-------|----------|-------------|
| Phase 1: Prompt Registry | 3 days | Working API with seed data, resolution, skills |
| Phase 2: Agent Middleware | 2 days | Command interceptor, agent, mock tools |
| Phase 3: Frontend | 2 days | Chat UI, autocomplete, param forms, skill catalog |
| Phase 4: Integration | 2 days | docker-compose, e2e tests, documentation |
| **Total** | **~9 working days** | **Full reference implementation** |

---

## 13. Open Questions and Future Considerations

These are deliberately out of scope for the MVP but documented for future planning:

1. **Multi-turn command workflows:** Some commands may need follow-up questions (e.g., `/create-pr` needs branch selection). Pattern: command returns a "continuation" that the interceptor handles as a multi-step flow.

2. **Command chaining:** `/triage-ticket PROJ-1234 | /create-pr PROJ-1234` — pipe output of one command as context for the next. This is a significant UX and architectural question.

3. **User-custom command authoring UI:** A form-based editor for creating new commands without writing templates directly. Consider a template playground with live preview.

4. **Marketplace API design:** Authentication, publisher verification, rating/review system, licensing, usage analytics. Consider OCI registry compatibility for air-gapped distribution.

5. **Skill auto-discovery via embeddings:** Instead of keyword matching, embed skill descriptions and user messages, use cosine similarity to suggest relevant skills. Requires a vector store.

6. **CRD migration (Pattern 3):** When to migrate command definitions from PostgreSQL to Kubernetes CRDs. Likely when GitOps-managed command promotion (dev → staging → prod) becomes a requirement.

7. **MCP prompt server mode:** Expose the Prompt Registry as a full MCP server (not just REST) so Claude Desktop and other MCP clients can discover and invoke commands natively.

8. **Telemetry and observability:** Command usage metrics, resolution latency, error rates. Integrate with Elastic APM (per existing company stack).
