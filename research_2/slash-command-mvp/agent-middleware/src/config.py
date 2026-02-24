"""
Configuration for the Agent Middleware service.

# DECISION: Environment variables for all config, matching the prompt-registry pattern.
# Why: Env vars are the 12-factor standard; lets Docker/K8s override without rebuilding images.
# Standard: 12-factor App (https://12factor.net/config)
# Production: Non-sensitive config (HOST, PORT, REGISTRY_URL, LLM_MODEL) from K8s ConfigMaps.
#   Sensitive values (LLM_API_KEY) from K8s Secrets mounted as env vars.
# Alternative: Rejected YAML config files -- harder to inject secrets at runtime.

# DECISION: LLM_API_KEY is read from an environment variable for MVP.
# Why: Simplest secure approach for local dev -- never hardcoded in source.
# Production: Mounted from a K8s Secret (e.g., via secretKeyRef in the Deployment spec).
#   Consider Vault or AWS Secrets Manager for rotation without pod restarts.
# Alternative: Rejected .env file in the image -- secrets must not be baked into container layers.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # INTEGRATION: Must match the PORT set in prompt-registry's config.py (8001).
    REGISTRY_URL: str = "http://localhost:8001"

    # DECISION: Default model pinned to a specific version for reproducibility.
    # Why: Model behaviour changes between versions; pinning prevents silent regressions.
    # Production: Override via env var per deployment environment.
    LLM_MODEL: str = "claude-sonnet-4-5-20250929"

    # DECISION: LLM_API_KEY env var for MVP, K8s Secret in production.
    # See module docstring above for full rationale.
    LLM_API_KEY: str = ""

    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
