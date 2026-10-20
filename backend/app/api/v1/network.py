"""Network endpoints: your contacts (LinkedIn export or manual) and referral requests."""

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.api.v1.applications import _get_owned_application
from app.services import referrals
from app.services.auth import CurrentUser, get_current_user
from app.services.supabase import get_supabase_client, select_all

router = APIRouter()

MIGRATION_FILE = "supabase/migrations/20261013_referrals.sql"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # the full LinkedIn archive (.zip) can be large
UPSERT_CHUNK = 500
ReferralStatus = Literal["drafted", "sent", "referred", "declined", "no_reply"]


class ContactCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    company: str = Field(default="", max_length=200)
    position: str = Field(default="", max_length=200)
    linkedin_url: str = Field(default="", max_length=500)
    email: str = Field(default="", max_length=320)
    notes: str = Field(default="", max_length=2000)


class ContactUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    position: str | None = Field(default=None, max_length=200)
    linkedin_url: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=320)
    notes: str | None = Field(default=None, max_length=2000)


class ReferralCreate(BaseModel):
    application_id: str
    contact_id: str
    message: str | None = Field(default=None, max_length=referrals.MESSAGE_LIMIT * 2)


class ReferralUpdate(BaseModel):
    status: ReferralStatus | None = None
    message: str | None = Field(default=None, max_length=referrals.MESSAGE_LIMIT * 2)


@contextmanager
def _guard():
    try:
        yield
    except HTTPException:
        raise
    except referrals.ImportError_ as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        if referrals.is_table_missing(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"The network tables don't exist yet. Run {MIGRATION_FILE} in Supabase.",
            )
        raise


def _client(user: CurrentUser):
    return get_supabase_client(user_jwt=user.token)


def _owned(supabase, table: str, row_id: str, user_id: str) -> dict:
    res = supabase.table(table).select("*").eq("id", row_id).eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Not found")
    return res.data[0]


def _all_contacts(supabase, user_id: str) -> list[dict]:
    return select_all(lambda: supabase.table("network_contacts").select("*").eq("user_id", user_id).order("id"))


# --- Contacts ------------------------------------------------------------------------

@router.post("/import")
async def import_connections(file: UploadFile = File(...), current_user: CurrentUser = Depends(get_current_user)):
    """Import LinkedIn's Connections.csv. Re-importing updates existing contacts."""
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That file is over 200 MB. Unzip the archive and upload Connections.csv on its own.")
    supabase = _client(current_user)
    with _guard():
        rows, skipped = referrals.parse_linkedin_connections(raw, current_user.id)
        if not rows:
            raise HTTPException(status_code=400, detail="No connections found in that file.")
        existing = {r["dedupe_key"] for r in select_all(
            lambda: supabase.table("network_contacts").select("dedupe_key").eq("user_id", current_user.id).order("id")
        )}
        for i in range(0, len(rows), UPSERT_CHUNK):
            supabase.table("network_contacts").upsert(rows[i:i + UPSERT_CHUNK], on_conflict="user_id,dedupe_key").execute()
    companies: dict[str, int] = {}
    for r in rows:
        if r["company"]:
            companies[r["company"]] = companies.get(r["company"], 0) + 1
    top = sorted(companies.items(), key=lambda kv: -kv[1])[:8]
    return {
        "imported": sum(1 for r in rows if r["dedupe_key"] not in existing),
        "updated": sum(1 for r in rows if r["dedupe_key"] in existing),
        "skipped": skipped,
        "with_company": sum(1 for r in rows if r["company"]),
        "top_companies": [{"company": c, "count": n} for c, n in top],
    }


@router.get("/contacts")
async def list_contacts(
    q: str = "", company: str = "", limit: int = 100, offset: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    limit = max(1, min(limit, 500))
    with _guard():
        rows = _all_contacts(_client(current_user), current_user.id)
    if company:
        rows = referrals.NetworkIndex(rows).find(company)
    needle = q.strip().lower()
    if needle:
        rows = [r for r in rows if any(needle in (r.get(k) or "").lower() for k in ("full_name", "company", "position", "email"))]
    rows.sort(key=lambda r: ((r.get("company") or "~").lower(), (r.get("full_name") or "").lower()))
    return {"contacts": rows[offset:offset + limit], "total": len(rows)}


@router.post("/contacts", status_code=status.HTTP_201_CREATED)
async def add_contact(request: ContactCreate, current_user: CurrentUser = Depends(get_current_user)):
    row = referrals.contact_row(current_user.id, **request.model_dump(), source="manual")
    supabase = _client(current_user)
    with _guard():
        res = supabase.table("network_contacts").upsert(row, on_conflict="user_id,dedupe_key").execute()
    return res.data[0]


@router.patch("/contacts/{contact_id}")
async def update_contact(contact_id: str, request: ContactUpdate, current_user: CurrentUser = Depends(get_current_user)):
    payload = request.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    supabase = _client(current_user)
    with _guard():
        current = _owned(supabase, "network_contacts", contact_id, current_user.id)
        if "company" in payload:
            payload["company_key"] = referrals.company_key(payload["company"])
        if "full_name" in payload:
            payload["first_name"] = payload["full_name"].split()[0] if payload["full_name"].strip() else ""
        res = supabase.table("network_contacts").update(payload).eq("id", contact_id).eq("user_id", current_user.id).execute()
    return res.data[0] if res.data else current


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: str, current_user: CurrentUser = Depends(get_current_user)):
    supabase = _client(current_user)
    with _guard():
        _owned(supabase, "network_contacts", contact_id, current_user.id)
        supabase.table("referral_requests").delete().eq("contact_id", contact_id).eq("user_id", current_user.id).execute()
        supabase.table("network_contacts").delete().eq("id", contact_id).eq("user_id", current_user.id).execute()


