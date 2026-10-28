"""Application management endpoints.

Handles the core job application workflow: parsing JDs,
running the agent pipeline, listing applications, editing
generated materials, and updating application status.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.agents.jd_parser import JDParserAgent
from app.agents.orchestrator import run_agent_pipeline
from app.models.application import ApplicationStatus
from app.services.auth import CurrentUser, get_current_user
from app.services.materials import (
    is_missing_column_error,
    normalize_application,
    update_application,
)
from app.services.referrals import contact_counts
from app.services.supabase import get_supabase_client
from app.services.websocket import manager
from app.services import runs

router = APIRouter()


class ReportSubmissionRequest(BaseModel):
    request_key: uuid.UUID


@router.post("/{application_id}/report-submission")
async def report_submission(application_id: uuid.UUID, request: ReportSubmissionRequest, current_user: CurrentUser = Depends(get_current_user)):
    from app.services import application_execution as execution
    from app.services.supabase import get_supabase_admin_client
    sid = uuid.uuid5(uuid.NAMESPACE_URL, f"jobpilot:web-report:{current_user.id}:{application_id}:{request.request_key}")
    execution.report(get_supabase_admin_client(), current_user.id, str(application_id), sid, request.request_key)
    return {"application_id": str(application_id), "evidence": "user_reported_not_independently_verified"}


@router.get("/{application_id}/execution")
async def execution_history(application_id: uuid.UUID, current_user: CurrentUser = Depends(get_current_user)):
    from app.services.application_execution import DOCUMENT_FIELDS, owned
    db = get_supabase_client(user_jwt=current_user.token)
    owned(db, current_user.id, application_id)
    try:
        sessions = db.table("application_execution_sessions").select("*").eq("application_id", str(application_id)).eq("user_id", current_user.id).order("created_at", desc=True).limit(20).execute().data
        ids = [s["id"] for s in sessions]
        events = db.table("application_events").select("*").eq("user_id", current_user.id).in_("session_id", ids).order("id", desc=True).limit(200).execute().data if ids else []
        documents = db.table("application_documents").select(DOCUMENT_FIELDS).eq("application_id", str(application_id)).eq("user_id", current_user.id).order("created_at", desc=True).limit(20).execute().data
    except Exception:
        raise HTTPException(503, "Submission evidence is unavailable. Apply the Sprint 5 migration.") from None
    return {"sessions": sessions, "events": events, "documents": documents}

# Days after applying before the tracker flags an application for follow-up.
FOLLOW_UP_AFTER_DAYS = 5


class JDParseRequest(BaseModel):
    """Request body for JD parsing."""
    jd_url: str | None = None
    jd_text: str | None = None


class ApplicationGenerateRequest(BaseModel):
    """Request body to trigger full agent pipeline."""
    jd_url: str | None = None
    jd_text: str | None = None
    auto_research: bool = True


class StatusUpdateRequest(BaseModel):
    """Request body for status update."""
    status: ApplicationStatus


class LinkedInDM(BaseModel):
    connection_request: str = Field(default="", max_length=300)
    follow_up: str = ""


class ApplicationUpdateRequest(BaseModel):
    """Editable fields of an application (all optional)."""
    company: str | None = None
    role: str | None = None
    jd_url: str | None = None
    notes: str | None = None
    cover_letter: str | None = None
    linkedin_dm: LinkedInDM | None = None
    follow_up_at: datetime | None = None


class ColdEmailUpdateRequest(BaseModel):
    """Editable fields of a cold email draft (all optional)."""
    to_email: str | None = None
    to_name: str | None = None
    subject: str | None = None
    body: str | None = None
    sent: bool | None = None
    replied: bool | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_owned_application(supabase, application_id: str, user_id: str) -> dict:
    try:
        uuid.UUID(str(application_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Job application not found")
    res = (
        supabase.table("job_applications")
        .select("*")
        .eq("id", application_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Job application not found")
    return res.data[0]


@router.post("/parse-jd")
async def parse_jd(
    request: JDParseRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Parse a job description URL or raw text.

    Extracts structured analysis: role, company, required skills,
    keywords, tone, seniority level, and tech stack.

    Args:
        request: JD URL or raw text to parse.
    """
    agent = JDParserAgent()
    analysis = await agent.parse(jd_url=request.jd_url, jd_text=request.jd_text)
    return {
        "status": "parsed",
        "analysis": analysis,
    }


