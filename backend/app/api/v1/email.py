"""Email management endpoints.

Handles cold email sending, template management,
and email tracking.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class EmailSendRequest(BaseModel):
    """Request body for sending a cold email."""
    to_email: str
    to_name: str
    subject: str
    body: str
    application_id: str | None = None


@router.post("/send")
async def send_email(request: EmailSendRequest):
    """Send an approved cold email via Resend or Gmail API.

    The email must be reviewed and approved by the user before
    this endpoint is called.

    Args:
        request: Email details including recipient, subject, and body.
    """
    # TODO: Send email via Resend API / Gmail OAuth
    return {
        "message": "Email send endpoint - not yet implemented",
        "to": request.to_email,
    }


@router.get("/history")
async def get_email_history(application_id: str | None = None):
    """Retrieve email sending history, optionally filtered by application.

    Args:
        application_id: Optional filter by specific application.
    """
    # TODO: Query email logs from Supabase
    return {"emails": [], "total": 0}
