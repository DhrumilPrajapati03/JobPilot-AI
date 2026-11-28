"""Custom experts: note artifacts.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-27

The SQL lives in migrations/0010_custom_experts.sql.
"""
from pathlib import Path

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

SQL = Path(__file__).resolve().parents[1] / "0010_custom_experts.sql"


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("Restore from a backup instead of downgrading.")
