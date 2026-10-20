"""Pydantic schemas for the dual resume rendering engine.

Ensures structured inputs for WeasyPrint/Tectonic renderers.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class RendererType(str, Enum):
    LATEX = "latex"
    HTML = "html"

class ExperienceItem(BaseModel):
    company: str
    role: str
    duration: str
    location: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)

class ProjectItem(BaseModel):
    name: str
    description: str = ""
    tech: List[str] = Field(default_factory=list)
    url: Optional[str] = None

class EducationItem(BaseModel):
    institution: str
    degree: str
    duration: str = ""
    gpa: Optional[str] = None

class SkillSet(BaseModel):
    primary: List[str] = Field(default_factory=list)
    secondary: List[str] = Field(default_factory=list)

class ResumeContentJSON(BaseModel):
    name: str
    headline: str
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    summary: str  # 3 lines max recommended
    experience: List[ExperienceItem] = Field(default_factory=list)
    skills: SkillSet = Field(default_factory=SkillSet)
    projects: List[ProjectItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    renderer: RendererType = RendererType.LATEX
    template_id: str = "standard"
