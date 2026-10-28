"""User profile model for the Identity Vault.

Stores the user's professional identity including personal info,
salary expectations, and work preferences.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


DEFAULT_SKIP_KEYWORDS = ["security clearance", "top secret", "polygraph"]


class WorkPreferences(BaseModel):
    """User's job search preferences and skip rules.

    Skip rules flag jobs the user would never take. Pasted jobs are only
    flagged (the user asked for them); automated job discovery skips them.
    """
    remote_only: bool = True
    preferred_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    min_company_size: int | None = None
    industries: list[str] = Field(default_factory=list)
    min_match_score: int = Field(default=70, ge=0, le=100)
    blocked_companies: list[str] = Field(default_factory=list)
    skip_keywords: list[str] = Field(default_factory=lambda: list(DEFAULT_SKIP_KEYWORDS))
    requires_sponsorship: bool = False
    career_level: Literal["any", "intern", "entry", "mid", "senior"] = "any"
    experience_years: float | None = Field(default=None, ge=0, le=60)
    authorized_countries: list[str] = Field(default_factory=list, max_length=20)
    salary_min: int | None = None
    salary_currency: str = "USD"
    # Job discovery: draft applications for the best new matches automatically.
    auto_draft_enabled: bool = False
    auto_draft_min_score: int = Field(default=80, ge=50, le=100)
    auto_draft_daily_cap: int = Field(default=3, ge=1, le=10)
    # Morning digest email. Boards are scanned two hours before it, in the user's time zone.
    digest_enabled: bool = False
    digest_hour: int = Field(default=7, ge=0, le=23)
    digest_email: str = ""  # empty = the account's email
    timezone: str = "UTC"


class UserProfile(BaseModel):
    """Core user profile for the Identity Vault.

    Attributes:
        id: Unique user identifier (from Supabase Auth).
        name: Full name.
        headline: Professional headline (e.g., 'AI/ML Engineer | RAG | LangChain').
        location: Current location.
        salary_range: Expected salary range string.
        work_preferences: Job search preferences.
        linkedin_url: LinkedIn profile URL.
        created_at: Profile creation timestamp.
        updated_at: Last update timestamp.
    """
    id: str | None = None
    name: str = ""
    headline: str = ""
    location: str = ""
    salary_range: str = ""
    work_preferences: WorkPreferences = Field(default_factory=WorkPreferences)
    linkedin_url: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
