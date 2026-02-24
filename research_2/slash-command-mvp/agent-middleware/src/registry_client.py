"""
Async HTTP client for the Prompt Registry Service.

# INTEGRATION: Prompt Registry Service
# Protocol: HTTP/REST (JSON)
# Contract: See prompt-registry/src/routers/commands.py and skills router.
#   Key endpoints consumed:
#     GET  /api/v1/commands                      → list_commands()
#     GET  /api/v1/commands/{name}/resolve       → resolve_command()
#     GET  /api/v1/skills                        → list_skills()
#     GET  /api/v1/skills/{name}                 → get_skill()
# Production changes:
#   - Consider gRPC for lower latency if command resolution becomes a hot path.
#   - If agent-middleware is co-located in the same pod as prompt-registry,
#     an in-process function call avoids network overhead entirely.
#   - If using a service mesh (Istio), mTLS is handled transparently between pods.
#   - Add retry logic with exponential backoff + jitter (tenacity library).
#   - Add circuit breaker (pybreaker) to avoid cascading failures when registry is down.
# Alternative: Considered synchronous httpx calls (simpler) but async is required
#   because the FastAPI endpoint handlers are async; blocking in async context
#   would stall the event loop.
"""

import httpx

from .config import settings


class RegistryClient:
    """Async HTTP client that wraps the Prompt Registry REST API."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        # DECISION: Client instance created at startup, not per-request.
        # Why: httpx.AsyncClient maintains a connection pool; re-creating it per request
        #   would negate the pooling benefit and add latency.
        self._client: httpx.AsyncClient | None = None

    async def start(self):
        """Initialise the connection pool. Call during application startup."""
        # DECISION: httpx AsyncClient with connection pooling and a 5 s timeout.
        # Production: Add retry logic with exponential backoff, circuit breaker,
        #   and propagate trace context (OpenTelemetry) via request headers.
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=5.0,
            headers={"Content-Type": "application/json"},
            follow_redirects=True,
        )

    async def stop(self):
        """Close the connection pool. Call during application shutdown."""
        if self._client:
            await self._client.aclose()

    async def list_commands(self, search: str | None = None) -> list[dict]:
        """Return all active commands, optionally filtered by search string."""
        params: dict = {}
        if search:
            params["search"] = search
        resp = await self._client.get("/api/v1/commands", params=params)
        resp.raise_for_status()
        return resp.json()

    async def resolve_command(
        self,
        name: str,
        arguments: dict,
        user_context: dict | None = None,
    ) -> dict:
        """Resolve a command template with concrete arguments.

        Returns a ResolvedCommand dict on success, or an error dict on failure.

        # INTEGRATION: /api/v1/commands/{name}/resolve accepts variables as query params.
        #   Special params prefixed with _ carry contextual metadata:
        #     _user → identity injected by middleware (never from the browser)
        #     _env  → deployment environment (dev / staging / prod)
        #   These are available as $user and $env in command templates.
        # DECISION: User context injected here, not in the frontend.
        # Why: The frontend is untrusted. Server-side injection prevents spoofing.
        # Production: Replace "andrew@company.com" with the identity extracted from
        #   a verified JWT (Authorization header) or mTLS client certificate.
        """
        params: dict = {**arguments}
        if user_context:
            params["_user"] = user_context.get("user", "anonymous")
            params["_env"] = user_context.get("env", "dev")

        resp = await self._client.get(
            f"/api/v1/commands/{name}/resolve", params=params
        )

        if resp.status_code == 404:
            return {
                "error": {
                    "code": "COMMAND_NOT_FOUND",
                    "message": f"Command '{name}' not found",
                }
            }
        if resp.status_code == 422:
            # Registry returns a ResolutionError body describing missing variables.
            return {"error": resp.json()}

        resp.raise_for_status()
        return resp.json()

    async def list_skills(self) -> list[dict]:
        """Return metadata for all active skills."""
        resp = await self._client.get("/api/v1/skills")
        resp.raise_for_status()
        return resp.json()

    async def get_skill(self, name: str) -> dict | None:
        """Fetch a single skill by name. Returns None if not found."""
        resp = await self._client.get(f"/api/v1/skills/{name}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


# Module-level singleton shared across all request handlers.
# DECISION: Module-level singleton for the registry client.
# Why: Shares the connection pool across all requests in the same process.
#   Avoids re-creating the pool on every request (expensive) or passing the
#   client through every function call (verbose).
# Production: Same pattern. In tests, override via dependency injection.
registry_client = RegistryClient(settings.REGISTRY_URL)
