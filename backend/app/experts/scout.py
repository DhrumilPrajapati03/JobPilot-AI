"""Scout: finds fresh jobs daily and scores them (plan section 2.1, wave 1).

Runs from its daily routine (with catch-up-on-wake) or on request. It reuses the board scan
and the deterministic scorer, then opens a case for each strong, eligible new match, at most
SCOUT_MAX_NEW_CASES per run so a big board can't flood the pipeline. Each new case wakes
Supervisor. Postings already seen (including everything imported from JobPilot) never open
a case twice: job_case is unique per posting.
"""
from __future__ import annotations

import asyncio

from psycopg.types.json import Jsonb

from app.db import get_db
from app.services.discovery import load_preferences

SCOUT_MAX_NEW_CASES = 5
RECENT_DAYS = 3


def candidates(user_id: str, min_score: float, limit: int) -> list[dict]:
    rows = get_db(user_id).fetch("""
        select to_jsonb(p) from (
          select p.id, p.company, p.title, p.url, p.description, p.fit_score, p.location, p.remote
          from public.job_postings p
          where p.user_id = %s::uuid and p.status = 'new' and p.closed_at is null and p.fit_score >= %s
            and coalesce(jsonb_array_length(p.skip_flags), 0) = 0
            and p.discovered_at >= now() - make_interval(days => %s)
            and not exists (select 1 from public.job_case c where c.user_id = p.user_id and c.posting_id = p.id)
          order by p.fit_score desc, p.discovered_at desc limit %s) p""", [user_id, min_score, RECENT_DAYS, limit])
    return [r[0] for r in rows]


def open_case_for_posting(user_id: str, posting: dict) -> dict | None:
    """Open a case for a posting; returns None when one already exists."""
    def work(conn):
        row = conn.execute("""insert into public.job_case (user_id, posting_id, source_url, company, role, jd_text, fit_score)
                              values (%s::uuid, %s::uuid, %s, %s, %s, %s, %s)
                              on conflict (user_id, posting_id) where posting_id is not null do nothing
                              returning id""",
                           [user_id, posting["id"], posting.get("url") or "", posting.get("company") or "",
                            posting.get("title") or "", posting.get("description") or "", posting.get("fit_score")]).fetchone()
        if row is None:
            return None
        conn.execute("""insert into public.case_event (case_id, user_id, kind, actor, actor_name, summary, data)
                        values (%s, %s::uuid, 'created', 'agent', 'scout', %s, %s)""",
                     [row[0], user_id, f"Scout found {posting.get('title') or 'a role'} at {posting.get('company') or 'a company'} "
                      f"(fit {round(float(posting.get('fit_score') or 0))})", Jsonb({"posting_id": posting["id"]})])
        return {"case_id": str(row[0]), "company": posting.get("company"), "role": posting.get("title")}
    return get_db(user_id).run(work)


async def run(ctx) -> dict:
    from app.experts.runtime import enqueue_expert
    summary = await ctx.tools.call("scan_job_boards", "Scanning the boards you follow")
    prefs = await asyncio.to_thread(load_preferences, ctx.db, ctx.user_id)
    threshold = max(prefs.min_match_score, prefs.auto_draft_min_score)
    found = await asyncio.to_thread(candidates, ctx.user_id, threshold, SCOUT_MAX_NEW_CASES)
    opened = []
    for posting in found:
        case = await ctx.tools.call("open_case", f"Opened a case: {posting.get('title')} at {posting.get('company')}",
                                    posting=posting)
        if case:
            opened.append(case)
            await asyncio.to_thread(enqueue_expert, ctx.user_id, "supervisor", case_id=case["case_id"],
                                    key=f"supervisor:{case['case_id']}:created", trigger="case_created")
    new = (summary or {}).get("new", 0) if isinstance(summary, dict) else 0
    words = (f"Found {new} new posting{'s' if new != 1 else ''}; opened {len(opened)} case{'s' if len(opened) != 1 else ''}"
             if new or opened else "No new postings")
    await ctx.log.add("note", "summary", words, {"threshold": threshold, "opened": opened,
                                                  "scan": {k: v for k, v in (summary or {}).items() if isinstance(v, (int, str))}})
    return {"new": new, "opened": opened, "threshold": threshold}
