"""Template model for reusable email/DM/cover letter templates.

Supports variable interpolation for personalisation
(e.g., {HR_NAME}, {COMPANY}, {ROLE}).
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TemplateType(str, Enum):
    """Supported template types."""
    EMAIL = "email"
    DM = "dm"
    COVER_LETTER = "cover_letter"


class Template(BaseModel):
    """Reusable outreach template.

    Attributes:
        id: Unique template identifier.
        user_id: Owner user ID.
        type: Template category (email, dm, cover_letter).
        name: Human-readable template name.
        subject: Email subject (for email templates).
        body: Template body with variable placeholders.
        variables: List of variable names used in the template.
        is_default: Whether this is a system default template.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """
    id: str | None = None
    user_id: str | None = None
    type: TemplateType = TemplateType.EMAIL
    name: str = ""
    subject: str = ""
    body: str = ""
    variables: list[str] = Field(default_factory=list)
    is_default: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
