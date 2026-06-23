"""Identity Vault / Profile endpoints.

Manages the user's professional identity data: resume content,
skills, projects, achievements, salary expectations, and
work preferences.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from app.services.auth import get_current_user_id
from app.services.supabase import get_supabase_client
from app.models.user import UserProfile

router = APIRouter()


@router.get("/", response_model=UserProfile)
async def get_profile(user_id: str = Depends(get_current_user_id)):
    """Retrieve the current user's full identity vault profile."""
    try:
        supabase = get_supabase_client()
        # Query the database
        response = supabase.table("user_profiles").select("*").eq("id", user_id).execute()
        
        # If no profile exists yet, insert a default blank profile row
        if not response.data:
            insert_response = supabase.table("user_profiles").insert({
                "id": user_id,
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
    user_id: str = Depends(get_current_user_id)
):
    """Update user identity vault data.

    Updates the profile in the user_profiles table.
    """
    try:
        supabase = get_supabase_client()
        
        # Ensure the user updates ONLY their own profile by forcing user_id
        profile_data["id"] = user_id
        
        # Upsert: updates existing or inserts if missing
        response = supabase.table("user_profiles").upsert(profile_data).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update profile."
            )
        return response.data[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )

