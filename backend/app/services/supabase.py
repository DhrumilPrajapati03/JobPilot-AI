"""Supabase client initialisation.

Provides a configured Supabase client instance for
database operations, auth, and file storage.
"""

from app.config import settings


def get_supabase_client():
    """Create and return a Supabase client instance.

    Uses SUPABASE_URL and SUPABASE_KEY from settings.

    Returns:
        Supabase client configured for the project.

    TODO: Initialise with supabase-py library
    """
    # from supabase import create_client
    # return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    raise NotImplementedError(
        "Supabase client not yet configured. "
        "Set SUPABASE_URL and SUPABASE_KEY in .env"
    )


def get_supabase_admin_client():
    """Create a Supabase client with service role key.

    Used for admin operations that bypass RLS.

    Returns:
        Supabase admin client.
    """
    # from supabase import create_client
    # return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    raise NotImplementedError(
        "Supabase admin client not yet configured. "
        "Set SUPABASE_SERVICE_KEY in .env"
    )
