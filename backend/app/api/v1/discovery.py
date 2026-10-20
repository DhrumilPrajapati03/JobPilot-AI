"""Job discovery endpoints: followed job boards, the job feed and the morning briefing."""

from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services import discovery, referrals
from app.services.auth import CurrentUser, get_current_user
from app.services.job_boards import ATS_NAMES, REMOTE_BOARDS, BoardError, fetch_board, parse_board
from app.services.supabase import get_supabase_client

router = APIRouter()

Ats = Literal["greenhouse", "lever", "ashby", "smartrecruiters", "himalayas", "remotive"]


def _board(group: str, ats: str, slug: str, company: str, tag: str = "") -> dict:
    return {"group": group, "ats": ats, "slug": slug, "company": company, "tag": tag}


# Public boards checked to exist and to belong to the named company (October 2026),
# offered as one-click suggestions. Tags are the sector; "Recently funded" only where verified.
SUGGESTED_BOARDS = [
    _board("remote", "himalayas", "remote", "Himalayas", "Remote jobs, many companies"),
    _board("remote", "remotive", "remote", "Remotive", "Remote jobs, many companies"),
    _board("india", "ashby", "sarvam", "Sarvam AI", "AI · Recently funded"),
    _board("india", "smartrecruiters", "swiggy", "Swiggy", "Food & quick commerce"),
    _board("india", "lever", "paytm", "Paytm", "Fintech"),
    _board("india", "lever", "cred", "CRED", "Fintech"),
    _board("india", "greenhouse", "groww", "Groww", "Fintech"),
    _board("india", "lever", "zeta", "Zeta", "Fintech"),
    _board("india", "lever", "fampay", "FamPay", "Fintech"),
    _board("india", "lever", "epifi", "Fi Money", "Fintech"),
    _board("india", "lever", "meesho", "Meesho", "E-commerce"),
    _board("india", "smartrecruiters", "freshworks", "Freshworks", "SaaS"),
    _board("india", "ashby", "atlan", "Atlan", "Data & AI"),
    _board("india", "ashby", "composio", "Composio", "AI agents"),
    _board("india", "greenhouse", "observeai", "Observe.AI", "AI"),
    _board("india", "ashby", "bolna", "Bolna", "Voice AI"),
    _board("india", "ashby", "smallest", "Smallest.ai", "Voice AI"),
    _board("india", "greenhouse", "karya", "Karya", "AI data"),
    _board("india", "ashby", "spotdraft", "SpotDraft", "Legal tech"),
    _board("india", "greenhouse", "hackerrank", "HackerRank", "Developer tools"),
    _board("india", "greenhouse", "cloudsek", "CloudSEK", "Cybersecurity"),
    _board("india", "lever", "mindtickle", "Mindtickle", "SaaS"),
    _board("india", "greenhouse", "druva", "Druva", "SaaS"),
    _board("india", "greenhouse", "inmobi", "InMobi", "Adtech"),
    _board("india", "greenhouse", "glance", "Glance", "Consumer tech"),
    _board("india", "lever", "pocketfm", "Pocket FM", "Media"),
    _board("india", "smartrecruiters", "ixigo", "ixigo", "Travel"),
    _board("india", "smartrecruiters", "captainfresh", "Captain Fresh", "Food supply chain"),
    _board("india", "smartrecruiters", "vegrow", "Vegrow", "Agritech"),
    _board("india", "smartrecruiters", "unacademy", "Unacademy", "Edtech"),
    _board("global", "greenhouse", "stripe", "Stripe"),
    _board("global", "greenhouse", "airbnb", "Airbnb"),
    _board("global", "greenhouse", "figma", "Figma"),
    _board("global", "greenhouse", "anthropic", "Anthropic"),
    _board("global", "greenhouse", "databricks", "Databricks"),
    _board("global", "greenhouse", "discord", "Discord"),
    _board("global", "lever", "spotify", "Spotify"),
    _board("global", "lever", "palantir", "Palantir"),
    _board("global", "ashby", "openai", "OpenAI"),
    _board("global", "ashby", "notion", "Notion"),
    _board("global", "ashby", "linear", "Linear"),
    _board("global", "ashby", "supabase", "Supabase"),
    _board("global", "ashby", "cohere", "Cohere"),
    _board("global", "ashby", "ramp", "Ramp"),
]
_CATALOG = {(b["ats"], b["slug"]): b for b in SUGGESTED_BOARDS}
MAX_BULK = 40


class SourceCreate(BaseModel):
    url: str = Field(min_length=1, max_length=500, description="Careers page URL, or a board name when ats is given.")
    ats: Ats | None = None