@router.post("/generate")
async def generate_application(
    request: ApplicationGenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None),
):
    """Run the full agent pipeline for a single application.

    Orchestrates: JD parsing → resume tailoring → PDF check →
    cover letter / cold email / LinkedIn DM → tracker update.

    Returns a run_id for WebSocket progress streaming.

    Args:
        request: JD input and pipeline configuration.
        background_tasks: FastAPI background tasks queue.
        current_user: Authenticated user.
    """
    jd_url = (request.jd_url or "").strip() or None
    jd_text = (request.jd_text or "").strip() or None
    if not jd_url and not jd_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide a job URL or the job description text.",
        )

    if runs.durable_enabled():
        run = runs.enqueue_for_user(current_user.id, "application", {"jd_url": jd_url, "jd_text": jd_text, "source": "manual"}, idempotency_key)
        return {"status": run["status"], "run_id": run["id"], "message": "Application queued. A background worker will prepare it."}
    run_id = str(uuid.uuid4())
    manager.register(run_id, current_user.id)
    background_tasks.add_task(
        run_agent_pipeline,
        run_id,
        current_user.id,
        current_user.token,
        jd_url,
        jd_text,
        current_user.email,
    )
    return {
        "status": "queued",
        "run_id": run_id,
        "message": "Agent pipeline started. Connect to WebSocket for progress.",
    }


