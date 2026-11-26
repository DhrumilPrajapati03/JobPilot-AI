"""Main API v1 router that aggregates all sub-routers."""

from fastapi import APIRouter
from app.api.v1 import runs
from app.api.v1 import research
from app.api.v1 import templates

from app.api.v1 import (
    agent,
    analytics,
    answers,
    applications,
    auth,
    autopilot,
    cases,
    experts,
    contacts,
    crm,
    answer_bank,
    sidepanel,
    discovery,
    network,
    email,
    extension,
    profile,
    resume,
)

api_v1_router = APIRouter()
api_v1_router.include_router(templates.router, prefix='/templates', tags=['Writing templates'])
api_v1_router.include_router(research.router, prefix='/research', tags=['Cited company research'])
api_v1_router.include_router(runs.router, prefix="/runs", tags=["Background runs"])
api_v1_router.include_router(cases.router, prefix="/cases", tags=["Cases and actions"])
api_v1_router.include_router(experts.router, prefix="/experts", tags=["Experts"])

api_v1_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"],
)
api_v1_router.include_router(
    profile.router,
    prefix="/profile",
    tags=["Identity Vault"],
)
api_v1_router.include_router(
    applications.router,
    prefix="/applications",
    tags=["Applications"],
)
api_v1_router.include_router(
    answers.router,
    prefix="/answers",
    tags=["Answer Bank"],
)
api_v1_router.include_router(
    resume.router,
    prefix="/resume",
    tags=["Resume"],
)
api_v1_router.include_router(
    email.router,
    prefix="/email",
    tags=["Email"],
)
api_v1_router.include_router(
    contacts.router,
    prefix="/contacts",
    tags=["HR Contacts"],
)
api_v1_router.include_router(
    answer_bank.router,
    prefix="/answer-bank",
    tags=["Answer bank"],
)
api_v1_router.include_router(
    crm.router,
    prefix="/crm",
    tags=["Contacts CRM"],
)
api_v1_router.include_router(
    agent.router,
    prefix="/agent",
    tags=["Assistant"],
)
api_v1_router.include_router(
    discovery.router,
    prefix="/discovery",
    tags=["Job Discovery"],
)
api_v1_router.include_router(
    network.router,
    prefix="/network",
    tags=["Network & Referrals"],
)
api_v1_router.include_router(
    autopilot.router,
    prefix="/autopilot",
    tags=["Autopilot"],
)
api_v1_router.include_router(
    extension.router,
    prefix="/extension",
    tags=["Chrome extension"],
)
api_v1_router.include_router(
    sidepanel.router,
    prefix="/extension",
    tags=["Chrome extension: JobDots side panel"],
)
api_v1_router.include_router(
    analytics.router,
    prefix="/analytics",
    tags=["Analytics"],
)
