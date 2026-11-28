"""Hardening: Telegram alerts.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-27

The SQL lives in migrations/0011_alerts.sql.
"""
from pathlib import Path

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

SQL = Path(__file__).resolve().parents[1] / "0011_alerts.sql"


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("Restore from a backup instead of downgrading.")
