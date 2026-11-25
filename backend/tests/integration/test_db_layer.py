"""app.db against a real, throwaway Postgres (run by scripts/check_database.py).

Skipped unless JOBDOTS_TEST_DATABASE_URL is set; tests/run_offline.py passes it
through as DATABASE_URL. Every fixture user is random and deleted afterwards.
"""
import os
import re
import uuid

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("JOBDOTS_TEST_DATABASE_URL"),
                                reason="needs the throwaway database from scripts/check_database.py")

from app.db import DatabaseError, get_db, select_all  # noqa: E402

ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?\+00:00$")


@pytest.fixture()
def owner():
    uid = str(uuid.uuid4())
    get_db().fetch("insert into auth.users(id, email) values (%s, %s)", [uid, uid + "@example.invalid"])
    yield uid
    get_db().fetch("delete from auth.users where id = %s", [uid])


def posting(uid, n, **extra):
    return {"user_id": uid, "ats": "lever", "external_id": f"ext-{n}", "title": f"Engineer {n}", **extra}


def test_insert_returns_postgrest_json_shapes(owner):
    row = get_db().table("job_postings").insert(posting(owner, 1, fit_score=87.5, matched_skills=["Python", "SQL"],
                                                        matching_details={"eligibility": {"status": "eligible"}})).execute().data[0]
    assert uuid.UUID(row["id"]) and row["user_id"] == owner
    assert ISO.match(row["discovered_at"]), row["discovered_at"]
    assert row["fit_score"] == 87.5 and row["remote"] is None
    assert row["matched_skills"] == ["Python", "SQL"] and row["matching_details"]["eligibility"]["status"] == "eligible"
    assert row["status"] == "new"  # column default applied for keys not sent


def test_select_columns_filters_order_limit_range_count(owner):
    db = get_db()
    db.table("job_postings").insert([posting(owner, n, fit_score=n) for n in range(1, 6)]).execute()
    rows = db.table("job_postings").select("external_id, fit_score").eq("user_id", owner).order("fit_score", desc=True).limit(2).execute().data
    assert rows == [{"external_id": "ext-5", "fit_score": 5}, {"external_id": "ext-4", "fit_score": 4}]
    page = db.table("job_postings").select("external_id", count="exact").eq("user_id", owner).order("external_id").range(1, 2).execute()
    assert [r["external_id"] for r in page.data] == ["ext-2", "ext-3"] and page.count == 5
    assert len(db.table("job_postings").select("id").eq("user_id", owner).in_("external_id", ["ext-1", "ext-3", "nope"]).execute().data) == 2
    assert len(db.table("job_postings").select("id").eq("user_id", owner).gt("fit_score", 3).execute().data) == 2
    assert len(db.table("job_postings").select("id").match({"user_id": owner, "external_id": "ext-2"}).execute().data) == 1
    assert len(db.table("job_postings").select("id").eq("user_id", owner).is_("remote", "null").execute().data) == 5
    assert len(select_all(lambda: db.table("job_postings").select("id").eq("user_id", owner).order("id"), page_size=2)) == 5


def test_json_path_filter_and_bool_filter(owner):
    db = get_db()
    db.table("job_postings").insert([posting(owner, 1, matching_details={"step": "queued"}, auto_drafted=True),
                                     posting(owner, 2, matching_details={"step": "done"})]).execute()
    hits = db.table("job_postings").select("external_id").eq("user_id", owner).eq("matching_details->>step", "queued").execute().data
    assert hits == [{"external_id": "ext-1"}]
    assert db.table("job_postings").select("external_id").eq("user_id", owner).eq("auto_drafted", True).execute().data == [{"external_id": "ext-1"}]


