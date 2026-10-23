"""Emit an ordered, transactional bootstrap for a fresh Supabase project.

Usage: python scripts/database_bundle.py --output supabase/bootstrap.generated.sql
Apply the generated SQL in Supabase's SQL editor; credentials are never needed
to build the bundle. PostgreSQL plus Supabase Auth/Storage schemas are required.
"""
import argparse
from pathlib import Path


def bundle() -> str:
    migrations = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
    sections = ["-- Generated from versioned migrations. Review before applying.\nBEGIN;"]
    for path in sorted(migrations.glob("*.sql")):
        sections.append(f"\n-- BEGIN {path.name}\n{path.read_text(encoding='utf-8')}")
    sections.append("COMMIT;\n")
    return "\n".join(sections)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        args.output.write_text(bundle(), encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(bundle())