@router.get("/companies")
async def network_companies(current_user: CurrentUser = Depends(get_current_user)):
    """Companies you know people at, with whether you follow their board or have applied."""
    supabase = _client(current_user)
    with _guard():
        contacts = _all_contacts(supabase, current_user.id)
    apps = supabase.table("job_applications").select("id, company").eq("user_id", current_user.id).execute().data
    try:
        sources = supabase.table("job_sources").select("company").eq("user_id", current_user.id).execute().data
    except Exception:
        sources = []
    groups: dict[str, dict] = {}
    for c in contacts:
        key = c.get("company_key")
        if not key:
            continue
        g = groups.setdefault(key, {"company": c.get("company") or key, "count": 0})
        g["count"] += 1
    result = []
    for key, g in groups.items():
        result.append({
            **g,
            "applications": sum(1 for a in apps if referrals.companies_match(key, referrals.company_key(a["company"]))),
            "followed": any(referrals.companies_match(key, referrals.company_key(s.get("company") or "")) for s in sources),
        })
    result.sort(key=lambda g: (-(g["applications"] > 0 or g["followed"]), -g["count"], g["company"].lower()))
    return {"companies": result[:200], "total_contacts": len(contacts), "total_companies": len(groups)}


# --- Referrals -------------------------------------------------------------------------

def _request_view(req: dict, contact: dict | None) -> dict:
    return {**req, "contact": contact}


@router.get("/referrals/{application_id}")
async def referrals_for_application(application_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """People you know at this application's company, best to ask first, with any requests made."""
    supabase = _client(current_user)
    application = _get_owned_application(supabase, application_id, current_user.id)
    with _guard():
        index = referrals.load_index(supabase, current_user.id)
        requests = supabase.table("referral_requests").select("*").eq("application_id", application_id).eq("user_id", current_user.id).execute().data
    by_contact = {r["contact_id"]: r for r in requests}
    ranked = referrals.rank_contacts(index.find(application["company"]), application["role"])
    return {
        "company": application["company"],
        "contacts": [
            {"contact": r.contact, "reason": r.reason, "score": r.score, "request": by_contact.get(r.contact["id"])}
            for r in ranked[:25]
        ],
        "total": len(ranked),
    }


@router.post("/referrals", status_code=status.HTTP_201_CREATED)
async def create_referral(request: ReferralCreate, current_user: CurrentUser = Depends(get_current_user)):
    """Draft (or save) a referral request message. Nothing is sent; you send it yourself."""
    supabase = _client(current_user)
    application = _get_owned_application(supabase, request.application_id, current_user.id)
    with _guard():
        contact = _owned(supabase, "network_contacts", request.contact_id, current_user.id)
        used_fallback = False
        message = (request.message or "").strip()
        if not message:
            message, used_fallback = await _draft(supabase, current_user.id, contact, application)
        res = supabase.table("referral_requests").upsert({
            "user_id": current_user.id,
            "application_id": application["id"],
            "contact_id": contact["id"],
            "message": message,
            "status": "drafted",
        }, on_conflict="application_id,contact_id").execute()
    return {**_request_view(res.data[0], contact), "used_fallback": used_fallback}


async def _draft(supabase, user_id: str, contact: dict, application: dict) -> tuple[str, bool]:
    profile = (supabase.table("user_profiles").select("*").eq("id", user_id).execute().data or [{}])[0]
    resume = (supabase.table("resumes").select("*").eq("user_id", user_id).eq("version", "base").execute().data or [{}])[0]
    return await referrals.draft_referral_message(contact, application, profile, resume)


@router.patch("/referrals/{request_id}")
async def update_referral(request_id: str, request: ReferralUpdate, current_user: CurrentUser = Depends(get_current_user)):
    payload = request.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    if payload.get("status") == "sent":
        payload["sent_at"] = datetime.now(timezone.utc).isoformat()
    elif payload.get("status") == "drafted":
        payload["sent_at"] = None
    supabase = _client(current_user)
    with _guard():
        _owned(supabase, "referral_requests", request_id, current_user.id)
        res = supabase.table("referral_requests").update(payload).eq("id", request_id).eq("user_id", current_user.id).execute()
    return res.data[0]


@router.delete("/referrals/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_referral(request_id: str, current_user: CurrentUser = Depends(get_current_user)):
    supabase = _client(current_user)
    with _guard():
        _owned(supabase, "referral_requests", request_id, current_user.id)
        supabase.table("referral_requests").delete().eq("id", request_id).eq("user_id", current_user.id).execute()

