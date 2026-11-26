"""Contacts CRM (plan section 6, screen 7): people Recon found or you added, with history,
channel, cooldown and dedupe. Your edits are marked as yours, so Recon never overwrites them."""
import asyncio
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core import contacts
from app.core.policy import load_policy
from app.services.auth import CurrentUser, get_current_user

router = APIRouter()
RoleClass = Literal["recruiter", "hiring_manager", "ceo", "cto", "employee", "unknown"]


def _public(contact: dict) -> dict:
    out = {k: v for k, v in contact.items() if k not in ("legacy",)}
    out["imported"] = contact.get("legacy", False)
    out["connected"] = contacts.connected(contact)
    return out


@router.get("/contacts")
async def list_contacts(company: str = "", role_class: RoleClass | None = None, q: str = Query("", max_length=100),
                        include_imported: bool = False, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                        user: CurrentUser = Depends(get_current_user)):
    rows = await asyncio.to_thread(contacts.list_contacts, user.id, company=company, role_class=role_class or "", q=q,
                                   include_imported=include_imported, limit=limit, offset=offset)
    return {"contacts": [_public(r) for r in rows], "total": len(rows)}


@router.get("/contacts/{contact_id}")
async def get_contact(contact_id: str, user: CurrentUser = Depends(get_current_user)):
    contact = await asyncio.to_thread(contacts.get_contact, user.id, contact_id)
    if contact is None:
        raise HTTPException(404, "Contact not found")
    touches = await asyncio.to_thread(contacts.last_touches, user.id, [contact_id])
    days = load_policy().caps["no_contact_if_touched_within_days"]
    blocked = contacts.contact_blocker(contact, touches.get(contact_id), days, datetime.now(timezone.utc))
    return {**_public(contact), "last_touch_at": touches.get(contact_id), "blocked": blocked}


class ContactPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=160)
    company: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    linkedin_url: str | None = Field(default=None, max_length=300)
    x_handle: str | None = Field(default=None, max_length=15)
    github: str | None = Field(default=None, max_length=39)
    role_class: RoleClass | None = None
    notes: str | None = Field(default=None, max_length=2000)
    do_not_contact: bool | None = None


@router.patch("/contacts/{contact_id}")
async def update_contact(contact_id: str, body: ContactPatch, user: CurrentUser = Depends(get_current_user)):
    from app.experts.reviewer import EMAIL
    changes = body.model_dump(exclude_none=True)
    if changes.get("email") and not EMAIL.match(changes["email"].strip()):
        raise HTTPException(422, "The email doesn't look valid.")
    try:
        contact = await asyncio.to_thread(contacts.update_contact, user.id, contact_id, changes)
    except Exception as exc:
        if "contact_linkedin_slug_key" in str(exc):
            raise HTTPException(409, "Another contact already has that LinkedIn profile.") from None
        raise
    if contact is None:
        raise HTTPException(404, "Contact not found")
    return _public(contact)


@router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(contact_id: str, user: CurrentUser = Depends(get_current_user)):
    if not await asyncio.to_thread(contacts.delete_contact, user.id, contact_id):
        raise HTTPException(404, "Contact not found")
