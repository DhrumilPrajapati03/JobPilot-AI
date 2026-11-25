"""Legacy import (plan section 5.1) against the throwaway Postgres, with a synthetic export."""
import hashlib
import json
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("JOBDOTS_TEST_DATABASE_URL"),
                                reason="needs the throwaway database from scripts/check_database.py")

import psycopg  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import legacy_import  # noqa: E402

LEGACY_USER = "780131be-0000-4000-8000-000000000001"


def ids(n):
    return [str(uuid.uuid4()) for _ in range(n)]


def write_export(folder, tables, by_status):
    manifest = {"tables": {}, "pdfs": [], "job_applications_by_status": by_status}
    for name, rows in tables.items():
        data = "".join(json.dumps(r) + "\n" for r in rows).encode()
        (folder / f"{name}.jsonl").write_bytes(data)
        manifest["tables"][name] = {"file": f"{name}.jsonl", "rows": len(rows), "sha256": hashlib.sha256(data).hexdigest()}
    (folder / "manifest.json").write_text(json.dumps(manifest))


@pytest.fixture()
def export(tmp_path):
    apps, tailored, emails, contacts, answers, sources, postings = ids(3), ids(3), ids(2), ids(2), ids(1), ids(1), ids(2)
    t = "2026-10-01T10:00:00+00:00"
    tables = {
        "job_applications": [
            {"id": apps[0], "user_id": LEGACY_USER, "company": "Acme", "role": "ML Engineer", "status": "applied", "source": "manual",
             "jd_url": "https://jobs.example/1", "jd_text": "JD", "jd_analysis": {}, "notes": "", "cover_letter": "Dear Acme",
             "linkedin_dm": {"body": "Hi"}, "prepared_form": {"fields": []}, "created_at": t, "updated_at": t,
             "applied_at": t, "follow_up_at": "2026-11-29T00:00:00+00:00"},
            {"id": apps[1], "user_id": LEGACY_USER, "company": "Beta", "role": "AI Engineer", "status": "interviewing", "source": "manual",
             "jd_url": "", "jd_text": "", "jd_analysis": None, "notes": "", "cover_letter": "", "linkedin_dm": {}, "prepared_form": None,
             "created_at": t, "updated_at": t, "applied_at": t, "follow_up_at": None},
            {"id": apps[2], "user_id": LEGACY_USER, "company": "Gamma", "role": "Engineer", "status": "archived", "source": "himalayas",
             "jd_url": "", "jd_text": "", "jd_analysis": None, "notes": "", "cover_letter": "", "linkedin_dm": {}, "prepared_form": None,
             "created_at": t, "updated_at": t, "applied_at": None, "follow_up_at": None},
        ],
        "tailored_resumes": [{"id": tailored[i], "user_id": LEGACY_USER, "application_id": apps[i], "version": 1, "content": {"name": "Ada"},
                              "keyword_match_score": 70.0 + i, "missing_keywords": [], "pdf_url": None, "generated_at": t} for i in range(3)],
        "cold_emails": [{"id": emails[0], "user_id": LEGACY_USER, "application_id": apps[0], "sequence_number": 1, "subject": "Hi",
                         "body": "Hello", "to_email": "hr@acme.example", "to_name": "HR", "sent_at": None, "opened": False,
                         "opened_at": None, "replied": False, "replied_at": None},
                        {"id": emails[1], "user_id": LEGACY_USER, "application_id": apps[0], "sequence_number": 2, "subject": "Re",
                         "body": "Following up", "to_email": "hr@acme.example", "to_name": "HR", "sent_at": t, "opened": False,
                         "opened_at": None, "replied": True, "replied_at": t}],
        "network_contacts": [{"id": contacts[0], "user_id": LEGACY_USER, "full_name": "Rita Recruiter", "position": "Senior Technical Recruiter",
                              "company": "Acme", "dedupe_key": "rita", "linkedin_url": "", "email": "", "source": "linkedin", "notes": "",
                              "created_at": t},
                             {"id": contacts[1], "user_id": LEGACY_USER, "full_name": "Pat Peer", "position": "Software Engineer",
                              "company": "Acme", "dedupe_key": "pat", "linkedin_url": "", "email": "", "source": "linkedin", "notes": "",
                              "created_at": t}],
        "referral_requests": [{"id": str(uuid.uuid4()), "user_id": LEGACY_USER, "application_id": apps[0], "contact_id": contacts[1],
                               "message": "Could you refer me?", "status": "drafted", "sent_at": None, "created_at": t}],
        "qa_answers": [{"id": answers[0], "user_id": LEGACY_USER, "question": "Are you authorized to work in India?", "answer": "Yes",
                        "category": "work_auth", "sensitive": True, "created_at": t, "updated_at": t}],
        "job_sources": [{"id": sources[0], "user_id": LEGACY_USER, "ats": "lever", "slug": f"acme-{sources[0][:6]}", "company": "Acme",
                         "enabled": True, "job_count": 2, "created_at": t}],
        "job_postings": [{"id": postings[i], "user_id": LEGACY_USER, "source_id": sources[0], "ats": "lever", "external_id": f"x-{postings[i]}",
                          "company": "Acme", "title": "Engineer", "location": "India", "status": "new", "application_id": apps[0]} for i in range(2)],
        "resumes": [{"id": str(uuid.uuid4()), "user_id": LEGACY_USER, "version": "base", "name": "Ada", "headline": "ML Engineer",
                     "summary": "", "experience": [], "skills": {"primary": ["Python"], "secondary": []}, "projects": [], "education": [],
                     "certifications": [], "created_at": t, "updated_at": t}],
        "user_profiles": [{"id": LEGACY_USER, "name": "Ada", "headline": "ML Engineer", "location": "India", "salary_range": "",
                           "linkedin_url": "", "work_preferences": {"remote": True}}],
        "extension_tokens": [{"id": str(uuid.uuid4()), "user_id": LEGACY_USER, "token_hash": "0" * 64}],
        "application_events": [],
    }
    write_export(tmp_path, tables, {"applied": 1, "interviewing": 1, "archived": 1})
    return tmp_path


