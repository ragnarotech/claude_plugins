# Production Migration Notes

## Overview

This document describes what changes when moving from the MVP (docker-compose + SQLite + in-process mocks) to a production Kubernetes deployment. Each section covers a specific service or concern, with a before/after table and concrete migration steps.

The MVP was designed with production in mind: service boundaries, environment variable configuration, and data models are all compatible with the production architecture. The migration is a series of incremental improvements, not a rewrite.

## Component Changes

### Prompt Registry Service

| MVP | Production |
|-----|-----------|
| SQLite with aiosqlite | PostgreSQL 15+ with asyncpg |
| FILE: `database.py` | Add: asyncpg connection pool, JSONB columns |
| In-memory Python dict cache | Redis with TTL |
| Skills loaded from disk at startup | DB-stored skills with hot reload via inotify |
| No auth | JWT Bearer token validation middleware |
| No RBAC | Per-command `allowed_roles` + per-user namespace |
| No versioning | `command_versions` table (immutable) |
| docker-compose service | K8s Deployment + Service + HPA |

**Migration steps:**

1. Change `DATABASE_URL` from `sqlite+aiosqlite:///./data/commands.db` to `postgresql+asyncpg://user:pass@host/dbname`. SQLAlchemy handles the dialect difference — no application code changes required.
2. Run `alembic upgrade head` to apply schema migrations (create the `alembic_version` table and initial schema on PostgreSQL).
3. Add a `command_versions` table (immutable append-only log). Modify the PUT handler to insert a new version row before updating the current row.
4. Add a `JSONB` column index on the `variables` field in PostgreSQL for efficient querying by variable name.
5. Add a Redis client to `config.py`. Wrap `CommandResolver.resolve()` with a cache decorator: key = `cmd:{name}:{hash(variables)}`, TTL = 30 seconds. Invalidate on any write to the command.
6. Add JWT validation middleware using `python-jose` or `PyJWT`. Validate the `Authorization: Bearer <token>` header on all write endpoints. Extract `sub` and `roles` claims.
7. Add `allowed_roles: list[str]` field to the `SlashCommand` model. The interceptor in agent-middleware checks the user's role (forwarded in the `X-User-Roles` header after JWT validation) against `allowed_roles`.
8. Replace the startup skill loader with an inotify watcher (`watchdog` library) so skill file changes hot-reload into the database without a service restart.

### Agent Middleware

| MVP | Production |
|-----|-----------|
| Anthropic API key in `.env` | K8s Secret mounted as env var, or Vault sidecar |
| Mock MCP tools in-process | Separate MCP server processes (stdio/SSE transport) |
| Manual SSE implementation | Official copilotkit Python SDK |
| HTTP to prompt registry | gRPC (if co-located) or HTTP/2 with mTLS |
| Single agent | Agent routing: different agents per command domain |
| Simple keyword skill matching | Embedding similarity (text-embedding-3-small) |
| No streaming backpressure | Proper streaming with backpressure handling |

**Migration steps:**

1. Remove `LLM_API_KEY` from `.env`. Mount it as a K8s Secret: `kubectl create secret generic llm-credentials --from-literal=api-key=sk-ant-...`. Reference in the Deployment manifest as `env.valueFrom.secretKeyRef`.
2. For Vault: annotate the Pod with `vault.hashicorp.com/agent-inject: "true"` and `vault.hashicorp.com/agent-inject-secret-llm: "secret/llm/api-key"`. The Vault agent sidecar writes the secret to `/vault/secrets/llm` at startup.
3. Replace in-process mock tools with MCP client connections. Each tool domain (Jira, GitHub, Slack, PagerDuty) becomes a separate Python process exposing an MCP server over stdio or SSE. The middleware spawns MCP client connections using `mcp.client.stdio.stdio_client()` from the official MCP Python SDK.
4. Replace the manual SSE implementation in `stream_agent_response()` with the `copilotkit` Python SDK's `CopilotKitResponse` context manager, which handles framing, error propagation, and backpressure correctly.
5. For gRPC between middleware and registry: generate protobufs from the registry's OpenAPI schema using `grpc-tools`. Add mTLS certificates via Istio sidecar injection — no application code changes needed for mTLS.
6. Add agent routing: maintain a mapping from command name prefixes (e.g., `triage-*`, `create-pr`) to specialized Pydantic AI agents configured with domain-specific tool sets and system prompts. Route incoming requests based on the detected command name.
7. Replace keyword skill matching with `openai.embeddings.create(model="text-embedding-3-small", input=message_text)`. Pre-compute and cache skill embeddings at startup. At request time, compute cosine similarity and activate skills above a threshold (default: 0.75).

### Frontend

| MVP | Production |
|-----|-----------|
| CORS open (`*`) | Restrict to known origins + CSP headers |
| Direct fetch to registry | API gateway with rate limiting |
| No auth | OIDC/SSO integration (Auth0, Okta, Cognito) |
| Vite dev server | nginx with proper caching headers |
| No analytics | Command usage telemetry (mixpanel or custom) |

**Migration steps:**

