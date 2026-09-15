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

    # ── LLM — shared defaults ─────────────────────────────────────────────────
    # Used by any agent that does not have its own override below.
    llm_model: str = "gpt-4o"
    llm_api_key: str | None = None    # optional: overrides provider-specific key
    llm_base_url: str | None = None   # optional: for local/institutional endpoints
    llm_max_retries: int = 3
    llm_temperature: float = 0.0

    # ── LLM — DiagnosisAgent overrides ───────────────────────────────────────
    # Falls back to the shared llm_* values when not set.
    # DiagnosisAgent does multi-step ReAct — use a strong reasoning model.
    diagnosis_llm_model: str | None = None
    diagnosis_llm_api_key: str | None = None
    diagnosis_llm_base_url: str | None = None

    # ── LLM — FixPlanningAgent overrides ─────────────────────────────────────
    # Falls back to the shared llm_* values when not set.
    # FixPlanning is a single call — a cheaper/faster model is often sufficient.
    fix_planning_llm_model: str | None = None
    fix_planning_llm_api_key: str | None = None
    fix_planning_llm_base_url: str | None = None

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
