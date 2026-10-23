"""HR Contact discovery endpoints.

Finds and enriches HR/recruiter contacts for target companies
using Hunter.io and Apollo.io APIs.
"""

from fastapi import APIRouter, Depends
from app.services.auth import CurrentUser, get_current_user

router = APIRouter()


@router.get("/find")
async def find_contacts(company_domain: str, _current_user: CurrentUser = Depends(get_current_user)):
    """Find HR/recruiter contacts for a given company domain.

    Uses Hunter.io and Apollo.io APIs to discover email addresses
    and LinkedIn profiles of HR personnel at the target company.

    Args:
        company_domain: The company's domain (e.g., 'google.com').
    """
    # TODO: Integrate Hunter.io + Apollo.io API
    return {
        "company_domain": company_domain,
        "contacts": [],
        "message": "HR contact finder - not yet implemented",
    }


@router.get("/")
async def list_contacts(company: str | None = None, _current_user: CurrentUser = Depends(get_current_user)):
    """List all discovered HR contacts, optionally filtered by company.

    Args:
        company: Optional company name filter.
    """
    # TODO: Query contacts from Supabase
    return {"contacts": [], "total": 0}
