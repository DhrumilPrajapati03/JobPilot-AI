"""Resume management endpoints.

Handles base resume uploads, structured updates, and storage.
"""

import re
import uuid
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Response, status
from app.services.auth import get_current_user, CurrentUser
from app.services.supabase import get_supabase_client
from app.services.parser import extract_text_from_pdf, extract_text_from_docx, parse_resume_text
from app.models.resume import Resume
from app.resume_engine.builder import build_render_content
from app.resume_engine.renderer import render_resume_pdf
from app.resume_engine.validator import calculate_ats_score
from app.services.vector_store import embed_resume

router = APIRouter()


def _latest_tailored_resume(supabase, application_id: str, user_id: str) -> dict:
    response = (
        supabase.table("tailored_resumes")
        .select("*")
        .eq("application_id", application_id)
        .eq("user_id", user_id)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Tailored resume not found")
    return response.data[0]


@router.get("/tailored/{application_id}")
async def get_tailored_resume(application_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Return the latest tailored resume record for a specific application."""
    try:
        supabase = get_supabase_client(user_jwt=current_user.token)
        return _latest_tailored_resume(supabase, application_id, current_user.id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch tailored resume: {str(e)}"
        )


@router.put("/tailored/{application_id}")
async def update_tailored_resume(
    application_id: str,
    content: Resume,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Save edits to a tailored resume and recompute its ATS keyword score."""
    supabase = get_supabase_client(user_jwt=current_user.token)
    tailored = _latest_tailored_resume(supabase, application_id, current_user.id)

    app_res = (
        supabase.table("job_applications")
        .select("jd_analysis")
        .eq("id", application_id)
        .eq("user_id", current_user.id)
        .execute()
    )
    jd_analysis = (app_res.data[0].get("jd_analysis") if app_res.data else None) or {}

    content_dict = content.model_dump(mode="json", exclude_none=True)
    score, missing = calculate_ats_score(content_dict, jd_analysis)
    response = (
        supabase.table("tailored_resumes")
        .update({"content": content_dict, "keyword_match_score": score, "missing_keywords": missing})
        .eq("id", tailored["id"])
        .eq("user_id", current_user.id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to save tailored resume.")
    return response.data[0]


@router.get("/tailored/{application_id}/pdf")
async def download_tailored_resume_pdf(
    application_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Render the latest tailored resume content to PDF on demand."""
    supabase = get_supabase_client(user_jwt=current_user.token)
    tailored = _latest_tailored_resume(supabase, application_id, current_user.id)
    profile_res = supabase.table("user_profiles").select("*").eq("id", current_user.id).execute()
    profile = profile_res.data[0] if profile_res.data else {}

    try:
        content = build_render_content(tailored.get("content") or {}, profile, email=current_user.email)
        pdf_bytes, _ = await render_resume_pdf(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PDF renderer unavailable: {str(e).splitlines()[0]}",
        )

    slug = re.sub(r"[^A-Za-z0-9]+", "_", content.name or "resume").strip("_") or "resume"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{slug}_resume.pdf"'},
    )


@router.get("/base", response_model=Resume)
async def get_base_resume(current_user: CurrentUser = Depends(get_current_user)):
    """Retrieve the user's base resume content as JSON."""
    try:
        supabase = get_supabase_client(user_jwt=current_user.token)
        response = (
            supabase.table("resumes")
            .select("*")
            .eq("user_id", current_user.id)
            .eq("version", "base")
            .execute()
        )
        if not response.data:
            return Resume(user_id=current_user.id, version="base")
        return response.data[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch resume: {str(e)}"
        )


@router.post("/base", response_model=Resume)
async def save_base_resume(
    resume_data: dict,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Save or update the user's structured base resume."""
    try:
        supabase = get_supabase_client(user_jwt=current_user.token)
        resume_data["user_id"] = current_user.id
        resume_data["version"] = "base"
        existing = (
            supabase.table("resumes")
            .select("id")
            .eq("user_id", current_user.id)
            .eq("version", "base")
            .execute()
        )
        if existing.data:
            resume_data["id"] = existing.data[0]["id"]
        response = supabase.table("resumes").upsert(resume_data).execute()
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save resume."
            )
        try:
            saved_resume = Resume(**response.data[0])
            embed_resume(current_user.id, saved_resume)
        except Exception as embedding_error:
            print(f"Warning: Failed to update vector database: {str(embedding_error)}")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save resume: {str(e)}"
        )


@router.post("/upload", response_model=Resume)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Upload a base resume file (PDF/DOCX) for text extraction and LLM parsing."""
    file_bytes = await file.read()
    filename = file.filename or "resume.pdf"

    if filename.endswith(".pdf"):
        raw_text = extract_text_from_pdf(file_bytes)
    elif filename.endswith(".docx"):
        raw_text = extract_text_from_docx(file_bytes)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload a PDF or DOCX file."
        )

    if not raw_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file has no readable text content."
        )

    try:
        parsed_resume = parse_resume_text(raw_text)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to structure resume content: {str(e)}"
        )

    supabase = get_supabase_client(user_jwt=current_user.token)
    storage_path = ""
    try:
        storage_path = f"{current_user.id}/{uuid.uuid4()}_{filename}"
        content_type = file.content_type or "application/octet-stream"
        supabase.storage.from_("resumes").upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type}
        )
    except Exception as e:
        print(f"Warning: Storage upload failed: {str(e)}")
        storage_path = ""

    try:
        resume_dict = parsed_resume.model_dump(exclude_none=True)
        resume_dict["user_id"] = current_user.id
        resume_dict["version"] = "base"
        existing = (
            supabase.table("resumes")
            .select("id")
            .eq("user_id", current_user.id)
            .eq("version", "base")
            .execute()
        )
        if existing.data:
            resume_dict["id"] = existing.data[0]["id"]
        save_response = supabase.table("resumes").upsert(resume_dict).execute()
        if not save_response.data:
            raise Exception("No data returned from database upsert.")
        try:
            saved_resume = Resume(**save_response.data[0])
            embed_resume(current_user.id, saved_resume)
        except Exception as embedding_error:
            print(f"Warning: Failed to update vector database: {str(embedding_error)}")
        return save_response.data[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Parsed successfully, but failed to save in database: {str(e)}"
        )
