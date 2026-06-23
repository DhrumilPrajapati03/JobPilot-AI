"""Authentication services and dependencies.

Extracts, validates, and decodes Supabase JWT tokens.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config import settings

# This tells FastAPI to expect an "Authorization: Bearer <token>" header
security = HTTPBearer()

async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """FastAPI dependency to authenticate requests.

    1. Extracts the Bearer token from the Authorization header.
    2. Decodes and verifies the signature using the Supabase JWT secret.
    3. Verifies that the audience is "authenticated".
    4. Extracts and returns the user's Supabase UUID.

    Raises:
        HTTPException: 401 Unauthorized if the token is invalid or expired.
    """
    token = credentials.credentials
    try:
        # Supabase JWTs are signed using the HS256 algorithm.
        # We enforce options to verify audience ('aud') matches 'authenticated'.
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": True},
            audience="authenticated"
        )
        
        # 'sub' is the unique identifier (UUID) for the user in Supabase
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload is missing 'sub' claim.",
            )
        return user_id
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired credentials: {str(e)}",
        )
