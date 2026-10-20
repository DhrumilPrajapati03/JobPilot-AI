"""Endpoints for the JobPilot Chrome extension.

The extension authenticates with a personal token (``X-JobPilot-Token``)
created in Settings. These endpoints use the service-role client, always
filtered to the token's user. The extension fills forms; it never submits them.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.resume_engine.builder import build_render_content
from app.resume_engine.renderer import render_resume_pdf
from app.services import autopilot, form_answers
from app.services.supabase import get_supabase_admin_client

router = APIRouter()
FOLLOW_UP_AFTER_DAYS = 5


@dataclass
class ExtensionUser:
    id: str
    email: str
    supabase: object


async def get_extension_user(x_jobpilot_token: str = Header(default="")) -> ExtensionUser:
    if not x_jobpilot_token.startswith(autopilot.TOKEN_PREFIX):
        raise HTTPException(status_code=401, detail="Connect the extension from JobPilot → Settings.")
    if not autopilot.server_ready():
        raise HTTPException(status_code=503, detail="The server needs SUPABASE_SERVICE_KEY for the extension to work.")
    admin = get_supabase_admin_client()
    try:
        rows = admin.table("extension_tokens").select("id, user_id").eq("token_hash", autopilot.hash_token(x_jobpilot_token)).execute().data
    except Exception as e:
        if autopilot._missing_table(e, "extension_tokens"):
            raise HTTPException(status_code=503, detail="Run supabase/migrations/20261014_autopilot.sql in Supabase.")
        raise
    if not rows:
        raise HTTPException(status_code=401, detail="This extension token was revoked. Reconnect from JobPilot → Settings.")
    row = rows[0]
    admin.table("extension_tokens").update({"last_used_at": datetime.now(timezone.utc).isoformat()}).eq("id", row["id"]).execute()
    return ExtensionUser(id=row["user_id"], email=autopilot.account_email(admin, row["user_id"]), supabase=admin)


class FieldIn(BaseModel):
    key: str = Field(max_length=300)
    label: str = Field(max_length=1000)
    type: str = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=300)


class FillRequest(BaseModel):
    url: str = Field(default="", max_length=2000)
    application_id: str | None = None
    fields: list[FieldIn] = Field(max_length=150)


class MatchRequest(BaseModel):
    url: str = Field(max_length=2000)
    title: str = Field(default="", max_length=500)


class AppliedRequest(BaseModel):
    application_id: str


class SavedAnswer(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(max_length=4000)


class AnswersRequest(BaseModel):
    answers: list[SavedAnswer] = Field(max_length=50)


def _application(user: ExtensionUser, application_id: str) -> dict:
    try:
        rows = user.supabase.table("job_applications").select("*").eq("id", application_id).eq("user_id", user.id).execute().data
    except Exception:
        rows = []
    if not rows:
        raise HTTPException(status_code=404, detail="Application not found")
    return rows[0]


def _key(url: str) -> str:
    """Comparable form of a job URL: host + path, without apply/application suffixes or tracking."""
    url = (url or "").lower().split("#")[0]
    gh = re.search(r"gh_jid=(\d+)", url) or re.search(r"greenhouse\.io/[\w-]+/jobs/(\d+)", url)
    if gh:
        return f"gh:{gh.group(1)}"
    url = re.sub(r"^https?://(www\.)?", "", url.split("?")[0]).rstrip("/")
    return re.sub(r"/(apply|application)$", "", url)


@router.get("/me")
async def me(user: ExtensionUser = Depends(get_extension_user)):
    profile = (user.supabase.table("user_profiles").select("name").eq("id", user.id).execute().data or [{}])[0]
    return {"email": user.email, "name": profile.get("name") or ""}


@router.get("/queue")
async def queue(user: ExtensionUser = Depends(get_extension_user)):
    return {"queue": autopilot.build_queue(user.supabase, user.id)}


@router.post("/match")
async def match(request: MatchRequest, user: ExtensionUser = Depends(get_extension_user)):
    """Which saved application this page is for, if any."""
    target = _key(request.url)
    for item in autopilot.build_queue(user.supabase, user.id):
        if target and target == _key(item["apply_url"]):
            return {"application": item}
    apps = user.supabase.table("job_applications").select("id, role, company, jd_url, status").eq("user_id", user.id).execute().data
    for a in apps:
        if target and target == _key(a.get("jd_url") or ""):
            return {"application": a}
    return {"application": None}


@router.post("/fill")
async def fill(request: FillRequest, user: ExtensionUser = Depends(get_extension_user)):
    """Answers for the fields on the page. Reuses tonight's prepared AI drafts where labels match."""
    application = _application(user, request.application_id) if request.application_id else None
    ctx = autopilot.applicant_context(user.supabase, user.id, user.email, application)
    prepared = (application or {}).get("prepared_form") or {}
    reuse = {f["label"]: f["value"] for f in prepared.get("fields") or [] if f.get("source") == "ai" and isinstance(f.get("value"), str)}
    fields = [form_answers.FormField(**f.model_dump()) for f in request.fields]
    answers = await form_answers.answer_fields(fields, ctx, use_ai=application is not None, reuse=reuse)
    return {
        "application_id": (application or {}).get("id"),
        "answers": [a.to_dict() for a in answers],
        "summary": form_answers.summarise(answers),
    }


@router.get("/resume/{application_id}")
async def resume_pdf(application_id: str, user: ExtensionUser = Depends(get_extension_user)):
    """The tailored resume as a PDF, for the form's upload field."""
    _application(user, application_id)
    tailored = user.supabase.table("tailored_resumes").select("*").eq("application_id", application_id).eq("user_id", user.id).order("version", desc=True).limit(1).execute().data
    if not tailored:
        raise HTTPException(status_code=404, detail="No tailored resume for this application")
    profile = (user.supabase.table("user_profiles").select("*").eq("id", user.id).execute().data or [{}])[0]
    try:
        content = build_render_content(tailored[0].get("content") or {}, profile, email=user.email)
        pdf, _ = await render_resume_pdf(content)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"PDF renderer unavailable on the server: {str(e).splitlines()[0]}")
    name = re.sub(r"[^A-Za-z0-9]+", "_", content.name or "Resume").strip("_") or "Resume"
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}_Resume.pdf"'})


@router.post("/applied")
async def mark_applied(request: AppliedRequest, user: ExtensionUser = Depends(get_extension_user)):
    """The user submitted the form: move the application to Applied and schedule a follow-up."""
    from datetime import timedelta

    app = _application(user, request.application_id)
    now = datetime.now(timezone.utc)
    payload = {"status": "applied"}
    if not app.get("applied_at"):
        payload["applied_at"] = now.isoformat()
    if not app.get("follow_up_at"):
        payload["follow_up_at"] = (now + timedelta(days=FOLLOW_UP_AFTER_DAYS)).isoformat()
    user.supabase.table("job_applications").update(payload).eq("id", app["id"]).eq("user_id", user.id).execute()
    return {"application_id": app["id"], "status": "applied"}


@router.post("/answers", status_code=status.HTTP_201_CREATED)
async def save_answers(request: AnswersRequest, user: ExtensionUser = Depends(get_extension_user)):
    """Save answers the user typed into a form, so next time they're filled automatically."""
    rows = [
        {"user_id": user.id, "question": a.question.strip()[:500], "answer": a.answer.strip(), "category": "custom", "sensitive": False}
        for a in request.answers if a.answer.strip()
    ]
    if rows:
        user.supabase.table("qa_answers").upsert(rows, on_conflict="user_id,question").execute()
    return {"saved": len(rows)}

