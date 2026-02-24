# Architecture Decision Record: Slash Command MVP

## Pattern Selection

### The three candidate patterns

Before building, three architectural patterns were evaluated for implementing slash commands in an AI chat system:

**Pattern 1 — Frontend-only (client-side command map):** The frontend holds a static map of command names to prompt templates. On `/command`, the template is rendered client-side and sent to the LLM as a normal message. Simple but has no centralized management, no auth context injection, and no way to update commands without a frontend deploy.

**Pattern 2 — Middleware Microservice with Prompt Template Registry (this implementation):** A dedicated registry service stores command definitions in a database. A middleware layer intercepts all LLM requests, resolves slash commands server-side (substituting variables and injecting auth context), and forwards the resolved prompt to the agent. Commands can be updated without any service restart.

**Pattern 3 — Kubernetes CRD + Operator:** `SlashCommand` custom resources stored in Git, managed by an operator that reconciles CRDs into the prompt registry. GitOps workflow — command changes go through PR review. Maximal auditability and reproducibility, but significant operational overhead (Kubebuilder, Argo CD, OCI skill registry).

### Why Pattern 2 wins for MVP

Pattern 1 was rejected because template security (secrets, user context) cannot be safely handled client-side, and there is no single source of truth for command definitions across teams.

Pattern 3 was rejected for MVP because it requires a running Kubernetes cluster, a Kubebuilder operator, and Argo CD — a stack that takes weeks to bootstrap and is inappropriate for a proof of concept.

Pattern 2 hits the right point on the complexity/value curve:

- Commands are centrally managed and immediately updatable via API.
- Auth context and secrets are injected server-side, never reaching the client.
- The service boundaries match a future Kubernetes deployment with minimal refactoring (each service is already a containerized microservice).
- The data model is compatible with Pattern 3 — adding a CRD operator later means writing a reconciler that calls the existing registry API.

For full rationale, see `research.md` in the parent repository.

## Component Decisions

### 1. Prompt Registry Service

**Decision: FastAPI + SQLite**

FastAPI was chosen for its async-first design (matches the async SQLAlchemy driver), automatic OpenAPI schema generation (useful for this documentation-heavy MVP), and Pydantic v2 integration for request validation. SQLite with `aiosqlite` eliminates the need to run a separate database process during development. The entire database is a single file that can be volume-mounted in docker-compose and inspected with standard SQLite tooling.

Production path: Replace `sqlite+aiosqlite` with `postgresql+asyncpg` in the `DATABASE_URL` environment variable. No application code changes required — SQLAlchemy handles the dialect difference. Add connection pooling parameters and a JSONB column type migration for the `variables` field.

Code reference: `prompt-registry/src/database.py`

**Decision: `{{variable}}` template syntax**

Double-brace syntax was chosen for readability and zero external dependencies. The resolver is a simple `str.replace` loop over the variables dict. This is intentionally minimal — the goal is to make the template mechanism transparent in the code, not to build a general-purpose templating system.

