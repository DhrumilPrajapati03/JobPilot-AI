"""Application management endpoints.

Handles the core job application workflow: parsing JDs,
running the agent pipeline, listing applications, and
updating application status.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


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
    status: str


@router.post("/parse-jd")
async def parse_jd(request: JDParseRequest):
    """Parse a job description URL or raw text.

    Extracts structured analysis: role, company, required skills,
    keywords, tone, seniority level, and tech stack.

    Args:
        request: JD URL or raw text to parse.
    """
    # TODO: Invoke JD Parser Agent
    return {
        "status": "parsed",
        "analysis": {
            "role": "placeholder",
            "company": "placeholder",
            "skills": [],
            "keywords": [],
            "seniority": "mid",
            "tone": "professional",
            "tech_stack": [],
        },
    }


@router.post("/generate")
async def generate_application(request: ApplicationGenerateRequest):
    """Run the full agent pipeline for a single application.

    Orchestrates: JD parsing → research → resume tailoring →
    cover letter → cold email → LinkedIn DM → tracker update.

    Returns a run_id for WebSocket progress streaming.

    Args:
        request: JD input and pipeline configuration.
    """
    # TODO: Launch LangGraph orchestrator agent pipeline
    return {
        "status": "queued",
        "run_id": "placeholder-run-id",
        "message": "Agent pipeline started. Connect to WebSocket for progress.",
    }


@router.get("/")
async def list_applications(
    status: str | None = None,
    source: str | None = None,
    skip: int = 0,
    limit: int = 20,
):
    """List all job applications with optional filters.

    Args:
        status: Filter by application status (e.g., 'applied', 'interviewing').
        source: Filter by job source (e.g., 'linkedin', 'adzuna').
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
    """
    # TODO: Query Supabase for applications with filters
    return {
        "applications": [],
        "total": 0,
        "skip": skip,
        "limit": limit,
    }


@router.put("/{application_id}/status")
async def update_application_status(application_id: str, request: StatusUpdateRequest):
    """Update the status of a specific application.

    Valid statuses: saved, applied, interviewing, offer, rejected, archived.

    Args:
        application_id: Unique application identifier.
        request: New status value.
    """
    # TODO: Update application status in Supabase
    return {
        "application_id": application_id,
        "status": request.status,
        "updated": True,
    }
