"""Orchestrator Agent.

Coalesces the sub-agents and dual rendering system into an end-to-end
job application pipeline. Progress is streamed over the agent WebSocket as
``{"type": "status", "step", "status", "message", "data"?}`` events where
status is one of ``running | done | warning | error | success``.
"""

import json

from fastapi import HTTPException

from app.agents.cover_letter import CoverLetterAgent
from app.agents.dm_writer import DMWriterAgent
from app.agents.email_writer import EmailWriterAgent
from app.agents.jd_parser import JDParserAgent
from app.agents.resume_tailor import ResumeTailorAgent
from app.resume_engine.builder import build_render_content
from app.resume_engine.renderer import render_resume_pdf
from app.resume_engine.validator import validate_page_count
from app.services.job_filters import evaluate_skip_rules
from app.services import referrals
from app.services.materials import insert_application
from app.services.supabase import get_supabase_client
from app.services.websocket import manager

EMAIL_SEQUENCE_KEYS = ["initial", "follow_up_1", "follow_up_2"]
DEFAULT_CONTACT = {
    "name": "Hiring Team",
    "email": "",
    "linkedin_url": "",
    "title": "Recruiter",
}


def _jsonable(value):
    """Round-trip through JSON so payloads never carry datetimes or other non-JSON types."""
    return json.loads(json.dumps(value, default=str))


def _error_text(error: Exception) -> str:
    if isinstance(error, HTTPException):
        return str(error.detail)
    return str(error)


async def _emit(run_id: str, step: str, status: str, message: str, **data):
    event = {"type": "status", "step": step, "status": status, "message": message}
    if data:
        event["data"] = data
    await manager.send_update(run_id, event)


async def _referral_check(run_id: str, supabase, user_id: str, application: dict, profile: dict, base_resume: dict):
    await _emit(run_id, "referral_check", "running", f"Looking for people you know at {application['company']}...")
    try:
        index = referrals.load_index(supabase, user_id)
    except Exception as e:
        if referrals.is_table_missing(e):
            await _emit(run_id, "referral_check", "done", "Skipped: the network tables aren't set up yet.")
        else:
            await _emit(run_id, "referral_check", "warning", f"Couldn't check your network: {_error_text(e)}")
        return
    ranked = referrals.rank_contacts(index.find(application["company"]), application["role"])
    if not ranked:
        message = (
            f"No contacts at {application['company']} in your network."
            if index.by_key else "Import your LinkedIn connections on the Network page to find referrals."
        )
        await _emit(run_id, "referral_check", "done", message, referrals=0)
        return
    best = ranked[0].contact
    try:
        text, _ = await referrals.draft_referral_message(best, application, profile, base_resume)
        supabase.table("referral_requests").upsert({
            "user_id": user_id, "application_id": application["id"], "contact_id": best["id"],
            "message": text, "status": "drafted",
        }, on_conflict="application_id,contact_id").execute()
        drafted = f" Drafted a referral request to {best.get('full_name')} for you to review."
    except Exception as e:
        print(f"Warning: referral draft failed: {e}")
        drafted = ""
    people = f"{len(ranked)} person" if len(ranked) == 1 else f"{len(ranked)} people"
    await _emit(
        run_id, "referral_check", "done", f"You know {people} at {application['company']}.{drafted}",
        referrals=len(ranked),
    )