1. Replace `allow_origins=["*"]` in both backend services with an explicit allowlist from the `ALLOWED_ORIGINS` environment variable. Add `Content-Security-Policy` headers to the nginx config.
2. Route all API traffic through an API gateway (Kong, AWS API Gateway, or Istio Gateway). Add rate limiting (e.g., 100 requests/minute per IP) and JWT validation at the gateway layer, removing the need to duplicate auth in each service.
3. Integrate OIDC: add `@auth0/auth0-react` (or equivalent) to the frontend. Wrap the app in `Auth0Provider`. Attach the Bearer token to all requests to the middleware in the `Authorization` header.
4. Replace the `frontend` service with an nginx container serving the `dist/` output from `npm run build`. Add cache-control headers for hashed static assets (`max-age=31536000, immutable`) and a short TTL for `index.html` (`max-age=60`).
5. Add a telemetry service: emit a custom event on each slash command invocation (`command_used: { command_name, user_id, latency_ms }`). Use this to identify the most-used commands and prioritize prompt improvements.

## Kubernetes Deployment

### Helm chart structure (to be created)

```
charts/
  slash-command-mvp/
    Chart.yaml
    values.yaml
    templates/
      prompt-registry-deployment.yaml
      agent-middleware-deployment.yaml
      frontend-deployment.yaml
      ingress.yaml
      secrets.yaml          # external-secrets operator
      hpa.yaml              # HorizontalPodAutoscaler
      servicemonitor.yaml   # Prometheus scrape config
```

The `values.yaml` should parameterize:

- Image tags for each service (for CI/CD promotion)
- Replica counts and HPA min/max
- Resource requests/limits
- Ingress hostname and TLS secret name
- External secrets references (Vault paths or AWS Secrets Manager ARNs)
- Environment-specific overrides (dev/staging/prod via Kustomize or Helm `--values`)

### Resource estimates (starting point, tune with load testing)

| Service | CPU request | CPU limit | Memory request | Memory limit | HPA target |
|---------|-------------|-----------|----------------|--------------|------------|
| prompt-registry | 100m | 500m | 128Mi | 512Mi | 70% CPU |
| agent-middleware | 200m | 1000m | 256Mi | 1Gi | 60% CPU |
| frontend (nginx) | 50m | 200m | 64Mi | 128Mi | 80% CPU |

Note: Agent middleware CPU limit should be generous — Pydantic AI agent runs are bursty (low idle, high during LLM streaming).

### Security hardening (Istio + mTLS)

All inter-service communication should run over mTLS in production. With Istio:

1. Label the namespace: `kubectl label namespace slash-command-mvp istio-injection=enabled`
2. Apply `PeerAuthentication` with `STRICT` mTLS mode:

```yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: slash-command-mvp
spec:
  mtls:
    mode: STRICT
```

3. Apply `AuthorizationPolicy` CRDs for per-service L7 access control:

```yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: allow-middleware-to-registry
  namespace: slash-command-mvp
spec:
  selector:
    matchLabels:
      app: prompt-registry
  rules:
    - from:
        - source:
            principals: ["cluster.local/ns/slash-command-mvp/sa/agent-middleware"]
      to:
        - operation:
            methods: ["GET", "POST"]
            paths: ["/api/v1/*"]
```

4. Add JWT validation via `RequestAuthentication`:

```yaml
apiVersion: security.istio.io/v1beta1
kind: RequestAuthentication
metadata:
  name: jwt-validation
  namespace: slash-command-mvp
spec:
  selector:
    matchLabels:
      app: agent-middleware
  jwtRules:
    - issuer: "https://your-auth-provider.com"
      jwksUri: "https://your-auth-provider.com/.well-known/jwks.json"
```

### Pattern 3 Migration (CRD + Operator)

When GitOps-managed command definitions become a requirement:

1. **Define `SlashCommand` CRD** using Kubebuilder (`kubebuilder init` + `kubebuilder create api`). The CRD spec mirrors the `SlashCommand` database model.

2. **Implement the reconciler:** The controller watches `SlashCommand` CRD events (create/update/delete) and calls the prompt registry API to upsert or soft-delete the corresponding record. Reconciliation is idempotent — the registry is the source of truth for runtime, Git is the source of truth for definitions.

3. **Store CRDs in Git:** Commit `SlashCommand` YAML manifests to the infrastructure repository. Argo CD watches the repository and applies changes to the cluster automatically.

4. **PR workflow for command changes:** Updating a command prompt becomes a pull request. The PR triggers a CI job that validates the template syntax (variable references are valid, no unclosed braces) and optionally runs a dry-run resolve against the staging registry.

5. **Kustomize overlays** for environment promotion:

```
k8s/
  base/
    slash-commands/
      triage-ticket.yaml
      list-my-tickets.yaml
  overlays/
    dev/
      kustomization.yaml    # may override allowed_roles for testing
    staging/
      kustomization.yaml
    prod/
      kustomization.yaml    # production allowed_roles, rate limits
```

6. **OCI skill distribution** (agentregistry): Package skills as OCI artifacts and push to a registry (e.g., ghcr.io). The skill loader can pull skills from the registry at startup using `oras pull`, enabling skill sharing across clusters and organizations without Git submodules.
