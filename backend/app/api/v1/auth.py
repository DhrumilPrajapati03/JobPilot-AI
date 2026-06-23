"""Authentication endpoints.

Manages user logins via OTP/Magic Link and session checks.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from app.services.supabase import get_supabase_client
from app.services.auth import get_current_user_id

router = APIRouter()

# Schema for login request
class LoginRequest(BaseModel):
    email: EmailStr

@router.post("/login")
async def login(request: LoginRequest):
    """Trigger Supabase Auth to send a passwordless OTP / Magic Link email."""
    try:
        supabase = get_supabase_client()
        # Trigger the Magic Link flow in Supabase
        response = supabase.auth.sign_in_with_otp({
            "email": request.email,
            "options": {
                # This specifies where the user lands after clicking the magic link.
                # It will redirect them back to our React application.
                "email_redirect_to": "http://localhost:5173"
            }
        })
        return {"message": "Magic link sent successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send magic link: {str(e)}"
        )

@router.get("/me")
async def get_me(user_id: str = Depends(get_current_user_id)):
    """Retrieve metadata about the currently authenticated user.

    Uses get_current_user_id dependency to verify the JWT first.
    """
    try:
        supabase = get_supabase_client()
        # Fetch the user profile details using the user_id from the JWT
        response = supabase.table("user_profiles").select("*").eq("id", user_id).execute()
        
        # If no profile exists yet, create an empty one (so the frontend gets a valid structure)
        if not response.data:
            profile_response = supabase.table("user_profiles").insert({
                "id": user_id,
                "name": "",
                "headline": "",
                "location": "",
                "salary_range": ""
            }).execute()
            profile = profile_response.data[0] if profile_response.data else {}
        else:
            profile = response.data[0]

        return {
            "user_id": user_id,
            "profile": profile
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch profile: {str(e)}"
        )

@router.post("/logout")
async def logout(user_id: str = Depends(get_current_user_id)):
    """Sign the user out.

    Since JWTs are stateless on our side, we tell Supabase to invalidate the token,
    and the frontend will delete it from its own storage.
    """
    try:
        supabase = get_supabase_client()
        supabase.auth.sign_out()
        return {"message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sign out failed: {str(e)}"
        )