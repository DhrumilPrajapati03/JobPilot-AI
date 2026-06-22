"""User profile model for the Identity Vault.

Stores the user's professional identity including personal info,
salary expectations, and work preferences.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class WorkPreferences(BaseModel):
    """User's job search preferences."""
    remote_only: bool = True
    preferred_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    min_company_size: int | None = None
    industries: list[str] = Field(default_factory=list)


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
