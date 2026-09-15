from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_file_encoding="utf-8")

    # ── Service ───────────────────────────────────────────────────────────────
    service_name: str = "pegasus-remediation"
    debug: bool = False

    # ── Database ──────────────────────────────────────────────────────────────
    # Set to a postgresql+asyncpg:// URL for production persistence.
    # Leave empty to use SQLite (sqlite_path) — no server needed.
    database_url: str = ""
    sqlite_path: str = "checkpoints.db"   # used when database_url is not postgresql

    # ── AMQP ──────────────────────────────────────────────────────────────────
    amqp_enabled: bool = False   # set to true to enable RabbitMQ event consumer
    amqp_url: str = "amqp://pegasus:pegasus_secret@localhost:5672/pegasus"
    amqp_exchange: str = "pegasus"
    amqp_queue: str = "pegasus.remediation"
    amqp_dead_letter_queue: str = "pegasus.remediation.dlq"
    amqp_routing_keys: list[str] = Field(
        default=["stampede.job_inst.*", "stampede.inv.*", "stampede.xwf.*"]
    )
    amqp_prefetch_count: int = 10

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_lock_ttl_seconds: int = 300
    redis_dedup_ttl_seconds: int = 86400  # 24 h

    # ── LLM — provider-agnostic via LiteLLM ──────────────────────────────────
    # Set LLM_MODEL to any model string LiteLLM supports.
    # Set the provider-specific key in env (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
    # or pass it via LLM_API_KEY for custom endpoints.
    llm_model: str = "gpt-4o"
    llm_api_key: str | None = None    # optional: overrides provider-specific key
    llm_base_url: str | None = None   # optional: for local/institutional endpoints
    llm_max_retries: int = 3
    llm_temperature: float = 0.0

    # ── Policy ────────────────────────────────────────────────────────────────
    policy_file: str = "policies/remediation.yaml"
    confidence_threshold: float = 0.80

    # ── Retry gate ────────────────────────────────────────────────────────────
    max_global_attempts: int = 5
    retry_outcome_timeout_seconds: int = 3600

    # ── Evidence collection ───────────────────────────────────────────────────
    log_excerpt_max_bytes: int = 8192   # sent to agents; full log stored by ref
    kickstart_excerpt_max_bytes: int = 16384

    # ── Observability ─────────────────────────────────────────────────────────
    log_level: str = "INFO"
    otlp_endpoint: str | None = None


settings = Settings()
