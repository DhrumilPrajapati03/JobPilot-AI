"""Baseline: legacy JobPilot schema without Supabase auth, RLS or grants.

Revision ID: 0001
Revises:
Create Date: 2026-11-25

The SQL lives in migrations/0001_baseline.sql (see its header for how it was made).
"""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL = Path(__file__).resolve().parents[1] / "0001_baseline.sql"


def upgrade() -> None:
    # Run on the raw psycopg connection: the file holds many statements and
    # dollar-quoted bodies, which must not go through SQLAlchemy's bind-param parsing.
    op.get_bind().connection.driver_connection.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("The baseline cannot be downgraded; restore from a backup instead.")
