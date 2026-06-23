"""Supabase client initialisation.

Provides a configured Supabase client instance for
database operations, auth, and file storage.
"""

from app.config import settings
from supabase import create_client, Client

def get_supabase_client() -> Client:
    """Create and return a Supabase client instance.
     
    Uses SUPABASE_URL and SUPABASE_KEY (anon key) from settings.
    This client enforces Row Level Security (RLS) policies.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in your environment.")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def get_supabase_admin_client() -> Client:
    """Create a Supabase client with service role key.
    
    Used for admin operations that bypass RLS.
    WARNING: Do NOT use this client for normal user operations.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in your environment.")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
