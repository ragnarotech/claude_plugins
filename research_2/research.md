# Slash command architectures for AI agent systems

**Three viable architectural patterns emerge for implementing slash commands as prompt substitution and skill invocation, each with distinct tradeoffs for the AGUI/CopilotKit/Pydantic AI/MCP stack.** The most important finding is that MCP prompts were explicitly designed for this exact use case — the spec literally shows prompts as `/code_review` in a chat interface — but the protocol has significant gaps (no versioning, no RBAC, no argument types) that require supplemental infrastructure. Meanwhile, the industry is converging on the **Agent Skills open standard** (agentskills.io), now adopted by Claude Code, OpenAI Codex, Cursor, GitHub Copilot, and VS Code, which provides a richer packaging format. The right architecture depends on whether you optimize for standards alignment, operational simplicity, or government-grade security controls.

## How existing platforms solve this problem

The platforms researched split into two camps: **client-side prompt expansion** (Open WebUI) and **server-side skill resolution** (Claude Code, Codex). Neither AG-UI nor CopilotKit currently have any slash command specification or skill registry — these are application-layer concerns left to the developer.

**Open WebUI** implements the simplest pattern: slash commands are prompt templates stored in a `prompt` table (SQLite/PostgreSQL) with `{{variable}}` substitution. The frontend detects `/` keystrokes, queries the backend for matching prompts, and expands them client-side. Custom variables like `{{priority | select:options="High,Medium,Low"}}` generate typed modal forms. This is elegant but limited to text expansion — no tool orchestration, no multi-step workflows, no programmatic invocation by the agent. Its community marketplace at openwebui.com enables one-click import of shared prompts.

**Claude Code** represents the most feature-rich implementation. Custom commands are Markdown files with YAML frontmatter stored in `.claude/commands/` (project) or `~/.claude/commands/` (personal). The frontmatter schema supports `allowed-tools`, `argument-hint`, `description`, and `model` override. Parameterization uses `$ARGUMENTS` and positional `$1`-`$9`. Crucially, commands can execute bash inline (`!`git status``) and reference files (`@src/main.py`) for context injection. Claude Code has evolved to a **two-tier system**: simple commands for explicit `/invoke` and Agent Skills (directory packages with `SKILL.md`) for implicit auto-discovery. The agent can even programmatically invoke commands via the `SlashCommand` tool, enabling autonomous command chaining.

**OpenAI Codex** mirrors this architecture almost exactly — deprecated `~/.codex/prompts/` in favor of Agent Skills — but adds named parameters (`$TICKET_ID=value`) and `agents/openai.yaml` for UI metadata and MCP tool dependencies. Both platforms now support the **Agent Skills open standard** from agentskills.io, which packages skills as directories with `SKILL.md` (YAML frontmatter + Markdown instructions), scripts, and resources.

