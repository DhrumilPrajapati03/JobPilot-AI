"""Application configuration via pydantic-settings.

Loads environment variables from .env file and provides
typed settings accessible throughout the application.
"""

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

    # HR Enrichment
    HUNTER_API_KEY: str = ""

    # Email
    RESEND_API_KEY: str = ""

    # Job Data APIs
    ADZUNA_APP_ID: str = ""
    ADZUNA_API_KEY: str = ""

    # Infrastructure
    REDIS_URL: str = "redis://localhost:6379/0"

    # App Config
    FRONTEND_URL: str = "http://localhost:5173"
    SECRET_KEY: str = "change-me-in-production"
    DEBUG: bool = True


settings = Settings()
