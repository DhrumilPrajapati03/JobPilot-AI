"""Owner row resolution against the throwaway Postgres (see test_db_layer.py for how it runs).

Each case runs inside one transaction that is rolled back, so it can start from an
empty auth.users table without deleting anything for real.
"""
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("JOBDOTS_TEST_DATABASE_URL"),
                                reason="needs the throwaway database from scripts/check_database.py")

import psycopg  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.auth import _resolve_owner  # noqa: E402


class TxDB:
    def __init__(self, conn):
        self.conn = conn

    def fetch(self, query, params=None):
        cur = self.conn.execute(query, params)
        return cur.fetchall() if cur.description else []


@pytest.fixture()
def db():
    url = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(url) as conn:
        conn.execute("delete from auth.users")  # inside the transaction; rolled back below
        yield TxDB(conn)
        conn.rollback()


def test_first_use_creates_the_owner(db):
    owner = _resolve_owner(db, "owner@example.invalid", "")
    assert db.fetch("select id::text, email from auth.users") == [(owner, "owner@example.invalid")]
    assert _resolve_owner(db, "owner@example.invalid", "") == owner


def test_changing_the_email_keeps_the_same_owner(db):
    owner = _resolve_owner(db, "old@example.invalid", "")
    db.fetch("insert into public.qa_answers(user_id, question) values (%s, 'Kept?')", [owner])
    assert _resolve_owner(db, "new@example.invalid", "") == owner
    assert db.fetch("select email from auth.users") == [("new@example.invalid",)]
    assert db.fetch("select count(*) from public.qa_answers where user_id = %s", [owner]) == [(1,)]


def test_pinned_id_is_used_and_created(db):
    pinned = str(uuid.uuid4())
    assert _resolve_owner(db, "owner@example.invalid", pinned) == pinned
    assert _resolve_owner(db, "renamed@example.invalid", pinned) == pinned
    assert db.fetch("select id::text, email from auth.users") == [(pinned, "renamed@example.invalid")]


def test_several_users_need_an_exact_match(db):
    db.fetch("insert into auth.users(email) values ('a@example.invalid'), ('b@example.invalid')")
    b = db.fetch("select id::text from auth.users where email = 'b@example.invalid'")[0][0]
    assert _resolve_owner(db, "b@example.invalid", "") == b
    with pytest.raises(RuntimeError):
        _resolve_owner(db, "nobody@example.invalid", "")
