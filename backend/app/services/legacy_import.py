"""Import the JobPilot export into JobDots (plan section 5.1). Nothing is lost:

* Every source row is copied to `legacy_import.raw` (with its sha256), even where the new
  schema has no column for a field.
* Idempotent: targets keep the legacy row's id (or a key derived from it) and
  `legacy_import` is unique on (source_table, legacy_id, target_table); a rerun inserts nothing.
* Dry run is the default: everything runs in one transaction that is rolled back.
* Imported drafts (cold emails, cover letters, DMs, referral asks) become `artifact(draft)`
  rows marked legacy. They never become `action` rows, so nothing old can be approved or
  sent; an agent has to propose it again under the current policy.

The export folder is read-only input (manifest.json + one JSONL file per table); its
sha256s are checked before anything is read.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from psycopg.types.json import Jsonb

# Legacy status -> (stage, status) on job_case.
STAGE = {"saved": ("found", "open"), "applied": ("applied", "open"), "interviewing": ("interview", "open"),
         "offer": ("offer", "open"), "rejected": ("closed", "closed"), "archived": ("closed", "closed")}
# Tables copied into tables that keep the legacy shape (Scout's "already seen" set, the
# board list, the base resume and the profile).
SKIPPED = {"autopilot_state": "runtime scheduler state; rebuilt by the worker",
           "extension_tokens": "credentials are never copied; reconnect the extension"}
_NS = uuid.UUID("5d1f6a3e-0c1b-4b7e-9a51-6a0d1c2e7b10")  # derives stable ids for split rows


class ImportError_(RuntimeError):
    pass


def derived_id(*parts: str) -> str:
    return str(uuid.uuid5(_NS, ":".join(parts)))


def canonical(row: dict) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def classify_role(title: str) -> str:
    """First-pass role_class from a job title (rules; a local model can refine it later)."""
    t = f" {(title or '').lower()} "
    if re.search(r"recruit|talent|\bhr\b|human resources|people (partner|ops|operations)|sourcer", t):
        return "recruiter"
    if re.search(r"\bceo\b|chief executive|founder", t):
        return "ceo"
    if re.search(r"\bcto\b|chief technology", t):
        return "cto"
    if re.search(r"engineering manager|head of|director|\bvp\b|vice president|hiring manager", t):
        return "hiring_manager"
    if t.strip():
        return "employee"
    return "unknown"


@dataclass
class Report:
    dry_run: bool
    source_counts: dict[str, int] = field(default_factory=dict)
    imported: Counter = field(default_factory=Counter)       # (source_table -> target_table) rows linked
    inserted: Counter = field(default_factory=Counter)       # target rows newly written this run
    skipped: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"dry_run": self.dry_run, "source_counts": self.source_counts,
                "imported": {f"{s} -> {t}": n for (s, t), n in sorted(self.imported.items())},
                "inserted_this_run": {f"{s} -> {t}": n for (s, t), n in sorted(self.inserted.items())},
                "skipped": self.skipped, "notes": self.notes}


def load_export(folder: Path) -> tuple[dict, dict[str, list[dict]]]:
    """Read the manifest and every table file, refusing files whose sha256 doesn't match."""
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    tables: dict[str, list[dict]] = {}
    for name, meta in manifest["tables"].items():
        data = (folder / meta["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != meta["sha256"]:
            raise ImportError_(f"{meta['file']} does not match its sha256 in manifest.json; the archive changed.")
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
        if len(rows) != meta["rows"]:
            raise ImportError_(f"{meta['file']} has {len(rows)} rows; the manifest says {meta['rows']}.")
        tables[name] = rows
    return manifest, tables


class Importer:
    def __init__(self, conn, owner_id: str, report: Report, embed=None):
        self.conn, self.owner, self.report, self.embed = conn, owner_id, report, embed
        self._columns: dict[str, set[str]] = {}

    # -- helpers -----------------------------------------------------------------------------
    def columns(self, table: str) -> set[str]:
        if table not in self._columns:
            rows = self.conn.execute("""select column_name from information_schema.columns
                                        where table_schema = 'public' and table_name = %s""", [table]).fetchall()
            self._columns[table] = {r[0] for r in rows}
        return self._columns[table]

    def link(self, source: str, row: dict, target: str, target_id: str) -> None:
        raw = canonical(row)
        self.conn.execute("""insert into public.legacy_import (source_table, legacy_id, target_table, target_id, raw, raw_sha256)
                             values (%s, %s, %s, %s, %s, %s) on conflict (source_table, legacy_id, target_table) do nothing""",
                          [source, str(row.get("id") or row.get("user_id")), target, target_id, Jsonb(row),
                           hashlib.sha256(raw.encode()).hexdigest()])
        self.report.imported[(source, target)] += 1

    def insert(self, source: str, table: str, values: dict, conflict: str = "(id)") -> bool:
        # Missing values fall back to column defaults (created_at = now(), nullable columns = null).
        cols = [c for c in values if c in self.columns(table) and values[c] is not None]
        params = [Jsonb(values[c]) if isinstance(values[c], (dict, list)) else values[c] for c in cols]
        placeholders = ", ".join(["%s"] * len(cols))
        row = self.conn.execute(f"insert into public.{table} ({', '.join(cols)}) values ({placeholders}) "
                                f"on conflict {conflict} do nothing returning 1", params).fetchone()
        if row:
            self.report.inserted[(source, table)] += 1
        return bool(row)

    def event(self, source: str, case_id: str, key: str, kind: str, at, summary: str, data: dict | None = None) -> None:
        """Timeline rows have identity ids, so idempotency comes from data.legacy_key."""
        exists = self.conn.execute("select 1 from public.case_event where case_id = %s and data->>'legacy_key' = %s",
                                   [case_id, key]).fetchone()
        if exists:
            return
        self.conn.execute("""insert into public.case_event (case_id, user_id, kind, actor, actor_name, summary, data, at)
                             values (%s, %s, %s, 'legacy', 'JobPilot', %s, %s, coalesce(%s::timestamptz, now()))""",
                          [case_id, self.owner, kind, summary, Jsonb({**(data or {}), "legacy_key": key}), at])
        self.report.inserted[(source, "case_event")] += 1

    def artifact(self, source: str, row: dict, art_id: str, case_id: str | None, kind: str, title: str, content: dict,
                 created_at, version: int = 1) -> None:
        self.insert(source, "artifact", {"id": art_id, "user_id": self.owner, "case_id": case_id, "kind": kind,
                                         "version": version, "title": title, "content": content, "legacy": True,
                                         "created_by": "jobpilot", "created_at": created_at})
        self.link(source, row, "artifact", art_id)

    def case_exists(self, case_id: str | None) -> str | None:
        if not case_id:
            return None
        return case_id if self.conn.execute("select 1 from public.job_case where id = %s", [case_id]).fetchone() else None

    # -- tables ------------------------------------------------------------------------------
    def applications(self, rows: list[dict], scores: dict[str, float]) -> None:
        for a in rows:
            if a["status"] not in STAGE:
                raise ImportError_(f"Unknown application status {a['status']!r}; add it to STAGE first.")
            stage, status = STAGE[a["status"]]
            self.insert("job_applications", "job_case", {
                "id": a["id"], "user_id": self.owner, "source_url": a.get("jd_url") or "", "company": a.get("company") or "",
                "role": a.get("role") or "", "jd_text": a.get("jd_text") or "", "jd_analysis": a.get("jd_analysis"),
                "stage": stage, "status": status, "fit_score_legacy": scores.get(a["id"]), "notes": a.get("notes") or "",
                "applied_at": a.get("applied_at"), "follow_up_at": a.get("follow_up_at"), "legacy": True,
                "created_at": a["created_at"], "updated_at": a.get("updated_at") or a["created_at"]})
            self.link("job_applications", a, "job_case", a["id"])
            self.event("job_applications", a["id"], f"created:{a['id']}", "imported", a["created_at"],
                       f"Imported from JobPilot (status {a['status']})", {"legacy_status": a["status"], "source": a.get("source")})
            if a.get("applied_at"):
                self.event("job_applications", a["id"], f"applied:{a['id']}", "applied", a["applied_at"], "Applied (recorded in JobPilot)")
            if a.get("follow_up_at"):
                # A suggestion for Supervisor, never a scheduled send.
                self.event("job_applications", a["id"], f"follow_up:{a['id']}", "follow_up_suggested", a.get("updated_at"),
                           "Follow-up date carried over from JobPilot", {"follow_up_at": a["follow_up_at"]})
            for field_name, label, channel in (("cover_letter", "Cover letter", "cover_letter"),
                                               ("linkedin_dm", "LinkedIn message", "linkedin_dm")):
                value = a.get(field_name)
                if value:
                    self.derived_artifact(a, field_name, "draft", f"{label} (JobPilot)",
                                          {"channel": channel, "legacy": True, "value": value}, a["created_at"])
            if a.get("prepared_form"):
                self.derived_artifact(a, "prepared_form", "answer_set", "Prepared application form (JobPilot)",
                                      {"legacy": True, "form": a["prepared_form"]}, a.get("updated_at") or a["created_at"])

    def derived_artifact(self, a: dict, field_name: str, kind: str, title: str, content: dict, created_at) -> None:
        # Split out of an application row whose raw copy is already linked to its case.
        self.insert("job_applications", "artifact", {
            "id": derived_id("job_applications", a["id"], field_name), "user_id": self.owner, "case_id": a["id"],
            "kind": kind, "title": title, "content": content, "legacy": True, "created_by": "jobpilot", "created_at": created_at})

    def tailored(self, rows: list[dict]) -> None:
        for t in rows:
            content = {"resume": t.get("content") or {}, "keyword_match_score": t.get("keyword_match_score"),
                       "missing_keywords": t.get("missing_keywords") or [], "legacy": True}
            self.artifact("tailored_resumes", t, t["id"], self.case_exists(t.get("application_id")), "resume_version",
                          "Tailored resume (JobPilot)", content, t.get("generated_at"), int(t.get("version") or 1))
            if t.get("pdf_url"):
                self.report.notes.append(f"tailored_resumes {t['id']}: pdf_url kept in raw; the export holds no PDF file.")

    def cold_emails(self, rows: list[dict]) -> None:
        for e in rows:
            case_id = self.case_exists(e.get("application_id"))
            content = {"channel": "email", "legacy": True, **{k: e.get(k) for k in
                       ("sequence_number", "to_name", "to_email", "subject", "body", "sent_at", "opened", "opened_at", "replied", "replied_at")}}
            self.artifact("cold_emails", e, e["id"], case_id, "draft", f"Cold email {e.get('sequence_number') or ''} (JobPilot)".replace("  ", " "),
                          content, e.get("sent_at"))
            if case_id and e.get("sent_at"):
                self.event("cold_emails", case_id, f"email_sent:{e['id']}", "email_sent", e["sent_at"], "Cold email sent (JobPilot)")
            if case_id and e.get("replied"):
                self.event("cold_emails", case_id, f"email_replied:{e['id']}", "email_replied", e.get("replied_at"), "Reply received (JobPilot)")

    def contacts(self, rows: list[dict]) -> None:
        for c in rows:
            self.insert("network_contacts", "contact", {
                "id": c["id"], "user_id": self.owner, "company": c.get("company") or "",
                "name": c.get("full_name") or " ".join(p for p in (c.get("first_name"), c.get("last_name")) if p),
                "title": c.get("position") or "", "linkedin_url": c.get("linkedin_url") or "", "email": c.get("email") or "",
                "role_class": classify_role(c.get("position") or ""), "stage": "unknown",
                "source": f"jobpilot:{c.get('source') or 'import'}", "dedupe_key": f"legacy:{c['dedupe_key']}",
                "notes": c.get("notes") or "", "legacy": True, "created_at": c.get("created_at")}, conflict="")  # id or dedupe key
            self.link("network_contacts", c, "contact", c["id"])

    def referrals(self, rows: list[dict]) -> None:
        for r in rows:
            case_id = self.case_exists(r.get("application_id"))
            self.artifact("referral_requests", r, r["id"], case_id, "draft", "Referral ask (JobPilot)",
                          {"channel": "referral", "legacy": True, "contact_id": r.get("contact_id"), "message": r.get("message"),
                           "status": r.get("status"), "sent_at": r.get("sent_at")}, r.get("created_at"))
            if r.get("sent_at") and r.get("contact_id"):
                self.conn.execute("""insert into public.contact_touch (contact_id, user_id, case_id, channel, sent_at, outcome, legacy)
                                     select %s, %s, %s, 'referral', %s, 'sent (JobPilot)', true
                                     where exists (select 1 from public.contact where id = %s) and not exists
                                       (select 1 from public.contact_touch where contact_id = %s and channel = 'referral'
                                        and sent_at = %s and legacy)""",
                                  [r["contact_id"], self.owner, case_id, r["sent_at"], r["contact_id"], r["contact_id"], r["sent_at"]])
            if case_id:
                self.event("referral_requests", case_id, f"referral:{r['id']}", "referral_" + (r.get("status") or "drafted"),
                           r.get("sent_at") or r.get("created_at"), f"Referral ask {r.get('status') or 'drafted'} (JobPilot)",
                           {"contact_id": r.get("contact_id")})

    def answers(self, rows: list[dict]) -> None:
        for q in rows:
            question = q.get("question") or ""
            vector, model = None, None
            done = self.conn.execute("select 1 from public.answer_bank where id = %s and embedding is not null",
                                     [q["id"]]).fetchone()
            if self.embed and not done:
                try:
                    vector, model = self.embed(question)
                except Exception:
                    vector = None
            self.insert("qa_answers", "answer_bank", {
                "id": q["id"], "user_id": self.owner, "question_text": question,
                "normalized_question": re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", question.lower())).strip(),
                "answer": q.get("answer") or "", "type": q.get("category") or "text", "source": "legacy",
                "sensitive": bool(q.get("sensitive")), "approved_at": q.get("updated_at"), "created_at": q.get("created_at"),
                "embedding": None, "embedding_model": model})
            if vector is not None:
                self.conn.execute("update public.answer_bank set embedding = %s::vector, embedding_model = %s where id = %s and embedding is null",
                                  [str(vector), model, q["id"]])
            self.link("qa_answers", q, "answer_bank", q["id"])

    def sources_and_postings(self, sources: list[dict], postings: list[dict]) -> None:
        for s in sources:
            self.insert("job_sources", "job_sources", {**s, "user_id": self.owner}, conflict="")  # id or (ats, slug)
            self.link("job_sources", s, "job_sources", s["id"])
        for p in postings:
            # application_id pointed at JobPilot's job_applications, which become cases; keep it in raw.
            values = {**p, "user_id": self.owner, "application_id": None}
            if p.get("source_id") and not self.conn.execute("select 1 from public.job_sources where id = %s", [p["source_id"]]).fetchone():
                values["source_id"] = None
            self.insert("job_postings", "job_postings", values, conflict="")  # id or board identity
            self.link("job_postings", p, "job_postings", p["id"])

    def resume_and_profile(self, resumes: list[dict], profiles: list[dict], legacy_owner: str | None) -> None:
        for r in resumes:
            if self.conn.execute("select 1 from public.resumes where user_id = %s", [self.owner]).fetchone() and \
                    not self.conn.execute("select 1 from public.resumes where id = %s", [r["id"]]).fetchone():
                self.report.notes.append("resumes: you already have a base resume here; the JobPilot one is kept only in legacy_import.")
                self.link("resumes", r, "none", "")
                continue
            self.insert("resumes", "resumes", {**r, "user_id": self.owner})
            self.link("resumes", r, "resumes", r["id"])
        for p in profiles:
            if legacy_owner and p["id"] != legacy_owner:
                self.report.notes.append("user_profiles: a profile of another JobPilot account was kept only in legacy_import.")
                self.link("user_profiles", p, "none", "")
                continue
            self.conn.execute("insert into public.user_profiles (id) values (%s) on conflict (id) do nothing", [self.owner])
            # Fill only fields that are still empty here; never overwrite what was entered in JobDots.
            self.conn.execute("""update public.user_profiles set
                                   name = case when name = '' then %s else name end,
                                   headline = case when headline = '' then %s else headline end,
                                   location = case when location = '' then %s else location end,
                                   salary_range = case when salary_range = '' then %s else salary_range end,
                                   linkedin_url = case when linkedin_url = '' then %s else linkedin_url end,
                                   work_preferences = case when work_preferences = '{}'::jsonb then %s else work_preferences end
                                 where id = %s""",
                              [p.get("name") or "", p.get("headline") or "", p.get("location") or "", p.get("salary_range") or "",
                               p.get("linkedin_url") or "", Jsonb(p.get("work_preferences") or {}), self.owner])
            self.link("user_profiles", p, "user_profiles", self.owner)


def run_import(conn, folder: Path, owner_id: str, *, dry_run: bool = True, embed=None) -> Report:
    """Import inside the caller's open transaction. The caller commits or rolls back."""
    manifest, tables = load_export(folder)
    report = Report(dry_run=dry_run, source_counts={t: len(r) for t, r in tables.items()})
    owners = {r["user_id"] for r in tables.get("job_applications", []) if r.get("user_id")}
    if len(owners) > 1:
        raise ImportError_("The export holds applications of several JobPilot accounts; import one at a time.")
    legacy_owner = next(iter(owners), None)
    imp = Importer(conn, owner_id, report, embed)
    if legacy_owner:
        # Rows of any other JobPilot account (e.g. a test login) are archived in legacy_import only.
        for name, rows in tables.items():
            if name in SKIPPED or name == "user_profiles":
                continue
            other = [r for r in rows if r.get("user_id") and r["user_id"] != legacy_owner]
            for r in other:
                imp.link(name, r, "none", "")
            if other:
                report.notes.append(f"{name}: {len(other)} row(s) of another JobPilot account kept only in legacy_import.")
                tables[name] = [r for r in rows if r not in other]
    scores = {t["application_id"]: t.get("keyword_match_score") for t in tables.get("tailored_resumes", []) if t.get("application_id")}
    imp.applications(tables.get("job_applications", []), scores)
    imp.tailored(tables.get("tailored_resumes", []))
    imp.cold_emails(tables.get("cold_emails", []))
    imp.contacts(tables.get("network_contacts", []))
    imp.referrals(tables.get("referral_requests", []))
    imp.answers(tables.get("qa_answers", []))
    imp.sources_and_postings(tables.get("job_sources", []), tables.get("job_postings", []))
    imp.resume_and_profile(tables.get("resumes", []), tables.get("user_profiles", []), legacy_owner)
    for name, why in SKIPPED.items():
        if tables.get(name):
            report.skipped[name] = why
    handled = {"job_applications", "tailored_resumes", "cold_emails", "network_contacts", "referral_requests", "qa_answers",
               "job_sources", "job_postings", "resumes", "user_profiles", *SKIPPED}
    for name, rows in tables.items():
        if rows and name not in handled:
            raise ImportError_(f"{name} has {len(rows)} rows but no import mapping; add one before importing.")
    if manifest.get("pdfs"):
        report.notes.append("The manifest lists PDFs; this importer does not copy PDF files yet.")
    return report


def verify(conn, folder: Path, owner_id: str) -> dict:
    """Section 5.1 step 4: source vs imported counts, status totals, and no approvable legacy drafts."""
    manifest, tables = load_export(folder)
    linked = dict(conn.execute("""select source_table, count(distinct legacy_id) from public.legacy_import
                                  group by source_table""").fetchall())
    checks = []
    for name, rows in tables.items():
        if not rows or name in SKIPPED:
            continue
        # Every source row must be accounted for: imported, or archived in legacy_import ('none').
        checks.append({"table": name, "source": len(rows), "imported": linked.get(name, 0), "ok": linked.get(name, 0) == len(rows)})
    stages = dict(conn.execute("select stage, count(*) from public.job_case where user_id = %s and legacy group by stage",
                               [owner_id]).fetchall())
    expected = Counter()
    for status, n in (manifest.get("job_applications_by_status") or {}).items():
        expected[STAGE[status][0]] += n
    # The import never writes actions; anything from JobPilot in the action table would be a bug.
    approvable = conn.execute("""select count(*) from public.action where agent = 'jobpilot'
                                 or payload->>'legacy' = 'true'""").fetchone()[0]
    sample = conn.execute("""select company, role, stage, to_char(created_at, 'YYYY-MM-DD') from public.job_case
                             where user_id = %s and legacy order by random() limit 5""", [owner_id]).fetchall()
    result = {"counts": checks, "stages": {"expected": dict(expected), "imported": stages, "ok": dict(expected) == stages},
              "legacy_actions": approvable, "pdfs": {"listed": len(manifest.get("pdfs") or []), "note": "no PDFs in the export"},
              "spot_check": [dict(zip(("company", "role", "stage", "created"), r)) for r in sample]}
    result["ok"] = all(c["ok"] for c in checks) and result["stages"]["ok"] and approvable == 0
    return result
