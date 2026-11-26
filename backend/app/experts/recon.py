"""Recon: the people at the company for one case (plan sections 2.1 and 2.4; Day 6).

Read-only and deterministic (no model calls):

1. **Who you already know there:** your imported LinkedIn connections at the company are
   referral candidates.
2. **Public LinkedIn results** through Brave Search with a LinkedIn-only Goggle: a few
   searches (recruiters, engineering leaders, founders, peers in the role), capped per run
   and per day by policy.yaml. A result counts only with evidence that the person works at
   the company now (app.recon.people). LinkedIn pages are never opened.
3. **Emails, never guessed:** addresses printed in the job description, and Hunter-verified
   ones when HUNTER_API_KEY is set.
4. **GitHub/X handles** from public GitHub profiles that name the company.
5. Everyone is merged into your contacts (dedupe by LinkedIn profile, email, name+company),
   checked against the cooldown and do-not-contact, and the first few in outreach order are
   marked `suggested` within `max_people_per_company`.

When the case has no recipient yet and Recon found a usable address (recruiter first), it
sets it, so Email Outreach drafts to that person. Nothing is sent: drafts still wait for
your approval.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.core import cases, contacts
from app.core.policy import load_policy
from app.db import get_db
from app.experts import artifacts
from app.recon import emails as email_mod
from app.recon import people as people_mod
from app.services import brave
from app.services.runs import PermanentRunError

OUTREACH_ORDER = ("recruiter", "hiring_manager", "referral", "cto", "ceo", "employee")
MAX_HUNTER = 2
MAX_HANDLES = 2
MAX_CONNECTIONS = 5
ROLE_WORDS = {"recruiter": "recruiter", "hiring_manager": "hiring manager", "ceo": "founder/CEO", "cto": "CTO",
              "employee": "peer"}


def searches_today(user_id: str, policy) -> int:
    rows = get_db(user_id).fetch("""select count(*) from public.run_step where user_id = %s::uuid and agent = 'recon'
                                    and kind = 'tool' and name = 'search_people' and at >= %s""",
                                 [user_id, policy.day_start(datetime.now(timezone.utc))])
    return rows[0][0]


def people_reached(user_id: str, company: str) -> set[str]:
    """Contacts at this company something was already sent to (counts toward max_people_per_company)."""
    rows = get_db(user_id).fetch("""select distinct payload->>'contact_id', payload->>'company' from public.action
                                    where user_id = %s::uuid and executing_at is not null and payload->>'contact_id' is not null""",
                                 [user_id])
    return {r[0] for r in rows if people_mod.same_company(r[1] or "", company)}


def channel_for(entry: dict) -> str:
    if entry["connected"] and entry["role_class"] == "employee":
        return "referral"
    return "email" if entry["email"] else "linkedin"


def order_key(entry: dict) -> tuple:
    group = "referral" if entry["channel"] == "referral" else entry["role_class"]
    rank = OUTREACH_ORDER.index(group) if group in OUTREACH_ORDER else len(OUTREACH_ORDER)
    return (rank, -(entry.get("confidence") or 0))


def suggest(entries: list[dict], slots: int) -> None:
    """Mark the first `slots` contactable people in outreach order, one per role group first."""
    ranked = sorted(entries, key=order_key)
    picked, groups = [], set()
    for entry in ranked:                       # first pass: one per group
        group = "referral" if entry["channel"] == "referral" else entry["role_class"]
        if len(picked) < slots and not entry["blocked"] and group not in groups and entry.get("name"):
            picked.append(entry)
            groups.add(group)
    for entry in ranked:                       # then fill the remaining slots
        if len(picked) < slots and not entry["blocked"] and all(entry is not p for p in picked) and entry.get("name"):
            picked.append(entry)
    for entry in entries:
        entry["suggested"] = any(entry is p for p in picked)


def pick_recipient(entries: list[dict]) -> dict | None:
    """Who Email Outreach should write to: a suggested recruiter/leader with a real address,
    else a hiring mailbox from the job description."""
    for entry in sorted(entries, key=order_key):
        if entry["email"] and not entry["blocked"] and entry["role_class"] in ("recruiter", "hiring_manager", "cto", "ceo") \
                and entry["email_source"] in ("job_description", "hunter", "you", "imported"):
            return entry
    return None


async def run(ctx) -> dict:
    if not ctx.case_id:
        raise PermanentRunError("Recon needs a case.")
    case = await ctx.tools.call("read_case", "Reading the case", case_id=ctx.case_id)
    if case is None:
        raise PermanentRunError("The case was removed.")
    company, role = (case.get("company") or "").strip(), (case.get("role") or "").strip()
    if not company:
        raise PermanentRunError("The case has no company name; set it before looking for people.")
    policy = load_policy()
    notes: list[str] = []

    # 1. People you already know there.
    known = await asyncio.to_thread(contacts.at_company, ctx.user_id, company)
    connections = [c for c in known if contacts.connected(c) and c["name"]
                   and (c["role_class"] in ("recruiter", "cto", "ceo") or people_mod.technical(c["title"]))]
    connections.sort(key=lambda c: people_mod.PRIORITY.get(c["role_class"], 9))
    connections = connections[:MAX_CONNECTIONS]

    # 2. Public LinkedIn results.
    found: list[people_mod.Person] = []
    searches = 0
    if not brave.configured():
        notes.append("Search isn't configured (BRAVE_API_KEY), so only your connections and the job description were used.")
    else:
        left_today = policy.caps["recon_searches_per_day"] - await asyncio.to_thread(searches_today, ctx.user_id, policy)
        budget = max(0, min(policy.caps["recon_searches_per_run"], left_today))
        if budget == 0:
            notes.append(f"Today's search cap is used up (recon_searches_per_day = {policy.caps['recon_searches_per_day']}).")
        for query in people_mod.queries(company, role)[:budget]:
            try:
                result = await ctx.tools.call("search_people", f"Searching LinkedIn for {ROLE_WORDS[query.role_class]}s at {company}",
                                              company=company, query=query.text, role_class=query.role_class)
            except brave.SearchError as exc:
                notes.append(str(exc))
                break
            searches += 1
            found += [people_mod.Person(**p) for p in result["people"]]
    people = people_mod.shortlist([p for p in people_mod.merge(found) if people_mod.relevant(p)])

    # 3. Emails from the job description; Hunter when configured.
    jd_emails = email_mod.in_text(case.get("jd_text") or "")
    by_slug_email: dict[str, tuple[str, str]] = {}
    for found_email in jd_emails:
        if found_email.kind == "person":
            for p in people:
                if email_mod.name_matches(found_email.email.split("@")[0], p.name):
                    by_slug_email[p.slug] = (found_email.email, "job_description")
    brief = await asyncio.to_thread(artifacts.latest, ctx.user_id, ctx.case_id, "company_brief")
    urls = [case.get("source_url") or ""] + [s.get("url") or "" for s in ((brief or {}).get("content") or {}).get("sources", [])]
    domain = email_mod.company_domain(company, emails=jd_emails, urls=urls)
    if email_mod.hunter_configured() and domain:
        tries = 0
        for p in people:
            if tries >= MAX_HUNTER:
                break
            if p.role_class in ("recruiter", "hiring_manager") and p.slug not in by_slug_email:
                tries += 1
                result = await ctx.tools.call("find_work_email", f"Checking Hunter for {p.name}'s work email",
                                              domain=domain, name=p.name)
                if result.get("email"):
                    by_slug_email[p.slug] = (result["email"], "hunter")
    elif email_mod.hunter_configured():
        notes.append("Couldn't tell the company's email domain from the job description or the brief, so Hunter wasn't used.")

    # 4. GitHub/X handles for a couple of technical people.
    handles: dict[str, dict] = {}
    from app.recon.handles import RateLimited
    for p in [p for p in people if p.role_class in ("hiring_manager", "cto", "employee")][:MAX_HANDLES]:
        try:
            result = await ctx.tools.call("lookup_handles", f"Looking for {p.name} on GitHub", name=p.name, company=company)
        except RateLimited:
            notes.append("GitHub asked to wait, so handle lookups stopped early.")
            break
        if result:
            handles[p.slug] = result

    # 5. Save everyone into contacts, then rank.
    entries: list[dict] = []
    for p in people:
        email, email_source = by_slug_email.get(p.slug, ("", ""))
        h = handles.get(p.slug) or {}
        saved = await ctx.tools.call("save_contact", f"Saved {p.name} ({ROLE_WORDS[p.role_class]})",
                                     company=company, name=p.name, title=p.title, role_class=p.role_class,
                                     linkedin_url=p.linkedin_url, email=email, email_source=email_source,
                                     github=h.get("github", ""), x_handle=h.get("x_handle", ""), confidence=p.confidence,
                                     evidence=p.evidence + ([h["evidence"]] if h.get("evidence") else []), source_urls=p.sources)
        entries.append({"contact_id": saved["id"], "name": p.name, "title": p.title, "role_class": p.role_class,
                        "linkedin_url": p.linkedin_url, "email": email, "email_source": email_source,
                        "github": h.get("github", ""), "x_handle": h.get("x_handle", ""), "confidence": p.confidence,
                        "evidence": (p.evidence + ([h["evidence"]] if h.get("evidence") else []))[:4]})
    seen = {e["contact_id"] for e in entries}
    for c in connections:
        if c["id"] not in seen:
            entries.append({"contact_id": c["id"], "name": c["name"], "title": c["title"], "role_class": c["role_class"],
                            "linkedin_url": c["linkedin_url"] or None, "email": c["email"], "email_source": c["email_source"],
                            "github": c["github"], "x_handle": c["x_handle"], "confidence": 0.95,
                            "evidence": ["In your LinkedIn connections"]})
    for found_email in jd_emails:
        if not any(e["email"] == found_email.email for e in entries):     # not already someone's address
            saved = await ctx.tools.call("save_contact", f"Saved {found_email.email} from the job description",
                                         company=company, name="", title="Hiring mailbox" if found_email.kind == "team" else "Address in the job description",
                                         role_class="recruiter", email=found_email.email, email_source="job_description",
                                         evidence=["Printed in the job description"], source="recon")
            entries.append({"contact_id": saved["id"], "name": "", "title": "Hiring mailbox" if found_email.kind == "team" else "Address in the job description",
                            "role_class": "recruiter", "linkedin_url": None, "email": found_email.email,
                            "email_source": "job_description", "github": "", "x_handle": "", "confidence": 0.9,
                            "evidence": ["Printed in the job description"]})
    connected_ids = {c["id"] for c in known if contacts.connected(c)}
    rows = {c["id"]: c for c in await asyncio.to_thread(contacts.at_company, ctx.user_id, company)}
    touches = await asyncio.to_thread(contacts.last_touches, ctx.user_id, [e["contact_id"] for e in entries])
    cooldown = policy.caps["no_contact_if_touched_within_days"]
    for e in entries:
        e["connected"] = e["contact_id"] in connected_ids
        row = rows.get(e["contact_id"]) or {}
        if row.get("email") and not e["email"]:          # an address you added earlier
            e["email"], e["email_source"] = row["email"], row.get("email_source") or ""
        touch = touches.get(e["contact_id"])
        e["last_touch_at"] = touch.isoformat() if touch else None
        e["blocked"] = contacts.contact_blocker(row or e, touch, cooldown)
        e["channel"] = channel_for(e)
    reached = await asyncio.to_thread(people_reached, ctx.user_id, company)
    slots = max(0, policy.caps["max_people_per_company"] - len(reached))
    if reached:
        notes.append(f"Already reached {len(reached)} at {company}; {slots} more allowed (max_people_per_company).")
    suggest(entries, slots)
    entries.sort(key=lambda e: (not e["suggested"], order_key(e)))

    card = artifacts.ContactList(company=company, people=entries[:30], searches=searches, notes=notes[:10])
    saved = await ctx.tools.call("save_artifact", "Saved the contact list", kind="contact_list",
                                 content=card.model_dump(mode="json"), title=f"People at {company}")
    counts = {}
    for e in entries:
        counts[e["role_class"]] = counts.get(e["role_class"], 0) + 1
    parts = [f"{n} {ROLE_WORDS.get(r, r)}{'s' if n > 1 else ''}" for r, n in counts.items()]
    summary = (f"Recon found {len(entries)} {'person' if len(entries) == 1 else 'people'} at {company}"
               + (f" ({', '.join(parts)})" if parts else "")
               + (f"; {len([e for e in entries if e['connected']])} in your connections" if any(e["connected"] for e in entries) else "")
               if entries else f"Recon found nobody at {company} it could confirm")
    await asyncio.to_thread(cases.add_event, ctx.user_id, ctx.case_id, "artifact", actor="agent", actor_name="recon",
                            summary=summary, data={"artifact_id": saved["id"], "kind": "contact_list"})

    # Hand Email Outreach a recipient when none is set.
    from app.experts import email_outreach
    chosen = None
    if await asyncio.to_thread(email_outreach.recipient, ctx.user_id, ctx.case_id) is None:
        chosen = pick_recipient([e for e in entries if e["suggested"] or not e["name"]])
        if chosen:
            await asyncio.to_thread(email_outreach.set_recipient, ctx.user_id, ctx.case_id, chosen["email"], chosen["name"],
                                    company, contact_id=chosen["contact_id"], actor="agent", actor_name="recon")
    return {"artifact_id": saved["id"], "people": len(entries), "searches": searches,
            "suggested": [e["contact_id"] for e in entries if e["suggested"]], "recipient": chosen["email"] if chosen else None}