class BoardRef(BaseModel):
    ats: Ats
    slug: str = Field(min_length=1, max_length=120)


class BulkSourceCreate(BaseModel):
    boards: list[BoardRef] = Field(min_length=1, max_length=MAX_BULK)


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    company: str | None = Field(default=None, max_length=120)


class PostingUpdate(BaseModel):
    status: Literal["new", "dismissed"]


@contextmanager
def _guard():
    """Turn missing tables and user-facing discovery errors into clear HTTP errors."""
    try:
        yield
    except HTTPException:
        raise
    except (discovery.DiscoveryError, BoardError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        if "job_sources_ats_check" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="This board type needs a database update. Run supabase/migrations/20261012_more_job_boards.sql in Supabase.",
            )
        if discovery.is_table_missing(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Job discovery tables don't exist yet. Run {discovery.MIGRATION_FILE} in Supabase.",
            )
        raise


def _client(user: CurrentUser):
    return get_supabase_client(user_jwt=user.token)


def _owned(supabase, table: str, row_id: str, user_id: str, columns: str = "*") -> dict:
    res = supabase.table(table).select(columns).eq("id", row_id).eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Not found")
    return res.data[0]


# --- Sources ------------------------------------------------------------------------

@router.get("/sources")
async def list_sources(current_user: CurrentUser = Depends(get_current_user)):
    with _guard():
        res = _client(current_user).table("job_sources").select("*").eq("user_id", current_user.id).order("created_at").execute()
    followed = {(s["ats"], s["slug"]) for s in res.data}
    return {
        "sources": res.data,
        "suggestions": [b for b in SUGGESTED_BOARDS if (b["ats"], b["slug"]) not in followed],
        "server_scans": discovery.server_scans_enabled(),
    }


@router.post("/sources", status_code=status.HTTP_201_CREATED)
async def add_source(request: SourceCreate, current_user: CurrentUser = Depends(get_current_user)):
    """Follow a company's job board, then scan it right away."""
    supabase = _client(current_user)
    with _guard():
        ats, slug = parse_board(request.url, request.ats)
        existing = supabase.table("job_sources").select("id").eq("user_id", current_user.id).eq("ats", ats).eq("slug", slug).execute()
        if existing.data:
            raise HTTPException(status_code=409, detail=f"You already follow {ATS_NAMES[ats] if ats in REMOTE_BOARDS else f'this {ATS_NAMES[ats]} board'}.")
        if ats in REMOTE_BOARDS:
            # Searched by your roles during the scan; nothing to validate up front.
            company, postings = ATS_NAMES[ats], []
        else:
            company, postings = await fetch_board(ats, slug)  # validates the board exists
            company = (_CATALOG.get((ats, slug)) or {}).get("company") or company
        source = supabase.table("job_sources").insert({
            "user_id": current_user.id, "ats": ats, "slug": slug, "company": company,
            "enabled": True, "job_count": len(postings),
        }).execute().data[0]
        scan = await discovery.scan_user(
            supabase, current_user.id, user_token=current_user.token, user_email=current_user.email,
            auto_draft=False, source_ids=[source["id"]],
        )
    return {"source": source, "scan": scan}


@router.post("/sources/bulk", status_code=status.HTTP_201_CREATED)
async def add_sources(request: BulkSourceCreate, current_user: CurrentUser = Depends(get_current_user)):
    """Follow several suggested boards at once. Scan afterwards to fetch their jobs."""
    supabase = _client(current_user)
    with _guard():
        followed = supabase.table("job_sources").select("ats, slug").eq("user_id", current_user.id).execute().data
        have = {(s["ats"], s["slug"]) for s in followed}
        rows, unknown = [], []
        for ref in request.boards:
            key = (ref.ats, ref.slug.lower())
            if key in have:
                continue
            board = _CATALOG.get(key)
            if not board:
                unknown.append(ref.slug)  # only suggested boards skip validation
                continue
            have.add(key)
            rows.append({"user_id": current_user.id, "ats": key[0], "slug": key[1], "company": board["company"], "enabled": True, "job_count": 0})
        created = supabase.table("job_sources").insert(rows).execute().data if rows else []
    return {"sources": created, "skipped_unknown": unknown}


