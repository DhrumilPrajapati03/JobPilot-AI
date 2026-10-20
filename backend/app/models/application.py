"""Job application model.

Tracks the full lifecycle of a job application from
JD discovery through to offer/rejection.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ApplicationStatus(str, Enum):
    """Valid application pipeline statuses."""
    SAVED = "saved"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class JDAnalysis(BaseModel):
    """Structured output from the JD Parser Agent."""
    role: str = ""
    company: str = ""
    seniority: str = ""
    tone: str = ""
    required_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    salary_range: str | None = None
    remote: bool | None = None
    company_type: str = Field(
        default="",
        description="'mnc' (large multinational/enterprise), 'startup' (early/growth-stage), or 'sme' (small/local business).",
    )


class JobApplication(BaseModel):
    """Core job application entity.

    Represents a single job application tracked through
    the Kanban pipeline.

    Attributes:
        id: Unique application identifier.
        user_id: Owner user ID.
        company: Company name.
        role: Job title/role.
        jd_url: URL to the original job description.
        jd_text: Raw job description text.
        jd_analysis: Structured JD analysis from parser agent.
        status: Current pipeline status.
        source: Where the job was found (linkedin, adzuna, manual, etc.).
        applied_at: When the user applied.
        follow_up_at: Scheduled follow-up date.
        notes: User notes about this application.
        created_at: Record creation timestamp.
        updated_at: Last update timestamp.
    """
    id: str | None = None
    user_id: str | None = None
    company: str = ""
    role: str = ""
    jd_url: str = ""
    jd_text: str = ""
    jd_analysis: JDAnalysis | None = None
    status: ApplicationStatus = ApplicationStatus.SAVED
    source: str = "manual"
    applied_at: datetime | None = None
    follow_up_at: datetime | None = None
    notes: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
