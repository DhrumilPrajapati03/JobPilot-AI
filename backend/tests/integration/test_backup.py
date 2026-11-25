"""Nightly backup (plan section 9.2) against the throwaway Postgres: encryption, Drive
verification before local deletion, mismatch keeps the local copy, retention, due logic.
pg_dump and Drive HTTP are faked; the backup_log rows and files are real."""
import hashlib
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("JOBDOTS_TEST_DATABASE_URL"),
                                reason="needs the throwaway database from scripts/check_database.py")

from cryptography.fernet import Fernet  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import get_db  # noqa: E402
from app.services import backup  # noqa: E402

DUMP = b"PGDMP synthetic dump " * 100


def fake_pg_dump(args, **kw):
    target = args[args.index("--file") + 1]
    with open(target, "wb") as f:
        f.write(DUMP)
    return SimpleNamespace(returncode=0, stderr="")


class FakeDrive:
    def __init__(self, corrupt=False):
        self.files, self.deleted, self.corrupt = {}, [], corrupt

        def respond(request: httpx.Request):
            if request.url.host == "oauth2.googleapis.com":
                return httpx.Response(200, json={"access_token": "ya29.fixture"})
            if request.method == "POST":
                payload = request.content.split(b"Content-Type: application/octet-stream\r\n\r\n", 1)[1].rsplit(b"\r\n--", 1)[0]
                file_id = f"drive-{len(self.files) + 1}"
                self.files[file_id] = payload
                md5 = hashlib.md5(payload + (b"x" if self.corrupt else b"")).hexdigest()
                return httpx.Response(200, json={"id": file_id, "md5Checksum": md5, "size": str(len(payload))})
            if request.method == "DELETE":
                self.deleted.append(request.url.path.rsplit("/", 1)[-1])
                return httpx.Response(204)
            return httpx.Response(404)

        self.drive = backup.Drive(httpx.Client(transport=httpx.MockTransport(respond)))


@pytest.fixture()
def env(monkeypatch, tmp_path):
    for name, value in {"BACKUP_ENCRYPTION_KEY": Fernet.generate_key().decode(), "BACKUP_DIR": str(tmp_path),
                        "GOOGLE_OAUTH_CLIENT_ID": "", "GOOGLE_DRIVE_REFRESH_TOKEN": "", "BACKUP_KEEP_DAILY": 2,
                        "BACKUP_KEEP_WEEKLY": 1, "BACKUP_HOUR": 2}.items():
        monkeypatch.setattr(settings, name, value)
    get_db().fetch("delete from public.backup_log")
    yield tmp_path
    get_db().fetch("delete from public.backup_log")


def test_drive_backup_is_encrypted_verified_then_local_copy_deleted(env):
    fake = FakeDrive()
    result = backup.run_backup(drive=fake.drive, runner=fake_pg_dump, now=datetime(2026, 11, 25, 21, tzinfo=timezone.utc))
    assert result.status == "verified" and result.destination == "drive"
    uploaded = next(iter(fake.files.values()))
    assert DUMP not in uploaded and Fernet(settings.BACKUP_ENCRYPTION_KEY.encode()).decrypt(uploaded) == DUMP
    assert list(env.iterdir()) == []  # neither the plaintext nor the encrypted file stays behind
    row = get_db().fetch("select status, md5, drive_file_id, local_deleted_at is not null from public.backup_log")[0]
    assert row[0] == "verified" and row[1] == hashlib.md5(uploaded).hexdigest() and row[2] == "drive-1" and row[3]


def test_checksum_mismatch_keeps_the_local_file_and_fails(env):
    fake = FakeDrive(corrupt=True)
    result = backup.run_backup(drive=fake.drive, runner=fake_pg_dump)
    assert result.status == "failed" and "checksum" in result.error
    assert [p.name for p in env.iterdir()] == [result.file_name]
    assert get_db().fetch("select status, local_deleted_at from public.backup_log")[0] == ("failed", None)


def test_no_key_means_no_backup_and_no_plaintext(env, monkeypatch):
    monkeypatch.setattr(settings, "BACKUP_ENCRYPTION_KEY", "")
    result = backup.run_backup(runner=fake_pg_dump)
    assert result.status == "failed" and "BACKUP_ENCRYPTION_KEY" in result.error
    assert list(env.iterdir()) == []


def test_local_destination_and_retention(env):
    start = datetime(2026, 11, 24, 21, tzinfo=timezone.utc)  # Tuesday 02:30 in Kolkata
    for day in range(4):
        assert backup.run_backup(runner=fake_pg_dump, now=start + timedelta(days=day)).status == "verified"
    states = get_db().fetch("select tier, status from public.backup_log order by started_at")
    assert [s for t, s in states if t == "daily"].count("verified") == 2  # BACKUP_KEEP_DAILY
    assert len(list(env.iterdir())) == len([1 for _, s in states if s == "verified"])


def test_drive_retention_deletes_old_drive_files(env):
    fake = FakeDrive()
    for day in range(3):
        backup.run_backup(drive=fake.drive, runner=fake_pg_dump, now=datetime(2026, 11, 25, 21, tzinfo=timezone.utc) + timedelta(days=day))
    assert fake.deleted, "the oldest daily backup should be removed from Drive"


def test_due_catches_up_after_the_laptop_was_off(env):
    now = datetime(2026, 11, 25, 6, 0, tzinfo=timezone.utc)  # 11:30 in Kolkata
    assert backup.due(now)  # never backed up
    get_db().fetch("insert into public.backup_log (file_name, status, verified_at) values ('x', 'verified', %s)",
                   [now - timedelta(hours=3)])
    assert not backup.due(now)  # today's backup after 02:00 local exists
    get_db().fetch("update public.backup_log set verified_at = %s", [now - timedelta(days=3)])
    assert backup.due(now)  # missed while asleep: run now, whatever the hour


def test_restore_decrypts_before_pg_restore(env, tmp_path):
    encrypted = backup.dump_encrypted(env, "manual.dump.enc", runner=fake_pg_dump)
    seen = {}

    def fake_restore(args, **kw):
        seen["data"] = open(args[-1], "rb").read()
        seen["args"] = args
        return SimpleNamespace(returncode=0, stderr="")

    backup.restore(encrypted, "postgresql+psycopg://u:p@127.0.0.1:1/scratch", runner=fake_restore)
    assert seen["data"] == DUMP and "postgresql://u:p@127.0.0.1:1/scratch" in seen["args"]
