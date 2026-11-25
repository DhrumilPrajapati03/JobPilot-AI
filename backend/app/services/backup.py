"""Nightly encrypted database backups to Google Drive (plan section 9.2).

1. `pg_dump -Fc` to a temporary file (never kept unencrypted: it is encrypted and removed
   right away).
2. Encrypt with BACKUP_ENCRYPTION_KEY (Fernet). The key lives only in the local .env,
   never on Drive; without it a backup is refused rather than written in the clear.
3. Upload to Drive with the narrow `drive.file` scope.
4. Verify before deleting: Drive's `md5Checksum` and size must equal the local file's.
   Only then is the local copy deleted. On any mismatch or error the local file stays and
   the run is logged as failed.
5. Retention: the last BACKUP_KEEP_DAILY daily and BACKUP_KEEP_WEEKLY weekly (Monday)
   backups; older ones are deleted from Drive (or local disk) and marked pruned.
6. Every run is a `backup_log` row. Catch-up-on-wake: the worker schedules a backup when
   the last verified one is older than a day, whatever the hour.

Without a Drive connection the encrypted file stays in BACKUP_DIR and is verified by
re-reading it (destination 'local').
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.db import get_db

DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,md5Checksum,size"
DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
TIMEOUT = httpx.Timeout(120.0, connect=15.0)


class BackupError(RuntimeError):
    pass


@dataclass
class BackupResult:
    log_id: int
    file_name: str
    destination: str
    status: str
    size_bytes: int
    error: str | None = None


def libpq_url(url: str | None = None) -> str:
    return (url or settings.DATABASE_URL).replace("postgresql+psycopg://", "postgresql://", 1)


def fernet() -> Fernet:
    key = settings.BACKUP_ENCRYPTION_KEY.strip()
    if not key:
        raise BackupError("BACKUP_ENCRYPTION_KEY is not set; backups are never written unencrypted.")
    try:
        return Fernet(key.encode())
    except ValueError:
        raise BackupError("BACKUP_ENCRYPTION_KEY is not a valid key (generate one with scripts/backup.py new-key).") from None


def drive_configured() -> bool:
    return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET and settings.GOOGLE_DRIVE_REFRESH_TOKEN)


def digests(path: Path) -> tuple[str, str, int]:
    sha, md5, size = hashlib.sha256(), hashlib.md5(), 0  # md5 only because Drive reports md5Checksum
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    return sha.hexdigest(), md5.hexdigest(), size


def dump_encrypted(target_dir: Path, name: str, *, url: str | None = None, runner=subprocess.run) -> Path:
    """pg_dump -> encrypt -> remove the plaintext. Returns the encrypted file."""
    box = fernet()
    target_dir.mkdir(parents=True, exist_ok=True)
    fd, plain = tempfile.mkstemp(prefix="jobdots-dump-", dir=target_dir)
    os.close(fd)
    plain_path = Path(plain)
    try:
        result = runner(["pg_dump", "--format=custom", "--no-owner", "--file", str(plain_path), "--dbname", libpq_url(url)],
                        capture_output=True, text=True, timeout=1800)
        if result.returncode:
            raise BackupError("pg_dump failed: " + (result.stderr or "")[-300:].replace(libpq_url(url), "<database>"))
        encrypted = target_dir / name
        encrypted.write_bytes(box.encrypt(plain_path.read_bytes()))
        return encrypted
    finally:
        plain_path.unlink(missing_ok=True)


def decrypt_to(encrypted: Path, plain: Path) -> None:
    try:
        plain.write_bytes(fernet().decrypt(encrypted.read_bytes()))
    except InvalidToken:
        raise BackupError("This backup can't be decrypted with BACKUP_ENCRYPTION_KEY.") from None


class Drive:
    """The three Drive calls backups need, on a refreshed access token."""

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=TIMEOUT)
        self._token: str | None = None

    def token(self) -> str:
        if self._token is None:
            response = self.client.post(GOOGLE_TOKEN, data={
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID, "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "refresh_token": settings.GOOGLE_DRIVE_REFRESH_TOKEN, "grant_type": "refresh_token"})
            if response.status_code != 200:
                raise BackupError("Google Drive refused the saved connection (in Testing mode it expires after 7 days). "
                                  "Reconnect with: python scripts/backup.py connect-drive")
            self._token = response.json()["access_token"]
        return self._token

    def upload(self, path: Path) -> dict:
        metadata = {"name": path.name, "mimeType": "application/octet-stream"}
        if settings.BACKUP_DRIVE_FOLDER_ID:
            metadata["parents"] = [settings.BACKUP_DRIVE_FOLDER_ID]
        boundary = "jobdots-backup-" + hashlib.sha256(path.name.encode()).hexdigest()[:16]
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(metadata)}\r\n"
                f"--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        response = self.client.post(DRIVE_UPLOAD, content=body, headers={
            "Authorization": f"Bearer {self.token()}", "Content-Type": f"multipart/related; boundary={boundary}"})
        if response.status_code not in (200, 201):
            raise BackupError(f"Drive upload failed (HTTP {response.status_code}).")
        return response.json()

    def delete(self, file_id: str) -> None:
        response = self.client.delete(f"{DRIVE_FILES}/{file_id}", headers={"Authorization": f"Bearer {self.token()}"})
        if response.status_code not in (204, 404):
            raise BackupError(f"Drive delete failed (HTTP {response.status_code}).")


def _tier(now: datetime) -> str:
    from app.core.policy import load_policy
    try:
        local = load_policy().local(now)
    except Exception:
        local = now
    return "weekly" if local.weekday() == 0 else "daily"


def backup_dir() -> Path:
    return Path(settings.BACKUP_DIR)


def run_backup(*, now: datetime | None = None, drive: Drive | None = None, url: str | None = None, runner=subprocess.run) -> BackupResult:
    """One full backup: dump, encrypt, upload, verify, delete local (Drive) and prune."""
    now = now or datetime.now(timezone.utc)
    tier = _tier(now)
    name = f"jobdots-{now.strftime('%Y%m%dT%H%M%SZ')}-{tier}.dump.enc"
    destination = "drive" if (drive is not None or drive_configured()) else "local"
    db = get_db()
    log_id = db.fetch("""insert into public.backup_log (file_name, tier, destination, status) values (%s, %s, %s, 'started')
                         returning id""", [name, tier, destination])[0][0]
    path = None
    try:
        path = dump_encrypted(backup_dir(), name, url=url, runner=runner)
        sha, md5, size = digests(path)
        db.fetch("update public.backup_log set size_bytes = %s, sha256 = %s, md5 = %s where id = %s", [size, sha, md5, log_id])
        if destination == "local":
            # Re-read what is on disk; that file is the backup.
            if digests(path)[0] != sha:
                raise BackupError("The local backup changed while it was being written.")
            db.fetch("update public.backup_log set status = 'verified', verified_at = now() where id = %s", [log_id])
        else:
            drive = drive or Drive()
            uploaded = drive.upload(path)
            db.fetch("update public.backup_log set drive_file_id = %s where id = %s", [uploaded.get("id"), log_id])
            if uploaded.get("md5Checksum") != md5 or int(uploaded.get("size") or -1) != size:
                raise BackupError("Drive's checksum or size does not match the local file; the local copy is kept.")
            db.fetch("update public.backup_log set status = 'verified', verified_at = now() where id = %s", [log_id])
            path.unlink()
            db.fetch("update public.backup_log set local_deleted_at = now() where id = %s", [log_id])
        prune(drive=drive if destination == "drive" else None)
        return BackupResult(log_id, name, destination, "verified", size)
    except Exception as exc:
        message = str(exc) if isinstance(exc, BackupError) else f"Backup failed ({type(exc).__name__})."
        db.fetch("update public.backup_log set status = 'failed', error = %s where id = %s", [message[:500], log_id])
        # The encrypted local file (if any) is kept for a retry or manual upload.
        return BackupResult(log_id, name, destination, "failed", path.stat().st_size if path and path.exists() else 0, message)


def prune(*, drive: Drive | None = None) -> int:
    """Keep the newest N daily and M weekly verified backups per destination; delete the rest."""
    db = get_db()
    removed = 0
    for tier, keep in (("daily", settings.BACKUP_KEEP_DAILY), ("weekly", settings.BACKUP_KEEP_WEEKLY)):
        rows = db.fetch("""select id, file_name, destination, drive_file_id from public.backup_log
                           where status = 'verified' and tier = %s order by started_at desc offset %s""", [tier, keep])
        for log_id, name, destination, file_id in rows:
            if destination == "drive":
                if drive is None or not file_id:
                    continue
                drive.delete(file_id)
            else:
                (backup_dir() / name).unlink(missing_ok=True)
            db.fetch("update public.backup_log set status = 'pruned' where id = %s", [log_id])
            removed += 1
    return removed


def last_verified() -> datetime | None:
    rows = get_db().fetch("select max(verified_at) from public.backup_log where status = 'verified'")
    return rows[0][0] if rows else None


def due(now: datetime | None = None) -> bool:
    """Nightly after BACKUP_HOUR (local time), or right away when the last good backup is over a day old."""
    now = now or datetime.now(timezone.utc)
    last = last_verified()
    if last is None or now - last > timedelta(hours=26):
        return True
    from app.core.policy import load_policy
    try:
        policy = load_policy()
        local, day_start = policy.local(now), policy.day_start(now)
    except Exception:
        local, day_start = now, now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local.hour >= settings.BACKUP_HOUR and last < day_start + timedelta(hours=settings.BACKUP_HOUR)


def schedule(store, owner_id: str, now: datetime | None = None) -> dict | None:
    """Queue tonight's backup on the durable queue (idempotent per local day)."""
    now = now or datetime.now(timezone.utc)
    if not settings.BACKUP_ENABLED or not due(now):
        return None
    from app.core.policy import load_policy
    try:
        day = load_policy().local(now).date().isoformat()
    except Exception:
        day = now.date().isoformat()
    return store.enqueue(owner_id, "backup", {"scheduled_on": day}, f"backup:{day}")


def restore(encrypted: Path, target_url: str, *, runner=subprocess.run) -> None:
    """Decrypt a backup and pg_restore it into target_url (use a scratch database for the monthly test)."""
    with tempfile.TemporaryDirectory(prefix="jobdots-restore-") as tmp:
        plain = Path(tmp) / "restore.dump"
        decrypt_to(encrypted, plain)
        result = runner(["pg_restore", "--no-owner", "--exit-on-error", "--dbname", libpq_url(target_url), str(plain)],
                        capture_output=True, text=True, timeout=1800)
        if result.returncode:
            raise BackupError("pg_restore failed: " + (result.stderr or "")[-300:].replace(libpq_url(target_url), "<database>"))
