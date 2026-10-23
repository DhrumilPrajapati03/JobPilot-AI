"""Authentication services and dependencies.

Extracts, validates, and decodes Supabase JWT tokens.

Supports both:
- HS256 (legacy Supabase projects): verified using SUPABASE_JWT_SECRET
- ES256 / RS256 (newer Supabase projects): verified using the public key
  fetched from Supabase's JWKS endpoint at /auth/v1/.well-known/jwks.json
"""

import httpx
from dataclasses import dataclass
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config import settings

# This tells FastAPI to expect an "Authorization: Bearer <token>" header
security = HTTPBearer()

# -----------------------------------------------------------------------
# JWKS cache (in-memory, per-process)
# Avoids fetching Supabase's public keys on every single request.
# -----------------------------------------------------------------------
_jwks_cache: dict | None = None


async def _fetch_jwks() -> dict:
    """Fetch the JSON Web Key Set from Supabase's well-known endpoint."""
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    jwks_url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url, timeout=10.0)
        response.raise_for_status()
        _jwks_cache = response.json()

    return _jwks_cache


async def _get_jwk_for_kid(kid: str) -> dict:
    """Return the JWK dict whose 'kid' matches the JWT header kid.

    Invalidates cache and retries once on key-not-found (handles key rotation).
    """
    global _jwks_cache

    jwks = await _fetch_jwks()
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

    if key is None:
        # Key might have rotated — clear cache and try once more
        _jwks_cache = None
        jwks = await _fetch_jwks()
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

    if key is None:
        raise JWTError(f"No public key found in JWKS matching kid='{kid}'")

    return key


async def _verify_token(token: str) -> dict:
    """Verify a Supabase access token and return its payload.

    Algorithm-aware JWT verification:
    1. Peeks at the JWT header to read the 'alg' and 'kid' fields.
    2. For HS256: verifies using the raw SUPABASE_JWT_SECRET string.
    3. For ES256 / RS256: fetches the matching public key from Supabase
       JWKS and verifies the asymmetric signature.
    4. Verifies that the audience claim is 'authenticated'.
    5. Ensures the user's Supabase UUID ('sub' claim) is present.

    Raises:
        HTTPException 401: If the token is missing, invalid, or expired.
    """
    try:
        # --- Step 1: Peek at the header (no signature verification yet) ---
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "HS256")
        if alg not in {"HS256", "ES256", "RS256"}:
            raise JWTError("Unsupported signing algorithm")
        kid = header.get("kid")

        # --- Step 2: Pick the correct verification key ---
        if alg == "HS256":
            # Older Supabase projects: symmetric HMAC key (the JWT secret string)
            verify_key = settings.SUPABASE_JWT_SECRET
        else:
            # Newer Supabase projects: asymmetric key (ES256 or RS256)
            # Fetch the matching public key from Supabase's JWKS endpoint
            if not kid:
                raise JWTError("JWT header is missing 'kid' — cannot look up public key.")
            verify_key = await _get_jwk_for_kid(kid)

        # --- Step 3: Decode and fully verify the token ---
        payload = jwt.decode(
            token,
            verify_key,
            algorithms=[alg],
            options={"verify_aud": True},
            audience="authenticated",
        )

        # --- Step 4: Ensure the user ID is present ---
        if not payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload is missing 'sub' claim.",
            )
        return payload

    except HTTPException:
        # Re-raise our own HTTPExceptions without wrapping them
        raise
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired credentials: {str(e)}",
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not reach Supabase JWKS endpoint: {str(e)}",
        )


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """FastAPI dependency that returns the verified user's Supabase UUID."""
    payload = await _verify_token(credentials.credentials)
    return payload["sub"]


@dataclass
class CurrentUser:
    """Holds the verified user identity for use in endpoint handlers."""
    id: str
    token: str
    email: str = ""


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    """FastAPI dependency that returns both user_id and raw token.

    Use this (instead of get_current_user_id) in endpoints that make
    Supabase database calls, so the user's JWT can be passed to the
    Supabase client and RLS policies work correctly.
    """
    payload = await _verify_token(credentials.credentials)
    return CurrentUser(
        id=payload["sub"],
        token=credentials.credentials,
        email=payload.get("email") or "",
    )
