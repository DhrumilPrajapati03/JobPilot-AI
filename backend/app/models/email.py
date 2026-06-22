"""Cold email model.

Tracks outreach emails sent to HR contacts/recruiters,
including open tracking and follow-up sequences.
"""

from datetime import datetime

from pydantic import BaseModel


class ColdEmail(BaseModel):
    """Cold email entity for outreach tracking.

    Attributes:
        id: Unique email identifier.
        application_id: Associated job application.
        to_email: Recipient email address.
        to_name: Recipient name.
        subject: Email subject line.
        body: Email body content.
        sequence_number: Position in follow-up sequence (1=initial, 2=first follow-up, etc.).
        sent_at: When the email was sent.
        opened: Whether the email was opened (tracking pixel).
        opened_at: When the email was first opened.
        replied: Whether a reply was received.
        replied_at: When the reply was received.
    """
    id: str | None = None
    application_id: str = ""
    to_email: str = ""
    to_name: str = ""
    subject: str = ""
    body: str = ""
    sequence_number: int = 1
    sent_at: datetime | None = None
    opened: bool = False
    opened_at: datetime | None = None
    replied: bool = False
    replied_at: datetime | None = None
