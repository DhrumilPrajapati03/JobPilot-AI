"""Identity Vault / Profile endpoints.

Manages the user's professional identity data: resume content,
skills, projects, achievements, salary expectations, and
work preferences.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from app.services.auth import get_current_user, CurrentUser
from app.services.supabase import get_supabase_client
from app.models.user import UserProfile

router = APIRouter()


@router.get("/", response_model=UserProfile)
async def get_profile(current_user: CurrentUser = Depends(get_current_user)):
    """Retrieve the current user's full identity vault profile."""
    try:
        # Pass user JWT so auth.uid() is set correctly in RLS policies
        supabase = get_supabase_client(user_jwt=current_user.token)

        response = supabase.table("user_profiles").select("*").eq("id", current_user.id).execute()

        # If no profile exists yet, insert a default blank profile row
        if not response.data:
            insert_response = supabase.table("user_profiles").insert({
                "id": current_user.id,
                "name": "",
                "headline": "",
                "location": "",
                "salary_range": "",
                "work_preferences": {}
            }).execute()

            if not insert_response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create initial user profile."
                )
            return insert_response.data[0]

        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {str(e)}"
        )


@router.post("/update", response_model=UserProfile)
async def update_profile(
    profile_data: dict,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Update user identity vault data.

    Updates the profile in the user_profiles table.
    The user can only update their own profile (enforced by RLS + forced id).
    """
    try:
        # Pass user JWT so auth.uid() is set correctly in RLS policies
        supabase = get_supabase_client(user_jwt=current_user.token)

        # Ensure the user updates ONLY their own profile by forcing user_id
        profile_data["id"] = current_user.id

        # Upsert: updates existing or inserts if missing
        response = supabase.table("user_profiles").upsert(profile_data).execute()

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update profile."
            )
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )
