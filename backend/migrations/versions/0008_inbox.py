"""Inbox: handled Gmail messages, LinkedIn acceptances, interval routines.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-27

The SQL lives in migrations/0008_inbox.sql.
"""
from pathlib import Path

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

SQL = Path(__file__).resolve().parents[1] / "0008_inbox.sql"


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("Restore from a backup instead of downgrading.")
