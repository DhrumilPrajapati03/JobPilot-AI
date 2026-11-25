"""pgvector resume store on the throwaway Postgres, with deterministic fake embeddings (no Ollama)."""
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("JOBDOTS_TEST_DATABASE_URL"),
                                reason="needs the throwaway database from scripts/check_database.py")

from app.db import get_db  # noqa: E402
from app.services import vector_store  # noqa: E402

TOPICS = ("docker", "python", "sql", "summary")


class KeywordEmbeddings:
    """One dimension per topic word, so the nearest section is predictable."""

    def __init__(self):
        self.calls = 0

    def embed_documents(self, texts):
        self.calls += 1
        return [[1.0 if word in t.lower() else 0.01 for word in TOPICS] for t in texts]

    def embed_query(self, text):
        return self.embed_documents([text])[0]


@pytest.fixture()
def owners(monkeypatch):
    emb = KeywordEmbeddings()
    monkeypatch.setattr(vector_store, "get_embeddings", lambda: ("fake-keyword", emb))
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    db = get_db()
    for uid in ids:
        db.fetch("insert into auth.users(id, email) values (%s, %s)", [uid, uid + "@example.invalid"])
    yield ids, emb, db
    for uid in ids:
        db.fetch("delete from auth.users where id = %s", [uid])


def base_resume(uid, bullets):
    return {"user_id": uid, "version": "base", "name": "Synthetic", "summary": "Summary of a backend engineer.",
            "experience": [{"company": "Example", "role": "Engineer", "duration": "2025", "bullets": bullets}],
            "skills": {"primary": ["Python"], "secondary": []}}


def test_search_indexes_on_demand_ranks_by_distance_and_isolates_owners(owners):
    (mine, other), emb, db = owners
    db.table("resumes").insert(base_resume(mine, ["Shipped Docker images for the API.", "Tuned SQL queries."])).execute()
    db.table("resumes").insert(base_resume(other, ["Other owner's Docker work."])).execute()

    hits = vector_store.search_relevant("docker", mine, top_k=2)
    assert hits[0]["text"] == "Shipped Docker images for the API."
    assert hits[0]["metadata"]["section_type"] == "experience" and hits[0]["metadata"]["company"] == "Example"
    assert hits[0]["distance"] <= hits[1]["distance"]
    assert all("Other owner" not in h["text"] for h in vector_store.search_relevant("docker", mine, top_k=10))

    calls = emb.calls
    vector_store.search_relevant("sql", mine)  # unchanged resume: no re-embedding of sections
    assert emb.calls == calls + 1  # only the query was embedded


def test_changed_resume_is_reindexed_and_deleted_resume_clears_rows(owners):
    (mine, _), _, db = owners
    db.table("resumes").insert(base_resume(mine, ["Tuned SQL queries."])).execute()
    assert vector_store.search_relevant("sql", mine)[0]["text"] == "Tuned SQL queries."
    db.table("resumes").update({"experience": [{"company": "Example", "role": "Engineer", "duration": "2025",
                                                "bullets": ["Built Docker pipelines."]}]}).eq("user_id", mine).execute()
    texts = [h["text"] for h in vector_store.search_relevant("docker", mine, top_k=10)]
    assert "Built Docker pipelines." in texts and "Tuned SQL queries." not in texts
    db.table("resumes").delete().eq("user_id", mine).execute()
    assert vector_store.search_relevant("docker", mine) == []
    assert db.fetch("select count(*) from public.resume_sections where user_id = %s", [mine]) == [(0,)]