@pytest.fixture()
def conn():
    url = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    owner = str(uuid.uuid4())
    with psycopg.connect(url) as c:
        c.execute("delete from public.legacy_import")
        c.execute("insert into auth.users(id, email) values (%s, %s)", [owner, f"{owner}@example.invalid"])
        c.commit()
        yield c, owner
        c.rollback()
        c.execute("delete from public.legacy_import")
        c.execute("delete from auth.users where id = %s", [owner])
        c.commit()


def count(c, query, *params):
    return c.execute(query, params).fetchone()[0]


def test_dry_run_saves_nothing(export, conn):
    c, owner = conn
    report = legacy_import.run_import(c, export, owner, dry_run=True)
    c.rollback()
    assert report.inserted[("job_applications", "job_case")] == 3
    assert count(c, "select count(*) from public.job_case where user_id = %s", owner) == 0


def test_import_is_complete_idempotent_and_never_creates_actions(export, conn):
    c, owner = conn
    legacy_import.run_import(c, export, owner, dry_run=False, embed=lambda q: ([0.1] * 768, "fixture"))
    c.commit()
    assert dict(c.execute("select stage, count(*) from public.job_case where user_id = %s group by stage", [owner]).fetchall()) == \
        {"applied": 1, "interview": 1, "closed": 1}
    assert count(c, "select count(*) from public.job_case where user_id = %s and fit_score_legacy is not null", owner) == 3
    drafts = c.execute("select content->>'channel' from public.artifact where user_id = %s and kind = 'draft' and legacy", [owner]).fetchall()
    assert sorted(d[0] for d in drafts) == ["cover_letter", "email", "email", "linkedin_dm", "referral"]
    assert count(c, "select count(*) from public.action where user_id = %s", owner) == 0
    kinds = [r[0] for r in c.execute("select kind from public.case_event where user_id = %s", [owner]).fetchall()]
    assert {"imported", "applied", "follow_up_suggested", "email_sent", "email_replied", "referral_drafted"} <= set(kinds)
    assert dict(c.execute("select name, role_class from public.contact where user_id = %s", [owner]).fetchall()) == \
        {"Rita Recruiter": "recruiter", "Pat Peer": "employee"}
    assert count(c, "select count(*) from public.answer_bank where user_id = %s and sensitive and embedding is not null", owner) == 1
    assert count(c, "select count(*) from public.job_postings where user_id = %s and application_id is null", owner) == 2
    assert count(c, "select count(*) from public.resumes where user_id = %s", owner) == 1
    assert c.execute("select name, work_preferences from public.user_profiles where id = %s", [owner]).fetchone() == ("Ada", {"remote": True})
    before = count(c, "select count(*) from public.case_event where user_id = %s", owner)
    again = legacy_import.run_import(c, export, owner, dry_run=False)
    c.commit()
    assert sum(again.inserted.values()) == 0
    assert count(c, "select count(*) from public.case_event where user_id = %s", owner) == before
    result = legacy_import.verify(c, export, owner)
    assert result["ok"], result
    assert result["legacy_actions"] == 0 and len(result["spot_check"]) == 3
    raw = c.execute("select raw from public.legacy_import where source_table = 'job_applications' limit 1").fetchone()[0]
    assert "cover_letter" in raw  # the original row is kept whole


def test_tampered_export_is_refused(export, conn):
    c, owner = conn
    (export / "qa_answers.jsonl").write_text('{"id": "x"}\n')
    with pytest.raises(legacy_import.ImportError_):
        legacy_import.run_import(c, export, owner)


def test_role_classifier():
    assert legacy_import.classify_role("Talent Acquisition Partner") == "recruiter"
    assert legacy_import.classify_role("Co-Founder & CEO") == "ceo"
    assert legacy_import.classify_role("CTO") == "cto"
    assert legacy_import.classify_role("Director of Engineering") == "hiring_manager"
    assert legacy_import.classify_role("") == "unknown"