async def run_agent_pipeline(
    run_id: str,
    user_id: str,
    user_token: str,
    jd_url: str | None = None,
    jd_text: str | None = None,
    user_email: str = "",
    source: str = "manual",
    supabase=None,
) -> str | None:
    """Executes the complete job application generation pipeline as a background task.

    Progress updates are streamed in real-time to the client via WebSockets.
    ``supabase`` overrides the user-scoped client (scheduled discovery scans run
    without a user session). Returns the new application's id, or None on failure.
    """
    supabase = supabase or get_supabase_client(user_jwt=user_token)

    # 1. Parse Job Description
    await _emit(run_id, "jd_parsing", "running", "Parsing job description using LLM...")
    try:
        parser = JDParserAgent()
        jd_analysis = await parser.parse(jd_url=jd_url, jd_text=jd_text)
        jd_analysis_dict = jd_analysis.model_dump()
        source_text = getattr(parser, "source_text", "") or jd_text or ""
    except Exception as e:
        await _emit(run_id, "jd_parsing", "error", f"Parsing failed: {_error_text(e)}")
        return
    await _emit(
        run_id, "jd_parsing", "done",
        f"Found {jd_analysis.role or 'role'} at {jd_analysis.company or 'company'}",
        role=jd_analysis.role,
        company=jd_analysis.company,
        seniority=jd_analysis.seniority,
        skills=jd_analysis.required_skills[:8],
    )

    # 2. Load User Profile and Base Resume
    await _emit(run_id, "profile_loading", "running", "Retrieving identity vault details...")
    try:
        profile_res = supabase.table("user_profiles").select("*").eq("id", user_id).execute()
        profile = profile_res.data[0] if profile_res.data else {}

        resume_res = supabase.table("resumes").select("*").eq("user_id", user_id).eq("version", "base").execute()
        if not resume_res.data:
            await _emit(
                run_id, "profile_loading", "error",
                "No base resume found. Upload or fill in your resume on the Profile page first.",
            )
            return
        base_resume = resume_res.data[0]
    except Exception as e:
        await _emit(run_id, "profile_loading", "error", f"Failed to retrieve profile: {_error_text(e)}")
        return
    await _emit(
        run_id, "profile_loading", "done",
        f"Loaded base resume with {len(base_resume.get('experience') or [])} roles",
    )

    # Skip rules: the user pasted this job, so warn rather than stop.
    skip_flags = evaluate_skip_rules(profile.get("work_preferences"), jd_analysis.company, source_text, jd_analysis_dict)
    jd_analysis_dict["skip_flags"] = skip_flags
    if skip_flags:
        await _emit(
            run_id, "jd_parsing", "warning",
            "Breaks your skip rules: " + "; ".join(skip_flags),
            skip_flags=skip_flags,
        )

    # 3. Resume Tailoring
    await _emit(run_id, "resume_tailoring", "running", "Rewriting and optimizing resume sections...")
    try:
        tailor = ResumeTailorAgent()
        tailored_result = await tailor.tailor(base_resume, jd_analysis_dict)
        tailored_dict = tailored_result["content"]
        score = tailored_result["keyword_match_score"]
        missing = tailored_result["missing_keywords"]
    except Exception as e:
        await _emit(run_id, "resume_tailoring", "error", f"Resume tailoring failed: {_error_text(e)}")
        return
    if tailor.used_fallback:
        await _emit(
            run_id, "resume_tailoring", "warning",
            f"The AI rewrite failed, so this is your base resume unedited ({score:.0f}% match). Create the application again to retry.",
            score=score,
            missing_keywords=missing[:8],
        )
    else:
        await _emit(
            run_id, "resume_tailoring", "done",
            f"ATS keyword match: {score:.0f}%",
            score=score,
            missing_keywords=missing[:8],
        )

    # 4. Render PDF — non-fatal: the PDF is regenerated on download from the
    # latest (possibly edited) content, so this only verifies the renderer.
    await _emit(run_id, "pdf_rendering", "running", "Compiling PDF document...")
    try:
        content_json = build_render_content(tailored_dict, profile, email=user_email)
        pdf_bytes, _ = await render_resume_pdf(content_json)
        pages = validate_page_count(pdf_bytes)
        if pages > 1:
            await _emit(run_id, "pdf_rendering", "warning", f"PDF rendered but runs {pages} pages — consider trimming.")
        else:
            await _emit(run_id, "pdf_rendering", "done", "One-page PDF rendered")
    except Exception as e:
        print(f"Warning: PDF render failed: {_error_text(e)}")
        await _emit(
            run_id, "pdf_rendering", "warning",
            "PDF engine unavailable on the server — you can still export from the resume preview.",
        )

    # 5. Generate Outreach Drafts (Cover Letter, Cold Email, LinkedIn DM)
    await _emit(
        run_id, "outreach_generation", "running",
        "Drafting cover letter, cold email sequence and LinkedIn messages...",
    )
    # Sequential on purpose: running the three writers at once bursts past
    # low tokens-per-minute limits (e.g. Groq's free tier) and forces template fallbacks.
    writers = {"cover letter": CoverLetterAgent(), "emails": EmailWriterAgent(), "LinkedIn messages": DMWriterAgent()}
    try:
        cover_letter_text = await writers["cover letter"].generate(jd_analysis_dict, profile)
        emails = await writers["emails"].generate(jd_analysis_dict, DEFAULT_CONTACT, profile)
        dms = await writers["LinkedIn messages"].generate(jd_analysis_dict, DEFAULT_CONTACT, profile)
    except Exception as e:
        await _emit(run_id, "outreach_generation", "error", f"Outreach generation failed: {_error_text(e)}")
        return
    fallbacks = [name for name, writer in writers.items() if writer.used_fallback]
    if fallbacks:
        await _emit(
            run_id, "outreach_generation", "warning",
            f"The AI provider failed for the {', '.join(fallbacks)}, so basic templates were used. Rewrite them before sending.",
        )
    else:
        await _emit(run_id, "outreach_generation", "done", "Cover letter, 3 emails and 2 LinkedIn messages drafted")

    # 6. Save Application, Tailored Resume and Cold Emails
    await _emit(run_id, "database_saving", "running", "Logging application in your tracker...")
    application_id = None
    try:
        application = insert_application(supabase, {
            "user_id": user_id,
            "company": jd_analysis_dict.get("company") or "Unknown Company",
            "role": jd_analysis_dict.get("role") or "Unknown Role",
            "jd_url": jd_url or "",
            "jd_text": jd_text or source_text,
            "jd_analysis": _jsonable(jd_analysis_dict),
            "status": "saved",
            "source": source,
            "notes": "",
            "cover_letter": cover_letter_text,
            "linkedin_dm": {
                "connection_request": dms.get("connection_request", ""),
                "follow_up": dms.get("follow_up", ""),
            },
        })
        application_id = application["id"]

        supabase.table("tailored_resumes").insert({
            "application_id": application_id,
            "user_id": user_id,
            "version": 1,
            "content": _jsonable(tailored_dict),
            "pdf_url": "",
            "keyword_match_score": score,
            "missing_keywords": missing,
        }).execute()

        email_rows = [
            {
                "application_id": application_id,
                "user_id": user_id,
                "to_email": "",
                "to_name": "Hiring Manager",
                "subject": emails[key].get("subject", ""),
                "body": emails[key].get("body", ""),
                "sequence_number": idx + 1,
                "opened": False,
                "replied": False,
            }
            for idx, key in enumerate(EMAIL_SEQUENCE_KEYS)
            if emails.get(key)
        ]
        if email_rows:
            supabase.table("cold_emails").insert(email_rows).execute()
    except Exception as e:
        # Don't leave a half-saved application behind; the user can simply retry.
        if application_id:
            for table, column in (("cold_emails", "application_id"), ("tailored_resumes", "application_id"), ("job_applications", "id")):
                try:
                    supabase.table(table).delete().eq(column, application_id).execute()
                except Exception as cleanup_error:
                    print(f"Warning: cleanup of {table} failed: {cleanup_error}")
        await _emit(run_id, "database_saving", "error", f"Failed to save application data: {_error_text(e)}")
        return
    await _emit(run_id, "database_saving", "done", "Application saved to tracker")

    # 7. Referral first: does the user know anyone there? Never fails the run.
    await _referral_check(run_id, supabase, user_id, application, profile, base_resume)

    # Pipeline Completion
    await manager.send_update(run_id, {
        "type": "status",
        "step": "complete",
        "status": "success",
        "message": "Job application generated successfully!",
        "application_id": application_id,
        "data": {"score": score, "company": application["company"], "role": application["role"]},
    })

    # Work out the apply link and pre-answer the form where its questions are public.
    try:
        from app.services.autopilot import prepare_application_form
        await prepare_application_form(supabase, user_id, application_id, user_email)
    except Exception as e:
        print(f"Warning: preparing the application form failed: {e}")
    return application_id
