"""Authentication endpoints.

Handles Supabase magic link authentication, JWT validation,
and session management.
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/login")
async def login(email: str):
    """Initiate magic link login via Supabase Auth.

    Sends a magic link to the provided email address.
    User clicks the link to authenticate.

    Args:
        email: User's email address for magic link delivery.
    """
    # TODO: Integrate with Supabase Auth magic link
    return {"message": "Magic link sent", "email": email}


@router.post("/logout")
async def logout():
    """Invalidate the current session and clear JWT cookie."""
    # TODO: Clear httpOnly JWT cookie and invalidate Supabase session
    return {"message": "Logged out successfully"}


@router.get("/me")
async def get_current_user():
    """Get the currently authenticated user's info.

    Returns user profile data from the validated JWT token.
    """
    # TODO: Extract user from JWT middleware
    return {
        "id": "placeholder-user-id",
        "email": "user@example.com",
        "authenticated": True,
    }
