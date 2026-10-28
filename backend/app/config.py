"""Application configuration via pydantic-settings.

Loads environment variables from .env file and provides
typed settings accessible throughout the application.
"""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""  

    # LLM Providers
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = ""  # override the default Groq model
    # Groq's free tier gives each model its own daily token quota, so when one is used up
    # (or busy) JobPilot moves to the next. Light tasks (chat, parsing) start with GROQ_LIGHT_MODEL.
    GROQ_FALLBACK_MODELS: str = "openai/gpt-oss-20b,qwen/qwen3.8-27b"
    GROQ_LIGHT_MODEL: str = "openai/gpt-oss-20b"
    OPENAI_MODEL: str = ""  # override the default OpenAI model
    ANTHROPIC_MODEL: str = ""  # override the default Anthropic model

    # Which provider every agent uses. "auto" = Anthropic, then OpenAI, then Groq (first with a key).
    LLM_PROVIDER: str = "auto"

    # Embeddings for resume search: "local" (offline MiniLM, default), "huggingface" (same model via API),
    # or "openai". Each model has its own vector collection; re-save the base resume after switching.
    EMBEDDINGS_PROVIDER: str = "local"
    HUGGINGFACE_API_KEY: str = ""

    # Chat assistant. "auto" follows LLM_PROVIDER; set to override it for the chat only.
    AGENT_PROVIDER: str = "auto"
    AGENT_MODEL: str = ""

    # Nightly board scans and morning digests on the server (services/autopilot.py). Needs
    # SUPABASE_SERVICE_KEY; without it the app scans when the user opens it instead.
    DISCOVERY_AUTO_SCAN: bool = True

    # HR Enrichment
    HUNTER_API_KEY: str = ""

    # Email: the morning digest is sent with Resend (free tier: from onboarding@resend.dev to your own address).
    RESEND_API_KEY: str = ""
    DIGEST_FROM: str = "JobPilot <onboarding@resend.dev>"

    # Shared secret for POST /api/v1/autopilot/tick, called by an external cron (e.g. cron-job.org)
    # so a host that sleeps when idle (Render free tier) still runs the nightly scan and digest.
    CRON_SECRET: str = ""

    # Job Data APIs
    ADZUNA_APP_ID: str = ""
    ADZUNA_API_KEY: str = ""

    # Infrastructure
    REDIS_URL: str = "redis://localhost:6379/0"
    # Inline preserves existing installs; durable requires the Sprint 2 migration
    # and `python -m app.workers.runner`. No Redis broker is required in this mode.
    EXECUTION_MODE: Literal["inline", "durable"] = "inline"
    RUN_LEASE_SECONDS: int = Field(default=120, ge=30, le=1800)
    RUN_POLL_SECONDS: float = Field(default=2.0, ge=0.1, le=60)

    # App Config
    FRONTEND_URL: str = "http://localhost:5173"  # comma-separated for several origins; the first is used in emails
    SECRET_KEY: str = "change-me-in-production"
    DEBUG: bool = True


settings = Settings()