**CopilotKit** provides `useCopilotAction` for frontend action registration and `CopilotAction` via the Python SDK for server-side registration. Actions use a custom parameter schema (`name`, `type`, `description`, `required`, `enum`) but are **model-controlled** (the LLM decides when to invoke them), not user-initiated like slash commands. The `CopilotKitRemoteEndpoint` serves as the middleware, but has **no built-in command interceptor**. Implementing slash commands requires custom logic in the runtime endpoint or a proxy layer. The `useCopilotChatSuggestions` hook generates LLM-powered contextual suggestions, but these cannot be hardcoded command lists (open feature request #1925).

## MCP prompts are purpose-built for this but have real gaps

The MCP prompts primitive is architecturally well-matched to slash commands. **Prompts are explicitly user-controlled** (unlike tools, which are model-controlled), discoverable via `prompts/list`, parameterized via arguments, and support dynamic content generation with embedded resources. The spec states prompts are designed to be "triggered through user-initiated commands in the user interface... for example, as slash commands."

The schema is straightforward. A prompt has `name`, `title`, `description`, and an optional `arguments` array of `PromptArgument` objects (each with `name`, `description`, `required`). When invoked via `prompts/get`, the server returns a `GetPromptResult` containing an array of `PromptMessage` objects with `role` ("user" or "assistant") and multi-modal `content` (text, image, audio, or embedded resource). The handler is arbitrary server-side code, so it can fetch live data, query databases, and construct dynamic multi-message workflows.

Auto-completion is supported via the `completion/complete` API, and the TypeScript SDK provides Zod validation for arguments. Change notifications (`notifications/prompts/list_changed`) enable live updates when prompts are added or modified.

However, **critical gaps exist** for a production slash command system:

- **No argument type system** at the protocol level — arguments are always `{ [key: string]: string }`, no `type`, `default`, or `enum` fields (contrast with tools which use full JSON Schema)
- **No versioning** — no version field, no migration path, no semantic versioning
- **No access control** — any connected client sees all prompts; no user/role scoping
- **No categories or tags** — only `name`, `title`, `description`
- **No formal tool references** — prompts can instruct the LLM to use tools via text, but there is no schema-level linking
- **No marketplace metadata** — no authorship, licensing, pricing, or ratings
- **String-only arguments** — no arrays, objects, or complex types

The `_meta` extensibility field on prompts can carry custom metadata to partially address some of these gaps.

## AG-UI has no opinion on commands; CopilotKit leaves it to you

**AG-UI deliberately operates below the slash command abstraction.** It defines ~16 event types for agent-to-UI streaming (`TextMessageStart`, `ToolCallStart`, `StateSnapshot`, etc.) but prescribes nothing about command syntax, skill registries, or prompt templates. The `Custom` event type (`name` + `value` fields) could theoretically carry skill invocation payloads, but this is application-defined.

AG-UI, MCP, and A2A form a complementary protocol trinity: **MCP connects agents to tools and context, A2A connects agents to other agents, and AG-UI connects agents to users**. Slash command functionality would span MCP (for prompt/tool definitions) and AG-UI (for user invocation and response streaming).

CopilotKit's runtime middleware — `@copilotkit/runtime` — routes between frontend actions, remote backend agents, and LLM adapters. It handles credential management, streaming SSE connections, and guardrails. But to intercept slash commands before they reach the agent, you must add custom logic in the `CopilotRuntime` endpoint, a custom `useCopilotChat` handler, or a proxy layer. The CoAgent pattern (`useCoAgent`) provides bidirectional state synchronization with Pydantic AI agents via AG-UI events, which means a slash command system could leverage state updates to communicate resolved commands to the agent.

## Three architectural patterns with concrete tradeoffs

### Pattern 1: Slash commands as MCP prompts

In this pattern, a dedicated MCP prompt server acts as the slash command registry. The server exposes prompts via `prompts/list` and `prompts/get`, with each slash command implemented as a prompt handler that performs variable substitution, context injection, and tool reference embedding.

**Resolution flow:**
```
User types "/triage-ticket 1234"
  → Frontend detects "/" prefix, queries MCP server via prompts/list for autocomplete
  → User confirms → Frontend calls prompts/get with arguments: { "ticket_number": "1234" }
  → MCP server handler: fetches ticket data, constructs multi-message prompt with embedded resources
  → Returns PromptMessage[] to client
  → Client injects messages into conversation → Agent processes with tool references in prompt text
```

**Implementation:** The MCP prompt server is a Python service (using the `mcp` SDK) deployed as a Kubernetes Deployment. Each slash command is a registered prompt with a handler function. The handler can call external APIs, query databases, and embed resources dynamically. For parameterization, arguments are declared in the prompt definition and received as a string dictionary. Tool orchestration is encoded in the prompt text itself ("Use the `jira_get_ticket` tool to fetch details...").

**Evolution path:** Start with hardcoded prompt handlers in Python code. For user-custom commands, add a database backend (PostgreSQL) that the prompt server reads from, with a CRUD API for creating/editing prompts. For marketplace, the MCP prompt server can aggregate prompts from multiple sources (local DB + remote registries). The `notifications/prompts/list_changed` mechanism handles live updates.

**Key tradeoffs:**
- **Strongest standards alignment** — uses MCP exactly as designed; compatible with VS Code, Claude Desktop, and any MCP client
- **Lowest coupling** — the MCP server is independent of CopilotKit; works with any MCP-compatible client
- **Weakest RBAC** — MCP has no access control; you must implement auth at the transport layer (mTLS, API gateway) or in server-side handler logic
- **Weakest parameterization** — string-only arguments, no typed forms, no client-side validation
- **Latency** — extra network hop to MCP server for every command invocation
- **Tool orchestration is implicit** — prompt text instructs the LLM, but there is no formal guarantee the right tools are available

### Pattern 2: Middleware microservice with prompt template registry

In this pattern, a standalone CRUD microservice stores slash command definitions in PostgreSQL and resolves them at the CopilotKit middleware layer before the agent sees them. The command never reaches the LLM as a raw `/command` — it arrives as a fully expanded prompt with injected context.

**Resolution flow:**
```
User types "/triage-ticket 1234"
  → Frontend detects "/" prefix, queries Command Registry API for autocomplete
  → User confirms → Frontend sends message to CopilotKit runtime with command metadata
  → Middleware intercepts: calls Command Registry API to resolve template
  → Registry returns: template + variable definitions + tool requirements + auth requirements
  → Middleware performs variable substitution, injects user context (from JWT/mTLS identity)
  → Middleware ensures required MCP tools are available
  → Resolved prompt sent to Pydantic AI agent as a regular message
  → Agent processes normally, calling tools as instructed
```

**Implementation:** The Command Registry is a FastAPI microservice with PostgreSQL, exposing REST endpoints: `GET /commands` (list/search), `GET /commands/{name}` (get definition), `POST /commands` (create), `PUT /commands/{name}` (update), `DELETE /commands/{name}` (soft delete). The schema includes: `name`, `description`, `template` (with `{{variable}}` placeholders), `variables` (typed: string, number, select, etc.), `tools` (MCP tool references), `rbac` (allowed roles/groups), `version`, `tags`, `author`. Resolution logic lives in a custom middleware layer added to the CopilotKit runtime endpoint.

**Evolution path:** Hardcoded commands seeded into PostgreSQL on deploy. User-custom commands via the CRUD API with RBAC (users create in their namespace, admins publish globally). Marketplace via a federated registry pattern — the local service can sync from a remote marketplace API, similar to how Helm chart repos work. **Version history** maintained via an immutable `command_versions` table (every edit creates a new version; aliases like "production" and "staging" point to specific versions, following the MLflow/LangChain Hub pattern).

**Key tradeoffs:**
- **Richest parameterization** — typed variables with validation, select/checkbox/date fields (Open WebUI pattern), client-side form generation
- **Strongest RBAC** — per-command role-based access, namespace scoping, audit logging, all in your control
- **Best marketplace path** — the registry service naturally evolves into a marketplace API with authorship, versioning, ratings, licensing metadata
- **Highest coupling** — tightly integrated with CopilotKit middleware; not portable to other platforms
- **Not standards-compliant** — custom protocol, not MCP or Agent Skills; tools that speak MCP won't discover these commands
- **Most complex** — requires building and maintaining a full CRUD service, database schema, migration system, and middleware interceptor
- **Best for government** — full control over auth propagation, audit trails, and data residency

### Pattern 3: Hybrid — MCP prompts + Kubernetes CRD + Agent Skills packaging

This pattern combines MCP prompts as the wire protocol, Kubernetes CRDs as the source of truth, and the Agent Skills standard for packaging and distribution. A Kubernetes operator watches `SlashCommand` CRDs and reconciles them into an MCP prompt server, while the CopilotKit middleware orchestrates resolution.

**Resolution flow:**
```
User types "/triage-ticket 1234"
  → Frontend detects "/" prefix
  → CopilotKit middleware queries MCP prompt server (which is backed by CRDs)
  → MCP server returns prompt with embedded resources and tool instructions
  → Middleware enriches with user context from mTLS identity (ServiceAccount → RBAC check)
  → Resolved prompt sent to Pydantic AI agent
  → Agent uses MCP tools (routed via agentgateway with mTLS)
```

**Implementation:** Define a `SlashCommand` CRD with the schema:
```yaml
apiVersion: ai.example.com/v1alpha1
kind: SlashCommand
metadata:
  name: triage-ticket
  namespace: team-platform
spec:
  name: triage-ticket
  description: "Triage a Jira ticket with AI analysis"
  template: |
    Analyze ticket {{ticket_number}}. Use the jira_get_ticket tool to fetch details,
    then assess priority, suggest assignee, and recommend next steps.
  variables:
    - name: ticket_number
      type: string
      required: true
      description: "Jira ticket number (e.g., PROJ-1234)"
  tools:
    - jira_get_ticket
    - jira_update_ticket
  rbac:
    allowedRoles: ["developer", "lead", "manager"]
status:
  phase: Active
  version: "3"
```

A Kubebuilder-based operator watches these CRDs and syncs them to an MCP prompt server. The prompt server's `prompts/list` and `prompts/get` handlers read from the CRD state. For user-custom commands, a CRUD API overlay creates `SlashCommand` CRs dynamically (with appropriate RBAC). For marketplace, adopt the **agentregistry** pattern (Solo.io) — skills packaged as OCI container images with `SKILL.md`, distributable via container registries compatible with air-gapped environments.

GitOps (Argo CD/Flux) manages the CRDs in Git, providing full version history, rollback, and environment promotion (dev → staging → prod via Kustomize overlays). Istio `AuthorizationPolicy` CRDs enforce mTLS and per-command access control. The **agentgateway** (Linux Foundation) provides MCP/A2A routing with built-in OAuth and tool federation.

**Key tradeoffs:**
- **Best standards alignment** — uses MCP prompts (wire protocol), Agent Skills (packaging), Kubernetes APIs (operations), all open standards
- **Strongest security posture** — Kubernetes RBAC on CRDs, Istio mTLS between all services, AuthorizationPolicy for L7 access control, full audit trail via K8s audit logs
- **Best for government/air-gapped** — everything runs on-cluster, no external dependencies, OCI images from internal registry, GitOps from internal Git
- **Most operationally complex** — requires Kubernetes operator development, service mesh configuration, CRD lifecycle management
- **Declarative and GitOps-native** — every command change is a Git commit with author, timestamp, and review
- **Moderate marketplace path** — agentregistry provides OCI-based skill distribution; less natural for a web-based marketplace UI than Pattern 2
- **Latency** — CRD reads are fast (cached by controller), but the full chain (K8s API → operator → MCP server → middleware → agent) adds hops

## Evaluating across all dimensions

| Dimension | Pattern 1: MCP Prompts | Pattern 2: Middleware µService | Pattern 3: Hybrid CRD+MCP |
|---|---|---|---|
| **Standards compliance** | ★★★★★ MCP-native | ★★☆☆☆ Custom protocol | ★★★★★ MCP + K8s + Agent Skills |
| **Parameterization** | ★★☆☆☆ String-only args | ★★★★★ Typed, validated forms | ★★★☆☆ CRD-typed, MCP string wire |
| **RBAC / Auth** | ★★☆☆☆ Transport-layer only | ★★★★★ Full application RBAC | ★★★★★ K8s RBAC + Istio AuthZ |
| **Tool orchestration** | ★★★☆☆ Implicit via prompt text | ★★★★☆ Explicit tool requirements | ★★★★☆ CRD-declared tools |
| **Marketplace evolution** | ★★★☆☆ MCP server aggregation | ★★★★★ Natural CRUD → marketplace | ★★★★☆ OCI-based via agentregistry |
| **CopilotKit integration** | ★★★★☆ MCP-compatible agent | ★★★★★ Deep middleware integration | ★★★☆☆ Requires middleware bridge |
| **Operational complexity** | ★★☆☆☆ Low (single service) | ★★★☆☆ Medium (API + DB) | ★★★★★ High (operator + mesh) |
| **Government readiness** | ★★★☆☆ Needs auth overlay | ★★★★☆ Good with custom auth | ★★★★★ K8s-native zero-trust |
| **Portability** | ★★★★★ Any MCP client | ★☆☆☆☆ CopilotKit-specific | ★★★★☆ K8s + MCP ecosystems |
| **Hardcoded → custom → marketplace** | ★★★☆☆ Code → DB → federation | ★★★★★ Seed → CRUD → marketplace API | ★★★★☆ CRD → dynamic CR → registry |

## The Agent Skills standard changes the calculus

A critical finding is the emergence of the **Agent Skills open standard** (agentskills.io), maintained by Anthropic and adopted by OpenAI, Cursor, GitHub Copilot, VS Code, Amp, Letta, and others. Skills are directory packages with `SKILL.md` (YAML frontmatter + Markdown instructions), optional scripts, templates, and resources. They support progressive disclosure (only metadata loaded at startup, full instructions on demand) and are framework-agnostic.

For any pattern chosen, **adopting Agent Skills as the packaging format is strongly recommended**. This means slash command definitions should be expressible as `SKILL.md` files, enabling interoperability with Claude Code, Codex, and the broader ecosystem. The packaging format is orthogonal to the registry pattern — Agent Skills can be stored in a PostgreSQL database (Pattern 2), as Kubernetes CRDs (Pattern 3), or served from an MCP prompt server (Pattern 1).

The **kagent** project (CNCF Sandbox, by Solo.io) already implements container-based Agent Skills on Kubernetes with CRDs for agents, model configs, and MCP servers. The companion **agentregistry** provides OCI-based skill distribution. These are directly usable building blocks for Pattern 3.

## Conclusion

**For this specific stack** (AGUI CopilotKit → Pydantic AI → MCP tools → Kubernetes → government-grade security), **Pattern 2 (middleware microservice) is the recommended starting point** with a clear migration path toward Pattern 3. The reasoning: CopilotKit has no native slash command system, so you must build the interception layer regardless. A FastAPI CRUD service with PostgreSQL is operationally simple, gives you full control over typed parameterization and RBAC, and naturally evolves into a marketplace. The MCP prompts protocol should be used as an **output format** — the middleware resolves commands and constructs MCP-compatible `PromptMessage[]` arrays that the Pydantic AI agent consumes.

When the system matures and Kubernetes-native security controls become essential (mTLS, namespace isolation, GitOps-managed command definitions), **migrate the source of truth to CRDs (Pattern 3)** with the operator syncing to the existing CRUD API for backward compatibility. Package commands in Agent Skills format from day one to ensure ecosystem interoperability. The `_meta` field on MCP prompts can carry your custom metadata (version, tags, RBAC rules) as a bridge between the MCP wire protocol and your richer command model.

The key insight from Claude Code and Codex is that slash commands and skills are not the same thing — **commands are explicit, user-invoked shortcuts; skills are implicit, agent-discovered capabilities**. Plan for both from the start: slash commands for deterministic workflows (`/triage-ticket`, `/create-pr`) and skills for flexible AI-driven task matching. The Agent Skills standard supports both invocation modes.