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


PAGE_SIZE = 1000  # PostgREST's default max rows per response


def select_all(build_query, page_size: int = PAGE_SIZE) -> list[dict]:
    """Read every row of a query, page by page.

    ``build_query`` returns a fresh filtered query each call, e.g.
    ``lambda: client.table("t").select("*").eq("user_id", uid).order("id")``.
    Supabase caps responses at 1000 rows, so large tables need paging.
    """
    rows: list[dict] = []
    while True:
        batch = build_query().range(len(rows), len(rows) + page_size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
