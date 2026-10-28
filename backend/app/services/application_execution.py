"""Owner-scoped, append-only preparation and submission observations.

Browser evidence is explicitly unverified; only a user report changes status.
No raw field answers, screenshots, page HTML or employer responses are stored.
"""
import base64
import hashlib
import re
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from app.resume_engine.builder import build_render_content
from app.resume_engine.renderer import render_resume_pdf

DOCUMENT_FIELDS = "id,user_id,application_id,resume_version,name,sha256,size_bytes,created_at"
PROVIDERS = {
    "boards.greenhouse.io": "greenhouse", "job-boards.greenhouse.io": "greenhouse",
    "job-boards.eu.greenhouse.io": "greenhouse", "jobs.lever.co": "lever", "jobs.eu.lever.co": "lever",
    "jobs.ashbyhq.com": "ashby", "jobs.smartrecruiters.com": "smartrecruiters",
}


def page_url(value: str) -> str:
    try:
        p = urlsplit(value)
        if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password or (p.scheme == "http" and p.hostname not in ("localhost", "127.0.0.1")):
            raise ValueError()
        # Preserve requisition identity, never arbitrary tracking/session tokens.
        pairs = parse_qsl(p.query)
        ids = {"gh_jid", "jobId", "job_id", "requisitionId", "jobpilot_identity"}
        retained = [(k, v) for k, v in pairs if k in ids]
        unknown = sorted((k, v) for k, v in pairs if k not in ids and not k.lower().startswith("utm_") and k.lower() not in {"ref", "source", "src", "gh_src", "trackingid"})
        if unknown:
            retained.append(("jobpilot_identity", hashlib.sha256(urlencode(unknown).encode()).hexdigest()))
        query = urlencode(sorted(retained))
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", query, ""))[:2000]
    except (ValueError, TypeError):
        raise HTTPException(422, "Use a valid HTTPS employer-form URL") from None


def page_key(value: str) -> str:
    if not value:
        return ""
    p = urlsplit(page_url(value))
    if PROVIDERS.get(p.hostname) == "greenhouse":
        match = re.search(r"/jobs/(\d+)", p.path)
        job_id = (match.group(1) if match else dict(parse_qsl(p.query)).get("gh_jid"))
        if job_id:
            return "greenhouse:" + job_id
    if PROVIDERS.get(p.hostname) in {"lever", "ashby", "smartrecruiters"}:
        segments = p.path.strip("/").split("/")
        if len(segments) >= 2:
            return f"{p.scheme}://{p.netloc}/" + "/".join(segments[:2])
    return urlunsplit((p.scheme, p.netloc, re.sub(r"/(apply|application)/?$", "", p.path).rstrip("/"), p.query, ""))


def owned(db, user_id, application_id):
    rows = db.table("job_applications").select("*").eq("id", str(application_id)).eq("user_id", user_id).execute().data
    if not rows:
        raise HTTPException(404, "Application not found")
    return rows[0]


def command(db, name, **params):
    try:
        return db.rpc(name, params).execute().data
    except Exception as exc:
        code = str(exc)
        if "execution_not_found" in code:
            raise HTTPException(404, "Application session not found") from None
        if any(s in code for s in ("execution_conflict", "execution_expired", "execution_preparation_required", "execution_attempt_required", "execution_status_conflict")):
            raise HTTPException(409, "Session expired, changed or missing earlier evidence. Review and start again.") from None
        raise HTTPException(503, "Application evidence is unavailable. Apply the Sprint 5 migration before using this workflow.") from None


def session(db, uid, session_id):
    rows = db.table("application_execution_sessions").select("*").eq("id", str(session_id)).eq("user_id", uid).execute().data
    if not rows:
        raise HTTPException(404, "Application session not found")
    return rows[0]


