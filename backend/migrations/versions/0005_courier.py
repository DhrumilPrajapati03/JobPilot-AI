"""Courier: encrypted connections (Gmail), Telegram state and approval messages, courier runs.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-26

The SQL lives in migrations/0005_courier.sql.
"""
from pathlib import Path

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

SQL = Path(__file__).resolve().parents[1] / "0005_courier.sql"


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("Restore from a backup instead of downgrading.")
