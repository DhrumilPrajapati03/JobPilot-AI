"""Connector and the LinkedIn queue: invite_set artifacts, queue index.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-27

The SQL lives in migrations/0007_connector.sql.
"""
from pathlib import Path

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

SQL = Path(__file__).resolve().parents[1] / "0007_connector.sql"


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("Restore from a backup instead of downgrading.")