@router.patch("/sources/{source_id}")
async def update_source(source_id: str, request: SourceUpdate, current_user: CurrentUser = Depends(get_current_user)):
    payload = request.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    supabase = _client(current_user)
    with _guard():
        _owned(supabase, "job_sources", source_id, current_user.id, "id")
        res = supabase.table("job_sources").update(payload).eq("id", source_id).eq("user_id", current_user.id).execute()
    return res.data[0]


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Unfollow a board. Its postings go too; applications already drafted stay."""
    supabase = _client(current_user)
    with _guard():
        _owned(supabase, "job_sources", source_id, current_user.id, "id")
        supabase.table("job_postings").delete().eq("source_id", source_id).eq("user_id", current_user.id).execute()
        supabase.table("job_sources").delete().eq("id", source_id).eq("user_id", current_user.id).execute()


# --- Scanning, feed and briefing ----------------------------------------------------

@router.post("/scan")
async def scan_now(current_user: CurrentUser = Depends(get_current_user)):
    """Scan every followed board now. Auto-drafts (if on) continue in the background."""
    with _guard():
        return await discovery.scan_user(
            _client(current_user), current_user.id, user_token=current_user.token, user_email=current_user.email,
        )


@router.get("/postings")
async def list_postings(
    status_filter: Literal["new", "skipped", "dismissed", "drafted"] = Query("new", alias="status"),
    min_score: float = 0,
    include_closed: bool = False,
    limit: int = 100,
    current_user: CurrentUser = Depends(get_current_user),
):
    """The job feed, best matches first. ``drafted`` includes drafts in progress."""
    limit = max(1, min(limit, 300))
    with _guard():
        rows = _client(current_user).table("job_postings").select(discovery.POSTING_FIELDS).eq("user_id", current_user.id).execute().data

    def bucket(r: dict) -> str:
        return "drafted" if r["status"] in ("drafting", "drafted") else r["status"]

    visible = [r for r in rows if (include_closed or not r.get("closed_at")) and not discovery.india_eligibility_flag(r)]
    counts = {k: 0 for k in ("new", "skipped", "dismissed", "drafted")}
    for r in visible:
        counts[bucket(r)] = counts.get(bucket(r), 0) + 1
    picked = [r for r in visible if bucket(r) == status_filter and float(r.get("fit_score") or 0) >= min_score]
    if status_filter == "drafted":
        picked.sort(key=lambda r: r.get("drafted_at") or "", reverse=True)
    else:
        picked.sort(key=lambda r: (float(r.get("fit_score") or 0), r.get("discovered_at") or ""), reverse=True)
    contacts = referrals.contact_counts(_client(current_user), current_user.id, [r["company"] for r in picked[:limit]])
    for r in picked:
        r.pop("description", None)  # the feed only needs it when a posting is opened
        r["referral_count"] = contacts.get(r["company"], 0)
    return {"postings": picked[:limit], "total": len(picked), "counts": counts}


@router.get("/postings/{posting_id}")
async def get_posting(posting_id: str, current_user: CurrentUser = Depends(get_current_user)):
    with _guard():
        return _owned(_client(current_user), "job_postings", posting_id, current_user.id)


@router.patch("/postings/{posting_id}")
async def update_posting(posting_id: str, request: PostingUpdate, current_user: CurrentUser = Depends(get_current_user)):
    """Dismiss a posting, or bring a dismissed / skipped one back to the feed."""
    supabase = _client(current_user)
    with _guard():
        posting = _owned(supabase, "job_postings", posting_id, current_user.id, "id, status")
        if posting["status"] in ("drafting", "drafted"):
            raise HTTPException(status_code=409, detail="This posting already has an application.")
        res = supabase.table("job_postings").update({"status": request.status}).eq("id", posting_id).eq("user_id", current_user.id).execute()
    return res.data[0]


@router.post("/postings/{posting_id}/draft")
async def draft_posting(posting_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Start the application pipeline for a posting. Progress streams over the agent WebSocket."""
    supabase = _client(current_user)
    with _guard():
        posting = _owned(supabase, "job_postings", posting_id, current_user.id, discovery.POSTING_FIELDS)
        if posting["status"] == "drafting":
            raise HTTPException(status_code=409, detail="A draft for this posting is already being created.")
        if posting["status"] == "drafted" and posting.get("application_id"):
            raise HTTPException(status_code=409, detail="This posting already has an application.")
        return discovery.start_manual_draft(
            supabase, current_user.id, posting, user_token=current_user.token, user_email=current_user.email,
        )


@router.get("/briefing")
async def get_briefing(current_user: CurrentUser = Depends(get_current_user)):
    """Morning briefing: new matches, drafts ready to review and follow-ups due."""
    supabase = _client(current_user)
    with _guard():
        prefs = discovery.load_preferences(supabase, current_user.id)
        return discovery.build_briefing(supabase, current_user.id, prefs)
