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
        extra="ignore",
        hide_input_in_errors=True,
    )

    # Database: local Postgres + pgvector (compose.yaml), e.g.
    # postgresql+psycopg://jobdots:<password>@127.0.0.1:55432/jobdots
    DATABASE_URL: str = ""
    DATABASE_POOL_SIZE: int = Field(default=10, ge=1, le=50)
    # Uploaded originals (resume files). Kept on local disk, never in git.
    FILE_STORAGE_DIR: str = "data/files"

    # Owner auth (single user). OWNER_API_TOKEN is the bearer token for the API (32+ random
    # characters). OWNER_ID optionally pins the owner's uuid (e.g. the old JobPilot user id).
    OWNER_EMAIL: str = ""
    OWNER_API_TOKEN: str = ""
    OWNER_ID: str = ""

    # Nightly encrypted backups (plan section 9.2). BACKUP_ENCRYPTION_KEY stays only in the
    # local .env (keep a copy in your password manager: without it no backup can be restored).
    BACKUP_ENABLED: bool = True
    BACKUP_ENCRYPTION_KEY: str = ""
    BACKUP_DIR: str = "data/backups"
    BACKUP_HOUR: int = Field(default=2, ge=0, le=23)  # local time (policy.yaml timezone)
    BACKUP_KEEP_DAILY: int = Field(default=7, ge=1, le=60)
    BACKUP_KEEP_WEEKLY: int = Field(default=4, ge=1, le=52)
    # Google API connection (Drive now; Gmail/Calendar later). Separate from the login client.
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GOOGLE_DRIVE_REFRESH_TOKEN: str = ""
    BACKUP_DRIVE_FOLDER_ID: str = ""  # optional Drive folder for the backups

    # LLM providers (plan section 7.1): Groq and local Ollama, both OpenAI-compatible.
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = ""  # override the default Groq model (openai/gpt-oss-120b)
    # Groq's free tier gives each model its own daily token quota, so when one is used up
    # (or busy) the next is tried. Light tasks (chat, parsing) start with GROQ_LIGHT_MODEL.
    GROQ_FALLBACK_MODELS: str = "openai/gpt-oss-20b,qwen/qwen3.8-27b"
    GROQ_LIGHT_MODEL: str = "openai/gpt-oss-20b"
    # Ollama on the laptop; containers reach it at http://host.docker.internal:11434.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:8b"
    OLLAMA_EMBED_MODEL: str = "embeddinggemma"

    # Which provider every agent uses: groq | ollama | auto (Groq when its key is set, else Ollama).
    LLM_PROVIDER: str = "auto"


    # Chat assistant. "auto" follows LLM_PROVIDER; set to override it for the chat only.
    AGENT_PROVIDER: str = "auto"
    AGENT_MODEL: str = ""

    # Nightly board scans and morning digests on the server (services/autopilot.py).
    DISCOVERY_AUTO_SCAN: bool = True

    # HR Enrichment
    HUNTER_API_KEY: str = ""

    # Email: the morning digest is sent with Resend (free tier: from onboarding@resend.dev to your own address).
    RESEND_API_KEY: str = ""
    DIGEST_FROM: str = "JobPilot <onboarding@resend.dev>"

    # Shared secret for POST /api/v1/autopilot/tick, called by an external cron (e.g. cron-job.org)
    # so a host that sleeps when idle (Render free tier) still runs the nightly scan and digest.
    CRON_SECRET: str = ""
    COMPOSIO_API_KEY: str = ""
    COMPOSIO_GMAIL_AUTH_CONFIG_ID: str = ""
    MAILBOX_ENABLED: bool = False
    MAIL_SEND_ENABLED: bool = False
    MAIL_SYNC_ENABLED: bool = True

    # Job Data APIs
    ADZUNA_APP_ID: str = ""
    ADZUNA_API_KEY: str = ""

    # Infrastructure. Durable mode runs jobs through the Postgres queue and needs
    # `python -m app.workers.runner` (the Compose worker service).
    EXECUTION_MODE: Literal["inline", "durable"] = "inline"
    RUN_LEASE_SECONDS: int = Field(default=120, ge=30, le=1800)
    RUN_POLL_SECONDS: float = Field(default=2.0, ge=0.1, le=60)
    # Semantic job matching from local Ollama embeddings; lexical-only when Ollama is down.
    MATCHING_SEMANTIC: bool = True
    USAGE_LIMITS_ENABLED: bool = False
    APPLICATION_DAILY_LIMIT: int = Field(default=25, ge=1, le=1000)
    CHAT_DAILY_LIMIT: int = Field(default=100, ge=1, le=5000)
    APP_ENV: Literal['development', 'test', 'production'] = 'development'

    # App Config
    FRONTEND_URL: str = "http://localhost:5173"  # comma-separated for several origins; the first is used in emails
    SECRET_KEY: str = "change-me-in-production"
    DEBUG: bool = True
    OBSERVABILITY_TOKEN: str = ''  # Private operations scraper; backend only.
    REQUEST_LOGS_ENABLED: bool = False
    SENTRY_DSN: str = ''  # Optional, allowlisted error events only; no tracing/data.


settings = Settings()