@router.get("/")
async def list_applications(
    status: str | None = None,
    source: str | None = None,
    skip: int = 0,
    limit: int = 200,
    current_user: CurrentUser = Depends(get_current_user)
):
    """List all job applications with optional filters.

    Each application includes its latest ``keyword_match_score``.

    Args:
        status: Filter by application status (e.g., 'applied', 'interviewing').
        source: Filter by job source (e.g., 'linkedin', 'adzuna').
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return (max 500).
        current_user: Authenticated user.
    """
    limit = max(1, min(limit, 500))
    supabase = get_supabase_client(user_jwt=current_user.token)
    query = supabase.table("job_applications").select("*", count="exact").eq("user_id", current_user.id)

    if status:
        query = query.eq("status", status)
    if source:
        query = query.eq("source", source)

    res = query.order("created_at", desc=True).range(skip, skip + limit - 1).execute()
    total = res.count if res.count is not None else len(res.data)

    scores: dict[str, float] = {}
    ids = [row["id"] for row in res.data]
    if ids:
        score_res = (
            supabase.table("tailored_resumes")
            .select("application_id, keyword_match_score, version")
            .in_("application_id", ids)
            .order("version", desc=False)
            .execute()
        )
        # Ascending by version, so the latest version wins.
        scores = {row["application_id"]: row["keyword_match_score"] for row in score_res.data}

    contacts = contact_counts(supabase, current_user.id, [row["company"] for row in res.data])
    applications = []
    for row in res.data:
        app = normalize_application(row)
        app.pop("jd_text", None)
        app["keyword_match_score"] = scores.get(row["id"])
        app["referral_count"] = contacts.get(row["company"], 0)
        prepared = app.pop("prepared_form", None) or {}
        app["prepared_summary"] = prepared.get("summary")
        app["apply_url"] = prepared.get("apply_url") or row.get("jd_url") or ""
        applications.append(app)

    return {
        "applications": applications,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{application_id}")
async def get_application_details(
    application_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Retrieve details for a single job application.

    Pulls information from job_applications, tailored_resumes,
    and cold_emails tables.
    """
    try:
        uuid.UUID(application_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Application not found")
    supabase = get_supabase_client(user_jwt=current_user.token)
    application = _get_owned_application(supabase, application_id, current_user.id)

    resume_res = (
        supabase.table("tailored_resumes")
        .select("*")
        .eq("application_id", application_id)
        .eq("user_id", current_user.id)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    tailored_resume = resume_res.data[0] if resume_res.data else None

    email_res = (
        supabase.table("cold_emails")
        .select("*")
        .eq("application_id", application_id)
        .order("sequence_number")
        .execute()
    )
    try:
        gmail = supabase.table("outreach_messages").select("id,state,to_email,from_email,provider_message_id,sent_at,delivery_status").eq("application_id", application_id).eq("user_id", current_user.id).order("created_at", desc=True).limit(25).execute().data
    except Exception as exc:
        if "outreach_messages" not in str(exc) or not any(code in str(exc) for code in ("PGRST205", "does not exist")):
            raise HTTPException(503, "Email acceptance history is temporarily unavailable") from exc
        gmail = []

    return {
        "application": normalize_application(application),
        "tailored_resume": tailored_resume,
        "cold_emails": email_res.data,
        "gmail_outreach": gmail,
    }


@router.patch("/{application_id}")
async def update_application_details(
    application_id: str,
    request: ApplicationUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Edit an application's details or its generated cover letter / DMs."""
    payload = request.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")

    supabase = get_supabase_client(user_jwt=current_user.token)
    current = _get_owned_application(supabase, application_id, current_user.id)
    try:
        return update_application(supabase, application_id, current_user.id, payload, current)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{application_id}/status")
async def update_application_status(
    application_id: str,
    request: StatusUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Update the status of a specific application.

    Valid statuses: saved, applied, interviewing, offer, rejected, archived.
    Moving to ``applied`` stamps ``applied_at`` and schedules a follow-up
    reminder; closed statuses clear any pending follow-up.

    Args:
        application_id: Unique application identifier.
        request: New status value.
        current_user: Authenticated user.
    """
    supabase = get_supabase_client(user_jwt=current_user.token)
    current = _get_owned_application(supabase, application_id, current_user.id)

    new_status = request.status.value
    payload: dict = {"status": new_status}
    if new_status == ApplicationStatus.APPLIED.value:
        if not current.get("applied_at"):
            payload["applied_at"] = _now().isoformat()
        if not current.get("follow_up_at"):
            payload["follow_up_at"] = (_now() + timedelta(days=FOLLOW_UP_AFTER_DAYS)).isoformat()
    elif new_status in {"interviewing", "offer", "rejected", "archived"}:
        payload["follow_up_at"] = None

    def _write(data: dict):
        return (
            supabase.table("job_applications")
            .update(data)
            .eq("id", application_id)
            .eq("user_id", current_user.id)
            .execute()
        )

    try:
        res = _write(payload)
    except Exception as e:
        if not is_missing_column_error(e):
            raise
        res = _write({"status": new_status})
    if not res.data:
        raise HTTPException(status_code=404, detail="Job application not found or unauthorized")

    return {
        "application_id": application_id,
        "status": new_status,
        "updated": True,
        "application": normalize_application(res.data[0]),
    }


@router.put("/{application_id}/emails/{email_id}")
async def update_cold_email(
    application_id: str,
    email_id: str,
    request: ColdEmailUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Edit a cold email draft or mark it as sent / replied."""
    supabase = get_supabase_client(user_jwt=current_user.token)
    _get_owned_application(supabase, application_id, current_user.id)

    payload = request.model_dump(exclude_unset=True, exclude={"sent"})
    if request.sent is not None:
        payload["sent_at"] = _now().isoformat() if request.sent else None
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")

    res = (
        supabase.table("cold_emails")
        .update(payload)
        .eq("id", email_id)
        .eq("application_id", application_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Email draft not found")
    return res.data[0]


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    application_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete an application together with its tailored resumes and emails."""
    supabase = get_supabase_client(user_jwt=current_user.token)
    _get_owned_application(supabase, application_id, current_user.id)

    try:
        history = supabase.table("outreach_messages").select("id").eq("application_id", application_id).eq("user_id", current_user.id).limit(1).execute().data
    except Exception as exc:
        if "outreach_messages" not in str(exc) or not any(code in str(exc) for code in ("PGRST205", "does not exist")):
            raise HTTPException(503, "Email history could not be checked before deletion") from exc
        history = []
    if history:
        raise HTTPException(409, "This application has email history. Archive it to preserve send and approval records.")
    try:
        execution_history = supabase.table("application_execution_sessions").select("id").eq("application_id", application_id).eq("user_id", current_user.id).limit(1).execute().data
    except Exception as exc:
        if "application_execution_sessions" not in str(exc) or not any(code in str(exc) for code in ("PGRST205", "does not exist")):
            raise HTTPException(503, "Submission history could not be checked before deletion") from None
        execution_history = []
    if execution_history:
        raise HTTPException(409, "This application has preparation or submission history. Archive it to preserve the evidence.")
    supabase.table("cold_emails").delete().eq("application_id", application_id).execute()
    supabase.table("tailored_resumes").delete().eq("application_id", application_id).eq("user_id", current_user.id).execute()
    supabase.table("job_applications").delete().eq("id", application_id).eq("user_id", current_user.id).execute()
