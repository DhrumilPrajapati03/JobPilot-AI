"""DM Outreach: dm_set artifacts.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-27

The SQL lives in migrations/0009_dm_outreach.sql.
"""
from pathlib import Path

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

SQL = Path(__file__).resolve().parents[1] / "0009_dm_outreach.sql"


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("Restore from a backup instead of downgrading.")
