"""Session endpoints: who is signed in, and sign-out.

Magic-link/OTP login (Supabase Auth) is gone; owner login replaces it (plan section 4.1).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from app.db import get_db
from app.services.auth import get_current_user, CurrentUser

router = APIRouter()


@router.get("/me")
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    """Return the signed-in owner's id and profile, creating an empty profile on first use."""
    try:
        db = get_db(current_user.id)
        response = db.table("user_profiles").select("*").eq("id", current_user.id).execute()

        if not response.data:
            profile_response = db.table("user_profiles").insert({
                "id": current_user.id,
                "name": "",
                "headline": "",
                "location": "",
                "salary_range": ""
            }).execute()
            profile = profile_response.data[0] if profile_response.data else {}
        else:
            profile = response.data[0]

        return {
            "user_id": current_user.id,
            "profile": profile
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch profile: {str(e)}"
        )


@router.post("/logout")
async def logout(current_user: CurrentUser = Depends(get_current_user)):
    """Sign the user out. Tokens are stateless here; the client discards its session."""
    return {"message": "Logged out successfully"}
