"""Shared, atomic per-account budgets; retries reuse the same reservation."""
import uuid
from fastapi import HTTPException
from app.config import settings
from app.services.supabase import get_supabase_admin_client


def reserve(uid: str, bucket: str, limit: int, key: str | None = None):
    if not settings.USAGE_LIMITS_ENABLED:
        return
    try:
        allowed = get_supabase_admin_client().rpc('reserve_release_usage', {
            'p_user_id': uid, 'p_bucket': bucket, 'p_key': key or str(uuid.uuid4()),
            'p_limit': limit, 'p_seconds': 86400,
        }).execute().data
    except Exception:
        raise HTTPException(503, 'Usage limits are unavailable. Please try again later.') from None
    if allowed is not True:
        raise HTTPException(429, 'Your daily limit for this operation has been reached. Try again tomorrow.')
