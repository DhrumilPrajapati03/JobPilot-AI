"""Resume management endpoints.

Handles base resume uploads, structured updates, and storage.
"""

import uuid
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from app.services.auth import get_current_user, CurrentUser
from app.services.supabase import get_supabase_client
from app.services.parser import extract_text_from_pdf, extract_text_from_docx, parse_resume_text
from app.models.resume import Resume

router = APIRouter()


@router.get("/tailored/{application_id}")
async def get_tailored_resume(application_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Download the tailored resume PDF for a specific application."""
    try:
        supabase = get_supabase_client(user_jwt=current_user.token)
        response = (
            supabase.table("tailored_resumes")
            .select("*")
            .eq("application_id", application_id)
            .eq("user_id", current_user.id)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="Tailored resume not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch tailored resume: {str(e)}"
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
        return save_response.data[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Parsed successfully, but failed to save in database: {str(e)}"
        )
