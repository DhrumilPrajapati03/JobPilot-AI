"""Identity Vault / Profile endpoints.

Manages the user's professional identity data: resume content,
skills, projects, achievements, salary expectations, and
work preferences.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ProfileUpdateRequest(BaseModel):
    """Request body for profile update."""
    name: str | None = None
    headline: str | None = None
    location: str | None = None
    salary_range: str | None = None
    work_preferences: dict | None = None
    linkedin_url: str | None = None


@router.post("/update")
async def update_profile(request: ProfileUpdateRequest):
    """Update user identity vault data.

    Updates the user's professional profile including personal info,
    salary expectations, and work preferences.

    Args:
        request: Fields to update in the profile.
    """
    # TODO: Update profile in Supabase
    return {"message": "Profile updated", "data": request.model_dump(exclude_none=True)}


@router.get("/")
async def get_profile():
    """Retrieve the current user's full identity vault profile."""
    # TODO: Fetch profile from Supabase
    return {
        "name": "",
        "headline": "",
        "location": "",
        "salary_range": "",
        "work_preferences": {},
        "linkedin_url": "",
    }
