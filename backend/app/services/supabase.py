"""Supabase client initialisation.

Provides a configured Supabase client instance for
database operations, auth, and file storage.
"""

from app.config import settings
from supabase import create_client, Client


def get_supabase_client(user_jwt: str | None = None) -> Client:
    """Create and return a Supabase client instance.

    Args:
        user_jwt: Optional. The user's Supabase access token (JWT).
            When provided, the client's PostgREST connection is authenticated
            as that user, so Row Level Security policies see the correct
            auth.uid() and can allow INSERT/SELECT/UPDATE/DELETE accordingly.
            Without this, auth.uid() is null and RLS will block most writes.

    Uses SUPABASE_URL and SUPABASE_KEY (anon key) from settings.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in your environment.")

    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

    if user_jwt:
        # Tell PostgREST to send the user's token in the Authorization header
        # so that auth.uid() returns the correct user UUID inside RLS policies.
        client.postgrest.auth(user_jwt)

    return client


def get_supabase_admin_client() -> Client:
    """Create a Supabase client with service role key.

    Used for admin operations that bypass RLS entirely.
    WARNING: Do NOT use this client for normal user operations.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in your environment.")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
