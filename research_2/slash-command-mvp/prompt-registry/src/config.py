"""
Configuration for the Prompt Registry service.

# DECISION: Use environment variables for all config (not a config file).
# Why: Env vars are the 12-factor standard; lets Docker/K8s override without rebuilding images.
# Production: Sensitive values (DB passwords, API keys) come from K8s Secrets mounted as env vars,
#             NOT from ConfigMaps or hardcoded values. Non-sensitive config (HOST, PORT) can use ConfigMaps.
# Standard: 12-factor App (https://12factor.net/config)
# Alternative: Rejected YAML/TOML config files -- harder to inject secrets at runtime; rejected
#              Vault-style dynamic secrets for MVP due to operational complexity.
"""

# INTEGRATION: Other services (agent-middleware) must match PORT=8001 when calling this service.

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8001

    # DECISION: SQLite path baked in as default; override via DATABASE_URL env var in any environment.
    # Why: Makes local dev zero-config while allowing CI and production to use a different path or engine.
    # Production: Replace with postgresql+asyncpg://user:pass@host/db (from K8s Secret).
    # Alternative: Rejected hardcoded path -- breaks containerized deployments.
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/commands.db"

    SKILLS_DIR: str = "./src/skills"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
