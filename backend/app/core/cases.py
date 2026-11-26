"""Job cases: the spine of JobDots (plan section 5). One case per role being pursued;
every expert posts into its timeline (case_event)."""
from __future__ import annotations

from psycopg.types.json import Jsonb

from app.db import get_db

# Research feeds tailoring, so Researched comes before Tailored (the plan's board listed them the other way).
STAGES = ("found", "researched", "tailored", "ready", "applied", "replied", "interview", "offer", "closed")
ACTORS = ("agent", "user", "courier", "system", "legacy")
_CASE = ("id, user_id, posting_id, source_url, company, role, jd_text, jd_analysis, stage, status, fit_score, "
         "fit_score_legacy, notes, applied_at, follow_up_at, legacy, created_at, updated_at")


def _rows(conn, query, params):
    return [r[0] for r in conn.execute(f"with x as ({query}) select to_jsonb(x) from x", params).fetchall()]


def create_case(user_id: str, *, company: str = "", role: str = "", source_url: str = "", jd_text: str = "",
                actor: str = "user", actor_name: str = "") -> dict:
    def work(conn):
        case = _rows(conn, f"""insert into public.job_case (user_id, company, role, source_url, jd_text)
                               values (%s::uuid, %s, %s, %s, %s) returning {_CASE}""",
                     [user_id, company, role, source_url, jd_text])[0]
        conn.execute("""insert into public.case_event (case_id, user_id, kind, actor, actor_name, summary)
                        values (%s::uuid, %s::uuid, 'created', %s, %s, 'Case opened')""",
                     [case["id"], user_id, actor, actor_name])
        return case
    return get_db(user_id).run(work)


def add_event(user_id: str, case_id: str, kind: str, *, actor: str, summary: str = "", data: dict | None = None,
              actor_name: str = "") -> dict:
    if actor not in ACTORS:
        raise ValueError(f"unknown actor {actor!r}")

    def work(conn):
        if not conn.execute("select 1 from public.job_case where id = %s::uuid and user_id = %s::uuid",
                            [case_id, user_id]).fetchone():
            raise LookupError("case_not_found")
        return _rows(conn, """insert into public.case_event (case_id, user_id, kind, actor, actor_name, summary, data)
                              values (%s::uuid, %s::uuid, %s, %s, %s, %s, %s) returning *""",
                     [case_id, user_id, kind, actor, actor_name, summary, Jsonb(data or {})])[0]
    return get_db(user_id).run(work)


def set_stage(user_id: str, case_id: str, stage: str, *, actor: str = "user", actor_name: str = "") -> dict:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}")

    def work(conn):
        before = conn.execute("select stage from public.job_case where id = %s::uuid and user_id = %s::uuid for update",
                              [case_id, user_id]).fetchone()
        if not before:
            raise LookupError("case_not_found")
        early = STAGES.index(stage) < STAGES.index("applied")      # moving back before applied clears the date
        case = _rows(conn, f"""update public.job_case set stage = %s,
                                   status = case when %s = 'closed' then 'closed' else status end,
                                   applied_at = case when %s = 'applied' then coalesce(applied_at, now())
                                                     when %s then null else applied_at end
                               where id = %s::uuid returning {_CASE}""", [stage, stage, stage, early, case_id])[0]
        if before[0] != stage:
            conn.execute("""insert into public.case_event (case_id, user_id, kind, actor, actor_name, summary, data)
                            values (%s::uuid, %s::uuid, 'stage_changed', %s, %s, %s, %s)""",
                         [case_id, user_id, actor, actor_name, f"{before[0]} -> {stage}",
                          Jsonb({"from": before[0], "to": stage})])
        return case
    return get_db(user_id).run(work)


def list_cases(user_id: str, *, stage: str | None = None, limit: int = 200) -> list[dict]:
    return get_db(user_id).run(lambda conn: _rows(conn, f"""select {_CASE} from public.job_case
        where user_id = %s::uuid and (%s::text is null or stage = %s) order by updated_at desc limit %s""",
        [user_id, stage, stage, limit]))


def get_case(user_id: str, case_id: str) -> dict | None:
    def work(conn):
        found = _rows(conn, f"select {_CASE} from public.job_case where id = %s::uuid and user_id = %s::uuid",
                      [case_id, user_id])
        if not found:
            return None
        case = found[0]
        case["events"] = _rows(conn, "select * from public.case_event where case_id = %s::uuid order by at, id", [case_id])
        case["artifacts"] = _rows(conn, """select id, kind, version, title, content, file_path, file_sha256, created_by,
                                           legacy, created_at from public.artifact where case_id = %s::uuid
                                           order by created_at""", [case_id])
        case["actions"] = _rows(conn, """select id, kind, mode, agent, status, payload, payload_sha256, revision, review,
                                         block_reason, created_at, updated_at from public.action
                                         where case_id = %s::uuid order by created_at""", [case_id])
        return case
    return get_db(user_id).run(work)
