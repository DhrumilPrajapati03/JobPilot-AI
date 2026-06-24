"""Authentication endpoints.

Manages user logins via OTP/Magic Link and session checks.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from app.services.supabase import get_supabase_client
from app.services.auth import get_current_user, CurrentUser

router = APIRouter()

# Schema for login request
class LoginRequest(BaseModel):
    email: EmailStr

@router.post("/login")
async def login(request: LoginRequest):
    """Trigger Supabase Auth to send a passwordless OTP / Magic Link email."""
    try:
        supabase = get_supabase_client()
        # supabase-py v2 sign_in_with_otp takes a credentials dict
        supabase.auth.sign_in_with_otp({
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
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    """Retrieve metadata about the currently authenticated user.

    Uses get_current_user dependency to verify the JWT first, then passes
    the user's token to the Supabase client so RLS policies work correctly.
    """
    try:
        # Pass the user's JWT so auth.uid() works in RLS policies
        supabase = get_supabase_client(user_jwt=current_user.token)

        # Fetch the user profile details using the user_id from the JWT
        response = supabase.table("user_profiles").select("*").eq("id", current_user.id).execute()

        # If no profile exists yet, create an empty one
        if not response.data:
            profile_response = supabase.table("user_profiles").insert({
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
    """Sign the user out.

    Since JWTs are stateless on our side, we simply confirm the logout.
    The frontend is responsible for calling supabase.auth.signOut() to
    clear the session from local storage.
    """
    return {"message": "Logged out successfully"}