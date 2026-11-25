"""Import the JobPilot export into the local JobDots database (plan section 5.1).

    cd backend
    python scripts/import_jobpilot.py --export D:/jobdots-archive/jobpilot-export-2026-11-24            # dry run
    python scripts/import_jobpilot.py --export D:/jobdots-archive/jobpilot-export-2026-11-24 --apply    # import
    python scripts/import_jobpilot.py --export D:/jobdots-archive/jobpilot-export-2026-11-24 --verify   # report

Uses DATABASE_URL and the owner from backend/.env (OWNER_EMAIL / OWNER_ID). The dry run
does everything in one transaction and rolls it back. Reruns are safe (idempotent).
The full report (with a 5-case spot check) is written next to the export, never into the
repo; the terminal shows counts only.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import legacy_import  # noqa: E402


def ollama_embedder():
    from app.services.llm import OllamaEmbeddings
    emb = OllamaEmbeddings()
    emb.embed_query("probe")  # fail early when Ollama is down

    def embed(text):
        return emb.embed_query(text), settings.OLLAMA_EMBED_MODEL
    return embed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--export", required=True, type=Path, help="export folder with manifest.json")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="commit the import (default: dry run)")
    mode.add_argument("--verify", action="store_true", help="compare the database with the export")
    parser.add_argument("--no-embed", action="store_true", help="skip answer-bank embeddings (Ollama)")
    args = parser.parse_args()
    if not settings.DATABASE_URL:
        print("DATABASE_URL is not set (backend/.env).")
        return 2
    from app.services.auth import owner_identity
    owner_id, _ = owner_identity()
    url = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with psycopg.connect(url) as conn:
        if args.verify:
            result = legacy_import.verify(conn, args.export, owner_id)
            out = args.export.parent / f"import-verify-{stamp}.json"
            out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
            for c in result["counts"]:
                print(f"  {'ok ' if c['ok'] else 'BAD'} {c['table']:<20} source {c['source']:>5}  imported {c['imported']:>5}")
            print(f"  {'ok ' if result['stages']['ok'] else 'BAD'} stages expected {result['stages']['expected']} imported {result['stages']['imported']}")
            print(f"  {'ok ' if result['legacy_actions'] == 0 else 'BAD'} approvable legacy drafts: {result['legacy_actions']}")
            print(f"Verification {'PASSED' if result['ok'] else 'FAILED'}. Full report with a 5-case spot check: {out}")
            return 0 if result["ok"] else 1
        embed = None
        if not args.no_embed:
            try:
                embed = ollama_embedder()
            except Exception:
                print("Ollama is not reachable; answers are imported without embeddings (rerun later to add them).")
        report = legacy_import.run_import(conn, args.export, owner_id, dry_run=not args.apply, embed=embed)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    out = args.export.parent / f"import-{'apply' if args.apply else 'dryrun'}-{stamp}.json"
    out.write_text(json.dumps(report.as_dict(), indent=2, default=str), encoding="utf-8")
    for key, n in report.as_dict()["inserted_this_run"].items():
        print(f"  {key:<45} {n:>5} new")
    for name, why in report.skipped.items():
        print(f"  skipped {name}: {why}")
    for note in report.notes:
        print(f"  note: {note}")
    print(("Imported and committed." if args.apply else "Dry run: nothing was saved.") + f" Report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
