"""Main API v1 router that aggregates all sub-routers."""

from fastapi import APIRouter
from app.api.v1 import runs

from app.api.v1 import (
    agent,
    analytics,
    answers,
    applications,
    auth,
    autopilot,
    contacts,
    discovery,
    network,
    email,
    extension,
    profile,
    resume,
)

api_v1_router = APIRouter()
api_v1_router.include_router(runs.router, prefix="/runs", tags=["Background runs"])

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
    analytics.router,
    prefix="/analytics",
    tags=["Analytics"],
)
