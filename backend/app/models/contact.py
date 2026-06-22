"""HR Contact model.

Stores discovered HR/recruiter contacts enriched via
Hunter.io and Apollo.io APIs.
"""

from datetime import datetime

from pydantic import BaseModel


class HRContact(BaseModel):
    """HR/Recruiter contact entity.

    Attributes:
        id: Unique contact identifier.
        company: Company name.
        name: Contact's full name.
        email: Contact's email address.
        linkedin_url: LinkedIn profile URL.
        title: Job title (e.g., 'Technical Recruiter', 'HR Manager').
        confidence_score: Email verification confidence (0.0-1.0).
        source: Discovery source (hunter, apollo, manual).
        created_at: When the contact was discovered.
    """
    id: str | None = None
    company: str = ""
    name: str = ""
    email: str = ""
    linkedin_url: str = ""
    title: str = ""
    confidence_score: float = 0.0
    source: str = ""
    created_at: datetime | None = None