def test_update_and_delete_require_filters_and_return_rows(owner):
    db = get_db()
    db.table("job_postings").insert(posting(owner, 1)).execute()
    updated = db.table("job_postings").update({"status": "dismissed", "skip_flags": ["remote"]}).eq("user_id", owner).execute().data
    assert updated[0]["status"] == "dismissed" and updated[0]["skip_flags"] == ["remote"]
    with pytest.raises(DatabaseError):
        db.table("job_postings").update({"status": "new"}).execute()
    with pytest.raises(DatabaseError):
        db.table("job_postings").delete().execute()
    assert len(db.table("job_postings").delete().eq("user_id", owner).execute().data) == 1


def test_upsert_merges_on_conflict_and_can_ignore_duplicates(owner):
    db = get_db()
    first = db.table("qa_answers").upsert({"user_id": owner, "question": "Notice period?", "answer": "30 days"},
                                          on_conflict="user_id,question").execute().data[0]
    second = db.table("qa_answers").upsert({"user_id": owner, "question": "Notice period?", "answer": "45 days"},
                                           on_conflict="user_id,question").execute().data[0]
    assert first["id"] == second["id"] and second["answer"] == "45 days"
    ignored = db.table("qa_answers").upsert({"user_id": owner, "question": "Notice period?", "answer": "60 days"},
                                            on_conflict="user_id,question", ignore_duplicates=True).execute().data
    assert ignored == []
    # Default conflict target is the primary key (writing_templates: user_id, kind).
    db.table("writing_templates").upsert({"user_id": owner, "kind": "email", "content": "v1"}).execute()
    db.table("writing_templates").upsert({"user_id": owner, "kind": "email", "content": "v2"}).execute()
    assert db.table("writing_templates").select("content").eq("user_id", owner).execute().data == [{"content": "v2"}]


def test_user_scoped_client_sets_auth_uid_for_defaults_and_rpcs(owner):
    db = get_db(owner)
    row = db.table("writing_templates").insert({"kind": "dm", "content": "Short and specific."}).execute().data[0]
    assert row["user_id"] == owner
    metrics = db.rpc("get_product_metrics", {}).execute().data
    assert isinstance(metrics, dict) and "runs" in metrics
    assert get_db().fetch("select auth.uid()") == [(None,)]


def test_rpc_types_and_errors(owner):
    db = get_db()
    run = db.rpc("enqueue_agent_run", {"p_user_id": owner, "p_kind": "scan", "p_inputs": {"auto_draft": False}, "p_key": "db-layer"}).execute().data
    assert run["status"] == "queued" and run["user_id"] == owner
    assert db.rpc("release_schema_ready", {}).execute().data is True
    assert db.rpc("prune_release_telemetry", {"p_before": "2000-01-01T00:00:00Z"}).execute().data is None  # void
    with pytest.raises(DatabaseError) as error:
        db.rpc("enqueue_agent_run", {"p_user_id": owner, "p_kind": "scan", "p_inputs": {"auto_draft": True}, "p_key": "db-layer"}).execute()
    assert "idempotency_key_conflict" in str(error.value)
    with pytest.raises(DatabaseError):
        db.rpc("enqueue_agent_run", {"p_nope": 1}).execute()
    db.fetch("delete from public.agent_runs where user_id = %s", [owner])


def test_error_codes_match_postgrest(owner):
    db = get_db()
    db.table("network_contacts").insert({"user_id": owner, "full_name": "A", "dedupe_key": "a"}).execute()
    with pytest.raises(DatabaseError) as error:
        db.table("network_contacts").insert({"user_id": owner, "full_name": "A", "dedupe_key": "a"}).execute()
    assert error.value.code == "23505"
    with pytest.raises(DatabaseError) as error:
        db.table("no_such_table").select("*").execute()
    assert error.value.code == "42P01" and "does not exist" in str(error.value)
    with pytest.raises(DatabaseError) as error:
        db.table("network_contacts").select("nope").execute()
    assert error.value.code == "42703"
    with pytest.raises(DatabaseError):
        db.table("network_contacts").select("id, (select 1)").execute()
