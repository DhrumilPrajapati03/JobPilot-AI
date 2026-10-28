"""Identity Vault / Profile endpoints.

Manages the user's professional identity data: resume content,
skills, projects, achievements, salary expectations, and
work preferences.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from app.services.auth import get_current_user, CurrentUser
from app.services.supabase import get_supabase_client
from app.models.user import UserProfile, WorkPreferences
from app.services import identity
from pydantic import BaseModel, Field

router = APIRouter()


class ConfirmFacts(BaseModel):
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    fact_ids: list[str] = Field(min_length=1, max_length=500)


@router.get("/facts")
async def get_facts(current_user: CurrentUser = Depends(get_current_user)):
    try:
        return identity.load_vault(get_supabase_client(user_jwt=current_user.token), current_user.id)
    except Exception as exc:
        raise HTTPException(503, "Identity facts are temporarily unavailable.") from exc


@router.post("/facts/confirm")
async def confirm_facts(request: ConfirmFacts, current_user: CurrentUser = Depends(get_current_user)):
    db = get_supabase_client(user_jwt=current_user.token)
    vault = identity.load_vault(db, current_user.id)
    if vault["source_digest"] != request.source_digest:
        raise HTTPException(409, "Your resume changed. Reload the facts before confirming.")
    if set(request.fact_ids) - {f["id"] for f in vault["facts"]}:
        raise HTTPException(422, "Only facts from your saved base resume can be confirmed.")
    rows = [{"user_id": current_user.id, "source_digest": request.source_digest, "fact_id": fid} for fid in set(request.fact_ids)]
    db.table("identity_confirmations").upsert(rows, on_conflict="user_id,source_digest,fact_id", ignore_duplicates=True).execute()
    return identity.load_vault(db, current_user.id)


@router.delete("/facts/{fact_id}")
async def revoke_fact(fact_id: str, current_user: CurrentUser = Depends(get_current_user)):
    db = get_supabase_client(user_jwt=current_user.token)
    db.table("identity_confirmations").delete().eq("user_id", current_user.id).eq("fact_id", fact_id).execute()
    return {"revoked": True}


@router.get("/", response_model=UserProfile)
async def get_profile(current_user: CurrentUser = Depends(get_current_user)):
    """Retrieve the current user's full identity vault profile."""
    try:
        # Pass user JWT so auth.uid() is set correctly in RLS policies
        supabase = get_supabase_client(user_jwt=current_user.token)

        response = supabase.table("user_profiles").select("*").eq("id", current_user.id).execute()

        # If no profile exists yet, insert a default blank profile row
        if not response.data:
            insert_response = supabase.table("user_profiles").insert({
                "id": current_user.id,
                "name": "",
                "headline": "",
                "location": "",
                "salary_range": "",
                "work_preferences": {}
            }).execute()

            if not insert_response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create initial user profile."
                )
            return insert_response.data[0]

        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {str(e)}"
        )


@router.post("/update", response_model=UserProfile)
async def update_profile(
    profile_data: dict,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Update user identity vault data.

    Updates the profile in the user_profiles table.
    The user can only update their own profile (enforced by RLS + forced id).
    """
    try:
        # Pass user JWT so auth.uid() is set correctly in RLS policies
        supabase = get_supabase_client(user_jwt=current_user.token)

        # Ensure the user updates ONLY their own profile by forcing user_id
        if "work_preferences" in profile_data:
            if not isinstance(profile_data["work_preferences"], dict):
                raise HTTPException(422, "Work preferences must be an object")
            try:
                current = supabase.table("user_profiles").select("work_preferences").eq("id", current_user.id).execute().data
                existing = (current[0].get("work_preferences") if current else None) or {}
                profile_data["work_preferences"] = WorkPreferences.model_validate({**existing, **profile_data["work_preferences"]}).model_dump(mode="json")
            except ValueError as exc:
                raise HTTPException(422, "Invalid work preferences") from exc
        profile_data["id"] = current_user.id

        # Upsert: updates existing or inserts if missing
        response = supabase.table("user_profiles").upsert(profile_data).execute()

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update profile."
            )
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )
