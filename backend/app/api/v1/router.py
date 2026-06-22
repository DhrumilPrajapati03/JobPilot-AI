"""Main API v1 router that aggregates all sub-routers."""

from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    applications,
    auth,
    contacts,
    email,
    profile,
    resume,
)

api_v1_router = APIRouter()

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
    analytics.router,
    prefix="/analytics",
    tags=["Analytics"],
)