async def start(db, uid, email, app_id, session_id, url, confirmed=False):
    app = owned(db, uid, app_id)
    url = page_url(url)
    candidates = [app.get("jd_url"), (app.get("prepared_form") or {}).get("apply_url")]
    matches = False
    for candidate in candidates:
        try:
            matches = matches or bool(candidate and page_key(candidate) == page_key(url))
        except HTTPException:
            continue
    if not matches and not confirmed:
        raise HTTPException(409, "Confirm that this form is for the selected company and role before linking it.")
    existing = db.table("application_execution_sessions").select("id").eq("id", str(session_id)).eq("user_id", uid).execute().data
    document = None
    if not existing:
        tailored = db.table("tailored_resumes").select("*").eq("application_id", str(app_id)).eq("user_id", uid).order("version", desc=True).limit(1).execute().data
        if tailored:
            profile = (db.table("user_profiles").select("*").eq("id", uid).execute().data or [{}])[0]
            try:
                content = build_render_content(tailored[0].get("content") or {}, profile, email=email)
                raw, _ = await render_resume_pdf(content)
                if not raw.startswith(b"%PDF-") or not 5 <= len(raw) <= 2 * 1024 * 1024:
                    raise ValueError()
            except Exception:
                raise HTTPException(503, "The tailored PDF could not be frozen. Retry preparation or use profile-only filling.") from None
            name = re.sub(r"[^A-Za-z0-9]+", "_", content.name or "Resume").strip("_") or "Resume"
            document = {"resume_version": tailored[0].get("version", 1), "name": name + "_Resume.pdf", "sha256": hashlib.sha256(raw).hexdigest(),
                        "size_bytes": len(raw), "pdf_base64": base64.b64encode(raw).decode("ascii")}
    result = command(db, "create_application_session", p_user_id=uid, p_id=str(session_id), p_application_id=str(app_id),
                     p_page_url=url, p_link_method="url_match" if matches else "user_confirmed", p_document=document)
    doc = None
    if result.get("document_id"):
        doc = (db.table("application_documents").select(DOCUMENT_FIELDS).eq("id", result["document_id"]).eq("user_id", uid).execute().data or [None])[0]
    return {"session": result, "document": doc, "application": {"id": app["id"], "company": app.get("company"), "role": app.get("role")}}


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=300)
    type: str = Field(max_length=30)
    required: bool
    outcome: Literal["filled", "preserved", "review", "missing", "invalid", "skipped"]
    source: Literal["profile", "answer_bank", "cover_letter", "resume", "default", "ai", "none", "user"]


class Preparation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=2000)
    fields: list[Observation] = Field(max_length=150)
    truncated: bool = False
    document_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class Attempt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=2000)


class Confirmation(Attempt):
    attempt_key: uuid.UUID
    rule: Literal["greenhouse_confirmation", "lever_confirmation", "ashby_confirmation", "smartrecruiters_confirmation"]


def append(db, uid, sid, kind, key, data):
    s = session(db, uid, sid)
    model = {"form_prepared": Preparation, "submission_attempted": Attempt, "submission_confirmation_observed": Confirmation}[kind]
    details = model.model_validate(data).model_dump(mode="json")
    details["url"] = page_url(details["url"])
    if urlsplit(details["url"]).netloc != urlsplit(s["page_url"]).netloc or urlsplit(details["url"]).scheme != urlsplit(s["page_url"]).scheme:
        raise HTTPException(409, "The observation belongs to another employer origin")
    if kind != "submission_confirmation_observed" and page_key(details["url"]) != page_key(s["page_url"]):
        raise HTTPException(409, "The form changed to another opening. Start a new preparation session.")
    if kind == "submission_confirmation_observed":
        provider = PROVIDERS.get(urlsplit(s["page_url"]).hostname)
        if details["rule"] != f"{provider}_confirmation":
            raise HTTPException(422, "Unsupported confirmation evidence")
        details["verification"] = "browser_observation_not_independently_verified"
    if kind == "form_prepared":
        if len({f["key"] for f in details["fields"]}) != len(details["fields"]):
            raise HTTPException(422, "Duplicate observed field keys")
        if details.get("document_sha256"):
            docs = db.table("application_documents").select("sha256").eq("id", s.get("document_id")).eq("user_id", uid).execute().data
            if not docs or docs[0]["sha256"] != details["document_sha256"]:
                raise HTTPException(409, "Selected PDF differs from the session snapshot")
        details["summary"] = {"total": len(details["fields"]), **{outcome: sum(f["outcome"] == outcome for f in details["fields"]) for outcome in ("filled", "preserved", "review", "missing", "invalid", "skipped")},
                              "required_missing": sum(f["required"] and f["outcome"] in ("missing", "invalid", "skipped") for f in details["fields"])}
    return command(db, "append_application_event", p_user_id=uid, p_session_id=str(sid), p_kind=kind, p_key=str(key), p_details=details)


def report(db, uid, app_id, sid=None, key=None):
    app = owned(db, uid, app_id)
    # A deterministic legacy report session permits retries without duplicate rows.
    sid = str(sid or uuid.uuid5(uuid.NAMESPACE_URL, f"jobpilot:manual:{uid}:{app_id}"))
    if not session_exists(db, uid, sid):
        command(db, "create_application_session", p_user_id=uid, p_id=sid, p_application_id=str(app_id),
                p_page_url="", p_link_method="manual_report", p_document=None)
    s = session(db, uid, sid)
    if s["application_id"] != str(app_id):
        raise HTTPException(404, "Application session not found")
    key = str(key or uuid.uuid5(uuid.NAMESPACE_URL, f"jobpilot:report:{sid}"))
    return command(db, "append_application_event", p_user_id=uid, p_session_id=sid, p_kind="user_reported_submitted", p_key=key,
                   p_details={"verification": "user_reported_not_independently_verified"})


def session_exists(db, uid, sid):
    return bool(db.table("application_execution_sessions").select("id").eq("id", sid).eq("user_id", uid).execute().data)
