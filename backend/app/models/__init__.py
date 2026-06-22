"""Data models for JobPilot AI.

Pydantic models representing the core entities
used throughout the application.
"""

from app.models.application import JobApplication
from app.models.contact import HRContact
from app.models.email import ColdEmail
from app.models.resume import Resume, ResumeExperience, ResumeProject, ResumeSkills, TailoredResume
from app.models.template import Template
from app.models.user import UserProfile

__all__ = [
    "UserProfile",
    "Resume",
    "ResumeExperience",
    "ResumeProject",
    "ResumeSkills",
    "TailoredResume",
    "JobApplication",
    "ColdEmail",
    "HRContact",
    "Template",
]
