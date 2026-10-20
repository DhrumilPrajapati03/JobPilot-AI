"""Maps tailored resume content onto the renderer's ResumeContentJSON schema."""

from app.resume_engine.schemas import RendererType, ResumeContentJSON


def build_render_content(
    content: dict,
    profile: dict | None = None,
    email: str = "",
    renderer: RendererType = RendererType.HTML,
) -> ResumeContentJSON:
    """Build renderer input from a Resume-shaped dict plus the user's profile.

    The Resume model stores education years as ``year`` and certifications as
    objects; the renderer expects ``duration`` and plain strings.
    """
    profile = profile or {}
    education = [
        {
            "institution": edu.get("institution", ""),
            "degree": edu.get("degree", ""),
            "duration": edu.get("duration") or edu.get("year", ""),
            "gpa": edu.get("gpa"),
        }
        for edu in content.get("education", [])
        if isinstance(edu, dict)
    ]
    certifications = []
    for cert in content.get("certifications", []):
        if isinstance(cert, dict):
            label = cert.get("name", "")
            details = ", ".join(v for v in (cert.get("issuer"), cert.get("year")) if v)
            certifications.append(f"{label} ({details})" if details else label)
        elif cert:
            certifications.append(str(cert))

    return ResumeContentJSON(
        name=content.get("name") or profile.get("name") or "",
        headline=content.get("headline") or profile.get("headline") or "",
        email=content.get("email") or email,
        phone=content.get("phone") or profile.get("phone") or "",
        location=profile.get("location") or content.get("location") or "",
        linkedin_url=profile.get("linkedin_url") or content.get("linkedin_url") or None,
        github_url=content.get("github_url"),
        summary=content.get("summary", ""),
        experience=content.get("experience", []),
        skills=content.get("skills") or {},
        projects=content.get("projects", []),
        education=education,
        certifications=certifications,
        renderer=renderer,
        template_id="standard",
    )