The syntax was chosen over `{variable}` (single brace, conflicts with Python's str.format) and `$variable` (ambiguous in shell scripts) and Jinja2-style `{{ variable }}` (added spaces are visually noisy for short variable names).

Production path: If command templates need conditionals, loops, or filters, migrate the resolver to use Jinja2's `Environment` with `undefined=StrictUndefined`. The `{{variable}}` syntax is a subset of valid Jinja2 syntax, so existing templates remain valid.

Code reference: `prompt-registry/src/services/command_resolver.py`

**Decision: Soft deletes**

Commands and skills are never physically deleted from the database. The `deleted_at` timestamp is set on "delete" requests, and all list/lookup queries filter on `deleted_at IS NULL`. This preserves the audit trail for commands that have been retired, allows accidental deletions to be recovered by an admin with direct database access, and avoids foreign key complications if a command_versions table is added later.

Production path: Add a `command_versions` table (immutable append-only log of every PUT/PATCH to a command). Add an admin endpoint to hard-delete or purge old versions.

Code reference: `prompt-registry/src/routers/commands.py`

**Decision: SKILL.md format (Agent Skills standard)**

Skills are stored as `SKILL.md` files following the Agent Skills open standard (agentskills.io). This format is recognized by Claude Code, OpenAI Codex, GitHub Copilot, Cursor, VS Code, and Amp. Using the standard format means skills written for this MVP can be shared across tools without conversion, and skills from external sources can be imported directly.

The format uses YAML frontmatter (between `---` delimiters) for machine-readable metadata and Markdown body for human/agent-readable instructions. This is the same pattern used by Jekyll, Hugo, and GitHub Pages — a widely understood convention.

Production path: Add an OCI-compatible registry for skill distribution (agentregistry pattern). Skills become versioned, signed artifacts that can be pulled like container images.

Code reference: `prompt-registry/src/services/skill_loader.py`

### 2. Agent Middleware

**Decision: Intercept at middleware, not frontend**

Slash command resolution happens in the middleware service, not in the frontend JavaScript. This is the key architectural decision of Pattern 2. The reasons:

1. **Template security:** Prompt templates may include instructions that reference internal system behavior. These should not be visible in browser DevTools or network inspector.
2. **Auth context injection:** The resolved prompt may include the current user's email, team, or role (fetched from the JWT or session). This context should come from the server, not from client-provided data.
3. **Centralized audit log:** Every command invocation can be logged with the resolved prompt text for debugging and compliance.
4. **Consistent behavior across clients:** The same command resolution logic applies whether the request comes from the React frontend, a CLI client, or a Slack integration.

Code reference: `agent-middleware/src/main.py`

**Decision: Replace user message with resolved prompt**

When a slash command is detected, the interceptor fetches the resolved prompt from the registry and substitutes it for the original user message text before passing the request to the Pydantic AI agent. The agent receives a fully-rendered prompt and has no knowledge that a slash command was involved.

This design keeps the agent layer completely agnostic of the command system. The agent does not need to understand `/triage-ticket` — it just receives a detailed prompt asking it to triage a specific ticket. This means the agent can be swapped out (different model, different agent framework) without touching the command resolution logic.

Code reference: `agent-middleware/src/main.py` (`copilotkit_endpoint` function)

**Decision: Mock MCP tools in-process**

In a production system, MCP (Model Context Protocol) tools would run as separate server processes communicating over stdio or SSE transport. For the MVP, mock tool implementations are registered as Python functions within the same process as the agent. This eliminates the need to manage MCP server processes during development while preserving the same tool-calling interface the agent would use in production.

The mock tools return deterministic fixture data keyed on the input arguments, which makes demos predictable and tests fast.

Production path: Replace in-process mock registrations with MCP client connections. Each tool category (Jira, GitHub, Slack) becomes a separate MCP server process. The agent-middleware becomes an MCP client that discovers available tools from each server's tool manifest.

Code reference: `agent-middleware/src/mcp_tools/`

**Decision: Manual SSE implementation instead of copilotkit SDK**

The AG-UI protocol events (TextMessageStart, TextMessageContent, TextMessageEnd, RunFinished) are written manually as newline-delimited JSON over an HTTP SSE stream, rather than using the official CopilotKit Python SDK. This choice makes the protocol visible in the code — a reader can see exactly what bytes are sent on the wire, which is valuable for understanding the AG-UI spec and for documentation purposes.

Production path: Replace the manual SSE implementation with the official `copilotkit` Python SDK. The SDK handles event serialization, error propagation, and streaming backpressure correctly.

Code reference: `agent-middleware/src/main.py` (`stream_agent_response` function)

**Decision: Simple keyword-based skill auto-discovery**

When no explicit `/use-skill` command is present, the middleware checks whether the user's message contains keywords that match a skill's name or tags. If a match is found, that skill's instructions are prepended to the system prompt automatically. This is a heuristic — it will have false positives and false negatives.

Production path: Replace keyword matching with embedding similarity. Embed the user's message using `text-embedding-3-small` and compare cosine similarity against pre-computed embeddings of each skill's description. Set a configurable threshold (e.g., 0.75) for automatic activation.

Code reference: `agent-middleware/src/skills_context.py`

### 3. React Frontend

**Decision: Custom `useSlashCommands` hook instead of native CopilotKit**

CopilotKit does not have native slash command support as of the time of this MVP (tracked in CopilotKit issue #1925). The `useSlashCommands` hook was built from scratch to detect `/` input in the chat textarea, fetch available commands from the prompt registry, filter them as the user continues typing, and manage palette open/close state.

Production path: Monitor the CopilotKit repository for native slash command support. Migrate to the native implementation when available to reduce custom code maintenance. The hook's interface is designed to be a drop-in replacement.

Code reference: `frontend/src/hooks/useSlashCommands.ts`

**Decision: CommandPalette above input, not inline autocomplete**

The command palette appears as a floating panel above the chat input, rather than inline autocomplete within the text field. This mirrors the UX pattern established by Discord, Slack, and Linear — users who have used any of these tools will immediately recognize the interaction.

Inline autocomplete (like VS Code's IntelliSense) was considered but rejected because command parameters require a separate data entry step (a modal form), which does not fit the inline autocomplete mental model.

Code reference: `frontend/src/components/CommandPalette.tsx`

**Decision: Parameter forms generated from variable schemas**

When a user selects a command that has required variables, a modal form is shown with one input field per variable. The form schema is derived from the command's `variables` array as returned by the prompt registry. This approach validates that all required parameters are provided before the message is sent, avoids string-parsing errors from commands typed with wrong argument counts, and gives the UI a natural place to show per-variable descriptions and validation errors.

Code reference: `frontend/src/components/ParamFormModal.tsx`

## Protocol Mappings

### AG-UI Events

The AG-UI (Agent-UI) protocol defines a set of server-sent events that the frontend uses to render streaming agent responses. This MVP implements the minimal set required for a text streaming use case:

| Event | When emitted | Payload |
|-------|-------------|---------|
| `TextMessageStart` | Beginning of agent response | `{ messageId, role: "assistant" }` |
| `TextMessageContent` | Each text chunk from the LLM | `{ messageId, delta }` |
| `TextMessageEnd` | Response complete | `{ messageId }` |
| `RunFinished` | Entire agent run complete | `{ threadId, runId }` |

The full AG-UI event set also includes `ToolCallStart`, `ToolCallArgs`, `ToolCallEnd`, `ToolCallResult`, `StateDelta` (for shared state), `MessagesSnapshot` (for state sync), and `Error`. A production implementation would emit tool call events so the frontend can show "Fetching Jira ticket..." progress indicators while the agent is calling tools.

### MCP Prompts Protocol

The prompt registry's data model is designed to be compatible with the MCP Prompts protocol. Each `SlashCommand` record maps to an MCP prompt:

| SlashCommand field | MCP Prompt field |
|-------------------|-----------------|
| `name` | `name` |
| `description` | `description` |
| `template` | `messages[0].content.text` (after variable substitution) |
| `variables` | `arguments` (array of `{ name, description, required }`) |

The registry exposes a `/mcp` endpoint that serves the MCP Prompts manifest, allowing a real MCP client to enumerate and invoke commands using the standard protocol. The MVP does not run a full MCP server (no stdio transport, no capability negotiation), but the data layer is MCP-compatible, so adding a proper MCP server adapter is a thin layer on top.

### Agent Skills Standard

The Agent Skills standard (agentskills.io) defines a portable packaging format for AI agent capabilities. Skills in this MVP follow the standard:

- Skills are stored as `SKILL.md` files with YAML frontmatter.
- The `skill_loader.py` service parses frontmatter at startup using PyYAML.
- At request time, `skills_context.py` fetches active skill records from the database and prepends their Markdown body to the Pydantic AI agent's system prompt.
- Skills can be activated explicitly via `/use-skill <name>` or implicitly via keyword matching.

Because the raw `SKILL.md` content is preserved in the database (not just the parsed fields), skills can be re-exported to disk in their original format — enabling round-trip compatibility with other tools.

## Evolution Path

### Short term (next sprint)

- Add JWT authentication middleware to the agent-middleware service. Validate Bearer tokens from the frontend and extract user identity for auth context injection into resolved prompts.
- Add RBAC per command: add an `allowed_roles` JSON field to the `SlashCommand` model. The interceptor checks the user's role (from JWT claims) against the command's allowed roles before resolving.
- Add a `command_versions` table (immutable append-only log). Every PUT to a command creates a new version row. Add `GET /commands/{name}/versions` to the registry API.
- Support named arguments in addition to positional: parse `--variable=value` syntax in the interceptor so users can write `/triage-ticket --ticket=PROJ-1234` as well as `/triage-ticket PROJ-1234`.

### Medium term

- Migrate prompt registry from SQLite to PostgreSQL 15+. Switch the `DATABASE_URL` to `postgresql+asyncpg://...`. Add a JSONB migration for the `variables` column.
- Add Redis caching for command lookups. Cache the resolved command definition with a short TTL (30s). Invalidate on write.
- Implement real MCP tool servers. Move mock Jira and Git tools to separate Python processes with stdio MCP transport. The agent-middleware becomes an MCP client.
- Replace keyword-based skill discovery with embedding similarity using `text-embedding-3-small`.

### Long term (Pattern 3 migration)

When GitOps-managed command definitions become a requirement (audit-complete change history, PR review for command updates, multi-environment promotion):

1. Define a `SlashCommand` custom resource definition using Kubebuilder.
2. Implement a reconciler that watches `SlashCommand` CRDs and calls the prompt registry API to upsert/delete.
3. Store `SlashCommand` CRDs in Git, managed by Argo CD.
4. Command changes become pull requests with approval workflows and automatic deployment to dev/staging/prod via Kustomize overlays.
5. Integrate OCI-based skill distribution (agentregistry) for sharing skills across clusters.
