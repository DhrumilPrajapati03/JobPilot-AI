"""Contacts CRM (plan sections 2.4 and 6): one row per person, merged across sources.

Identity, strongest first: the LinkedIn profile (unique per owner), the email address, then
name + company. Merging only fills gaps: something you typed (`source = 'you'`,
`email_source = 'you'`) is never overwritten by Recon, and a found title never replaces
yours. Every detail keeps where it came from (`sources`, `email_source`).

Contact history is `contact_touch` (written by Courier when something is sent) plus the
actions that named the contact; the cooldown and do-not-contact flags are read from here
by Recon (to rank) and by Reviewer and Courier (to block).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from app.db import get_db
from app.recon.people import canonical_linkedin, core_company, linkedin_slug, same_company

FIELDS = ("company", "name", "title", "linkedin_url", "email", "x_handle", "github", "role_class", "stage", "source",
          "confidence", "email_source", "sources", "notes", "do_not_contact", "legacy")
_COLUMNS = "id::text, " + ", ".join(FIELDS) + ", created_at, updated_at"
MAX_SOURCES = 10
EDITABLE = {"name", "title", "email", "x_handle", "github", "role_class", "notes", "do_not_contact", "company", "linkedin_url"}


def _row(row) -> dict:
    keys = ("id", *FIELDS, "created_at", "updated_at")
    return dict(zip(keys, row))


def dedupe_key(company: str, name: str, linkedin_url: str = "", email: str = "") -> str:
    slug = linkedin_slug(linkedin_url)
    if slug:
        return f"li:{slug}"
    if email:
        return f"email:{email.strip().lower()}"
    return f"name:{core_company(company)}:{' '.join(name.lower().split())}"


def upsert(user_id: str, *, company: str, name: str, title: str = "", role_class: str = "unknown",
           linkedin_url: str = "", email: str = "", email_source: str = "", github: str = "", x_handle: str = "",
           confidence: float | None = None, source: str = "recon", evidence: list[str] | None = None,
           source_urls: list[str] | None = None, stage: str = "classified") -> dict:
    """Insert or merge one person; returns the stored contact."""
    linkedin_url = canonical_linkedin(linkedin_url) or ""
    slug = linkedin_slug(linkedin_url)
    email = email.strip().lower()
    now = datetime.now(timezone.utc).isoformat()
    new_sources = [{"url": u, "what": (evidence or [""])[0][:200], "at": now} for u in (source_urls or [])[:3]] or \
        [{"url": None, "what": (evidence or [source])[0][:200], "at": now}]

    def work(conn):
        existing = None
        if slug:
            existing = conn.execute(f"select {_COLUMNS} from public.contact where user_id = %s::uuid and linkedin_slug = %s "
                                    "for update", [user_id, slug]).fetchone()
        if existing is None and email:
            existing = conn.execute(f"select {_COLUMNS} from public.contact where user_id = %s::uuid and lower(email) = %s "
                                    "order by legacy, created_at limit 1 for update", [user_id, email]).fetchone()
        if existing is None and name:
            for row in conn.execute(f"select {_COLUMNS} from public.contact where user_id = %s::uuid and lower(name) = %s "
                                    "for update", [user_id, " ".join(name.lower().split())]).fetchall():
                if same_company(row[1], company) and (not slug or not row[FIELDS.index("linkedin_url") + 1]):
                    existing = row
                    break
        if existing is None:
            row = conn.execute(f"""insert into public.contact (user_id, company, name, title, linkedin_url, email, x_handle,
                                     github, role_class, stage, source, confidence, email_source, sources, dedupe_key)
                                   values (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                   on conflict (user_id, dedupe_key) do nothing returning {_COLUMNS}""",
                               [user_id, company, name, title, linkedin_url, email, x_handle, github, role_class, stage,
                                source, confidence, email_source if email else "", Jsonb(new_sources),
                                dedupe_key(company, name, linkedin_url, email)]).fetchone()
            if row is not None:
                return {**_row(row), "created": True}
            # Lost a race with another run, on the dedupe key or the LinkedIn profile.
            existing = conn.execute(f"select {_COLUMNS} from public.contact where user_id = %s::uuid and (dedupe_key = %s "
                                    "or (linkedin_slug is not null and linkedin_slug = %s)) limit 1 for update",
                                    [user_id, dedupe_key(company, name, linkedin_url, email), slug]).fetchone()
        current = _row(existing)
        mine = current["source"] == "you"
        update = {}
        for key, value in (("company", company), ("name", name), ("linkedin_url", linkedin_url), ("x_handle", x_handle),
                           ("github", github)):
            if value and not current[key]:
                update[key] = value
        if title and (not current["title"] or (not mine and not current["legacy"] and confidence and
                                               confidence > (current["confidence"] or 0))):
            update["title"] = title
        if role_class != "unknown" and (current["role_class"] == "unknown" or "title" in update):
            update["role_class"] = role_class
        if email and current["email_source"] != "you" and (not current["email"] or email_source in ("hunter", "you")):
            update["email"], update["email_source"] = email, email_source
        if confidence is not None and confidence > (current["confidence"] or 0):
            update["confidence"] = confidence
        if current["stage"] in ("unknown", "discovered") and not current["legacy"] and role_class != "unknown":
            update["stage"] = "classified"
        known = {(s.get("url"), s.get("what")) for s in current["sources"] or []}
        merged = list(current["sources"] or []) + [s for s in new_sources if (s["url"], s["what"]) not in known]
        if len(merged) != len(current["sources"] or []):
            update["sources"] = Jsonb(merged[-MAX_SOURCES:])
        if update:
            sets = ", ".join(f"{k} = %s" for k in update)
            existing = conn.execute(f"update public.contact set {sets} where id = %s::uuid returning {_COLUMNS}",
                                    [*update.values(), current["id"]]).fetchone()
        return {**_row(existing), "created": False}

    return get_db(user_id).run(work)


def at_company(user_id: str, company: str) -> list[dict]:
    """Everyone stored for this company (your imported connections included)."""
    core = core_company(company)
    if not core:
        return []
    first = core.split()[0]
    rows = get_db(user_id).fetch(f"select {_COLUMNS} from public.contact where user_id = %s::uuid "
                                 "and lower(company) like %s", [user_id, f"%{first}%"])
    return [_row(r) for r in rows if same_company(r[1], company)]


def connected(contact: dict) -> bool:
    """In your LinkedIn connections (imported from JobPilot's LinkedIn export)."""
    return contact.get("source") == "jobpilot:linkedin"


def last_touches(user_id: str, contact_ids: list[str]) -> dict[str, datetime]:
    if not contact_ids:
        return {}
    rows = get_db(user_id).fetch("""
        select id, max(at) from (
          select contact_id::text id, sent_at at from public.contact_touch where user_id = %s::uuid
            and contact_id::text = any(%s) and sent_at is not null
          union all
          select payload->>'contact_id', executing_at from public.action where user_id = %s::uuid
            and payload->>'contact_id' = any(%s) and executing_at is not null) t group by id""",
        [user_id, contact_ids, user_id, contact_ids])
    return {r[0]: r[1] for r in rows if r[1]}


def contact_blocker(contact: dict, last_touch: datetime | None, cooldown_days: int, now: datetime | None = None) -> str:
    """Why this person shouldn't be contacted now ('' when they can be)."""
    now = now or datetime.now(timezone.utc)
    if contact.get("do_not_contact"):
        return "Marked do not contact."
    if last_touch and now - last_touch < timedelta(days=cooldown_days):
        return f"Contacted on {last_touch:%d %b}; cooldown is {cooldown_days} days."
    return ""


# --- CRM reads and edits (API) -------------------------------------------------------------------

def list_contacts(user_id: str, *, company: str = "", role_class: str = "", q: str = "", include_imported: bool = False,
                  limit: int = 100, offset: int = 0) -> list[dict]:
    where, args = ["user_id = %s::uuid"], [user_id]
    if not include_imported:
        where.append("not legacy")
    if role_class:
        where.append("role_class = %s")
        args.append(role_class)
    if company:
        where.append("lower(company) like %s")
        args.append(f"%{core_company(company).split()[0] if core_company(company) else company.lower()}%")
    if q:
        where.append("(name ilike %s or title ilike %s or company ilike %s or email ilike %s)")
        args += [f"%{q}%"] * 4
    rows = get_db(user_id).fetch(f"select {_COLUMNS} from public.contact where {' and '.join(where)} "
                                 "order by updated_at desc limit %s offset %s", [*args, min(limit, 500), offset])
    out = [_row(r) for r in rows]
    return [c for c in out if same_company(c["company"], company)] if company else out


def get_contact(user_id: str, contact_id: str) -> dict | None:
    db = get_db(user_id)
    rows = db.fetch(f"select {_COLUMNS} from public.contact where user_id = %s::uuid and id = %s::uuid", [user_id, contact_id])
    if not rows:
        return None
    contact = _row(rows[0])
    touches = db.fetch("""select t.channel, t.sent_at, t.outcome, t.case_id::text, t.action_id::text
                          from public.contact_touch t where t.user_id = %s::uuid and t.contact_id = %s::uuid
                          order by t.sent_at desc nulls last limit 50""", [user_id, contact_id])
    contact["touches"] = [dict(zip(("channel", "sent_at", "outcome", "case_id", "action_id"), t)) for t in touches]
    actions = db.fetch("""select id::text, kind, status, case_id::text, created_at, executing_at from public.action
                          where user_id = %s::uuid and payload->>'contact_id' = %s order by created_at desc limit 50""",
                       [user_id, contact_id])
    contact["actions"] = [dict(zip(("id", "kind", "status", "case_id", "created_at", "executing_at"), a)) for a in actions]
    cases = db.fetch("""select distinct a.case_id::text, c.company, c.role from public.artifact a
                        join public.job_case c on c.id = a.case_id
                        where a.user_id = %s::uuid and a.kind = 'contact_list' and not a.legacy
                          and a.content->'people' @> %s""", [user_id, Jsonb([{"contact_id": contact_id}])])
    contact["cases"] = [dict(zip(("case_id", "company", "role"), c)) for c in cases]
    return contact


def update_contact(user_id: str, contact_id: str, changes: dict) -> dict | None:
    """Your edits. They mark the contact (or its email) as yours, so Recon won't overwrite them."""
    changes = {k: v for k, v in changes.items() if k in EDITABLE and v is not None}
    if "linkedin_url" in changes:
        changes["linkedin_url"] = canonical_linkedin(changes["linkedin_url"]) or ""
    if "email" in changes:
        changes["email"] = changes["email"].strip().lower()
        changes["email_source"] = "you" if changes["email"] else ""
    if any(k in changes for k in ("name", "title", "role_class", "company")):
        changes["source"] = "you"
    if not changes:
        return get_contact(user_id, contact_id)
    sets = ", ".join(f"{k} = %s" for k in changes)
    rows = get_db(user_id).fetch(f"update public.contact set {sets} where user_id = %s::uuid and id = %s::uuid returning id",
                                 [*changes.values(), user_id, contact_id])
    return get_contact(user_id, contact_id) if rows else None


def delete_contact(user_id: str, contact_id: str) -> bool:
    rows = get_db(user_id).fetch("delete from public.contact where user_id = %s::uuid and id = %s::uuid returning id",
                                 [user_id, contact_id])
    return bool(rows)
