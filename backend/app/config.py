"""Centralised application configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values come from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- LLM (OpenAI-compatible) ---
    OPENAI_API_KEY: str = "sk-placeholder"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536

    # --- Optional RapidAPI CodeRunner ---
    RAPIDAPI_KEY: str = ""
    RAPIDAPI_CODERUNNER_HOST: str = ""

    # --- PostgreSQL ---
    POSTGRES_USER: str = "tutor"
    POSTGRES_PASSWORD: str = "tutor_pass"
    POSTGRES_DB: str = "tutor"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    # --- Qdrant ---
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "tutor_content"

    # --- Redis ---
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    # --- Code executor ---
    CODE_EXECUTOR_URL: str = "http://code-executor:9000"
    EXECUTION_TIMEOUT_SECONDS: int = 10
    EXECUTION_MEMORY_MB: int = 256

    # --- Web search (SearXNG via SearXNG MCP server) ---
    # Fully optional and fail-open: if these services are unavailable the tutor
    # still works (no remediation links / curated tasks only). The MCP server is
    # the primary path; the direct SearXNG URL is the fallback. INTERNET_TASKS
    # is the master switch for live, sandbox-verified task generation.
    SEARXNG_URL: str = "http://searxng:8080"
    SEARXNG_MCP_URL: str = "http://searxng-mcp:8077"
    INTERNET_TASKS_ENABLED: bool = True

    # --- Adaptive behaviour ---
    COOLDOWN_SOLVES: int = 500
    MAX_REGEN_ATTEMPTS: int = 3
    MASTERY_SUCCESS_STREAK: int = 2
    ADVANCED_SUCCESS_STREAK: int = 3

    # --- Guardrails ---
    # On-topic guardrail: when enabled, off-topic chat (not about programming or
    # the current learning process) is politely declined. Fail-open if the LLM
    # classifier is unavailable. Runtime-editable via the graph settings API/UI.
    TOPIC_GUARD_ENABLED: bool = True

    # --- Langfuse observability (optional tracing of the LangGraph run) ---
    # Tracing is fully optional: if either key is empty it is disabled and the
    # backend runs normally without any observability.
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "http://langfuse:3000"

    # --- Authentication (application JWT auth — NOT Langfuse) ---
    # Secret used to sign application JWTs. A dev default is provided so the
    # stack runs out-of-the-box; CHANGE THIS IN PRODUCTION via .env.
    JWT_SECRET: str = "dev-insecure-change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # --- Default application user (seeded at startup) ---
    # Acts both as a ready-to-use login AND as a safeguard guaranteeing at least
    # one valid user row exists (so skill_progress FKs never dangle).
    APP_DEFAULT_USER_EMAIL: str = "admin@example.com"
    APP_DEFAULT_USER_PASSWORD: str = "qwerty123456"
    APP_DEFAULT_USER_NAME: str = "admin"
    APP_DEFAULT_USER_LANGUAGE: str = "python"

    # --- App ---
    SEED_ON_STARTUP: bool = True
    LOG_LEVEL: str = "INFO"

    # ------------------------------------------------------------------
    @property
    def sqlalchemy_url(self) -> str:
        """SQLAlchemy (psycopg2) connection URL."""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def psycopg_url(self) -> str:
        """Plain libpq URL used by the LangGraph Postgres checkpointer."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def rapidapi_enabled(self) -> bool:
        return bool(self.RAPIDAPI_KEY and self.RAPIDAPI_CODERUNNER_HOST)

    @property
    def langfuse_enabled(self) -> bool:
        """True only when both Langfuse keys are configured."""
        return bool(self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY)

    @property
    def search_enabled(self) -> bool:
        """True when a SearXNG endpoint (MCP or direct) is configured.

        Search is always fail-open at the call site; this only reflects whether
        an endpoint is set at all.
        """
        return bool(self.SEARXNG_MCP_URL or self.SEARXNG_URL)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
