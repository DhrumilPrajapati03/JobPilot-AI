"""Read-only export of every JobPilot table and the `resumes` storage bucket.

Usage:
    backend/.venv-release/Scripts/python.exe scripts/export_supabase.py OUT_DIR

OUT_DIR must be outside the repo and must not already contain files.

Reads SUPABASE_URL and SUPABASE_SERVICE_KEY from backend/.env in memory only.
Issues only GET/HEAD requests, plus the storage list endpoint (a POST that only lists).
Prints table names and row counts, never keys or row contents.
"""
from __future__ import annotations

import base64
import binascii
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[1]
PAGE = 500
EXPECTED_TABLES = [
    "user_profiles", "resumes", "identity_confirmations", "job_applications", "tailored_resumes",
    "cold_emails", "qa_answers", "job_sources", "job_postings", "network_contacts",
    "referral_requests", "extension_tokens", "autopilot_state", "agent_runs", "agent_run_events",
    "agent_run_locks", "mail_connections", "outreach_messages", "mail_replies", "recruiter_leads",
    "application_documents", "application_execution_sessions", "application_events",
    "execution_workers",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class ReadOnlyClient:
    """Wraps httpx so only reads can be sent."""

    def __init__(self, base: str, key: str):
        self._c = httpx.Client(
            base_url=base,
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=httpx.Timeout(60.0),
        )

    def get(self, path: str, **kw) -> httpx.Response:
        return self._c.get(path, **kw)

    def head(self, path: str, **kw) -> httpx.Response:
        return self._c.head(path, **kw)

    def storage_list(self, bucket: str, prefix: str, offset: int) -> httpx.Response:
        # Storage's list endpoint is POST-only but does not mutate anything.
        return self._c.post(
            f"/storage/v1/object/list/{quote(bucket)}",
            json={"prefix": prefix, "limit": 100, "offset": offset,
                  "sortBy": {"column": "name", "order": "asc"}},
        )


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def discover_tables(api: ReadOnlyClient) -> dict[str, list[str]]:
    """Return {table: [primary key columns]} from PostgREST's OpenAPI document."""
    r = api.get("/rest/v1/", headers={"Accept": "application/openapi+json"})
    if r.status_code != 200:
        fail(f"OpenAPI discovery failed with HTTP {r.status_code}")
    defs = r.json().get("definitions", {})
    out: dict[str, list[str]] = {}
    for name, d in defs.items():
        props = d.get("properties", {})
        out[name] = [c for c, p in props.items() if "<pk/>" in (p.get("description") or "")]
    return out


def exact_count(api: ReadOnlyClient, table: str) -> int | None:
    r = api.head(f"/rest/v1/{table}", params={"select": "*"},
                 headers={"Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"})
    m = re.search(r"/(\d+)$", r.headers.get("content-range", ""))
    return int(m.group(1)) if m else None


def export_table(api: ReadOnlyClient, table: str, pks: list[str], path: Path) -> list[dict] | int:
    """Page through a table into JSON lines. Returns rows for the tables needed later, else a count."""
    keep = table in ("job_applications", "application_documents")
    kept: list[dict] = []
    n = 0
    offset = 0
    params_base = {"select": "*"}
    if pks:
        params_base["order"] = ",".join(f"{c}.asc" for c in pks)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        while True:
            r = api.get(f"/rest/v1/{table}", params={**params_base, "limit": PAGE, "offset": offset})
            if r.status_code not in (200, 206):
                fail(f"{table}: HTTP {r.status_code} at offset {offset}")
            rows = r.json()
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
                if keep:
                    kept.append(row)
            n += len(rows)
            if len(rows) == 0:
                break
            offset += len(rows)
    return kept if keep else n


def export_pdfs(docs: list[dict], out: Path) -> list[dict]:
    pdf_dir = out / "pdfs"
    pdf_dir.mkdir(exist_ok=True)
    seen: Counter[str] = Counter(d.get("application_id") for d in docs)
    results = []
    for d in docs:
        app_id = str(d.get("application_id"))
        name = f"{app_id}.pdf" if seen[d.get("application_id")] == 1 else f"{app_id}_{d.get('id')}.pdf"
        entry = {"document_id": d.get("id"), "application_id": app_id, "file": f"pdfs/{name}"}
        try:
            data = base64.b64decode(d.get("pdf_base64") or "", validate=True)
        except (binascii.Error, ValueError):
            entry["error"] = "invalid base64"
            results.append(entry)
            continue
        (pdf_dir / name).write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        entry.update(sha256=digest, size_bytes=len(data),
                     matches_stored_sha256=(digest == d.get("sha256")),
                     starts_with_pdf_header=data.startswith(b"%PDF"))
        results.append(entry)
    return results


def export_storage(api: ReadOnlyClient, bucket: str, out: Path) -> dict:
    r = api.get(f"/storage/v1/bucket/{quote(bucket)}")
    if r.status_code != 200:
        return {"bucket": bucket, "exists": False, "http_status": r.status_code, "files": []}
    files: list[dict] = []

    def walk(prefix: str) -> None:
        offset = 0
        while True:
            resp = api.storage_list(bucket, prefix, offset)
            if resp.status_code != 200:
                fail(f"storage list failed with HTTP {resp.status_code}")
            items = resp.json()
            for it in items:
                full = f"{prefix}{it['name']}"
                if it.get("id") is None:  # folder placeholder
                    walk(full + "/")
                else:
                    files.append({"path": full})
            if len(items) < 100:
                return
            offset += len(items)

    walk("")
    dest = out / "storage" / bucket
    for f in files:
        resp = api.get(f"/storage/v1/object/{quote(bucket)}/{quote(f['path'])}")
        if resp.status_code != 200:
            f["error"] = f"HTTP {resp.status_code}"
            continue
        target = dest / Path(*f["path"].split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(resp.content)
        f.update(file=str(target.relative_to(out)).replace("\\", "/"),
                 sha256=hashlib.sha256(resp.content).hexdigest(), size_bytes=len(resp.content))
    return {"bucket": bucket, "exists": True, "files": files}


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: export_supabase.py OUT_DIR")
    out = Path(sys.argv[1]).resolve()
    if out == REPO or REPO in out.parents:
        fail("OUT_DIR must be outside the repository")
    if out.exists() and any(out.iterdir()):
        fail(f"{out} already exists and is not empty; refusing to overwrite an export")
    env = dotenv_values(REPO / "backend" / ".env")
    url = (env.get("SUPABASE_URL") or "").rstrip("/")
    key = env.get("SUPABASE_SERVICE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        fail("SUPABASE_URL or SUPABASE_SERVICE_KEY missing from backend/.env")
    host = urlsplit(url).hostname or ""
    out.mkdir(parents=True, exist_ok=True)
    api = ReadOnlyClient(url, key)

    tables = discover_tables(api)
    missing = [t for t in EXPECTED_TABLES if t not in tables]
    manifest: dict = {
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "supabase_host": host,
        "supabase_project_ref": host.split(".")[0],
        "method": "PostgREST GET with limit/offset paging, ordered by primary key; service-role key",
        "expected_tables_missing_from_api": missing,
        "tables": {}, "pdfs": [], "storage": None, "pg_dump": None,
    }
    status_counts: Counter[str] = Counter()
    for t in sorted(tables):
        path = out / f"{t}.jsonl"
        result = export_table(api, t, tables[t], path)
        rows = len(result) if isinstance(result, list) else result
        expected = exact_count(api, t)
        manifest["tables"][t] = {
            "rows": rows, "server_exact_count": expected, "count_matches": rows == expected,
            "ordered_by": tables[t], "file": path.name, "sha256": sha256_file(path),
        }
        if t == "job_applications":
            status_counts = Counter(str(r.get("status")) for r in result)
        if t == "application_documents":
            manifest["pdfs"] = export_pdfs(result, out)

    manifest["job_applications_by_status"] = dict(sorted(status_counts.items()))
    manifest["storage"] = export_storage(api, "resumes", out)

    db_url = env.get("SUPABASE_DB_URL")
    if db_url and shutil.which("pg_dump"):
        dump = out / "public.sql"
        proc = subprocess.run(["pg_dump", "--schema=public", "--no-owner", "--no-privileges",
                               "--file", str(dump), db_url], capture_output=True)
        manifest["pg_dump"] = ({"file": dump.name, "sha256": sha256_file(dump)} if proc.returncode == 0
                               else {"error": f"pg_dump exited {proc.returncode}"})
    else:
        manifest["pg_dump"] = {"skipped": "SUPABASE_DB_URL not in backend/.env" if not db_url
                               else "pg_dump not installed"}

    t = manifest["tables"]
    manifest["totals"] = {
        "tables": len(t), "rows": sum(v["rows"] for v in t.values()),
        "count_mismatches": [k for k, v in t.items() if not v["count_matches"]],
        "pdfs": sum(1 for p in manifest["pdfs"] if "sha256" in p),
        "pdf_sha_mismatches": sum(1 for p in manifest["pdfs"] if p.get("matches_stored_sha256") is False),
        "storage_files": sum(1 for f in manifest["storage"]["files"] if "sha256" in f),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    # Summary only: names and counts.
    width = max(len(k) for k in t) if t else 10
    print(f"{'table'.ljust(width)}  rows  server")
    for k, v in sorted(t.items()):
        flag = "" if v["count_matches"] else "  MISMATCH"
        print(f"{k.ljust(width)}  {v['rows']:>4}  {v['server_exact_count']!s:>6}{flag}")
    print(f"\nmissing expected tables: {missing or 'none'}")
    print(f"job_applications: {t.get('job_applications', {}).get('rows')}  by status: {manifest['job_applications_by_status']}")
    print(f"totals: {manifest['totals']}")
    print(f"pg_dump: {manifest['pg_dump']}")
    print(f"host: {host}")

    if os.name == "nt":
        subprocess.run(["attrib", "+R", str(out / "*"), "/S", "/D"], check=True, capture_output=True)
        subprocess.run(["attrib", "+R", str(out)], check=True, capture_output=True)


if __name__ == "__main__":
    main()
