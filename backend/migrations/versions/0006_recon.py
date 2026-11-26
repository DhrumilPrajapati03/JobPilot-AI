"""Recon and the contacts CRM: contact provenance, LinkedIn identity, do-not-contact.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-26

The SQL lives in migrations/0006_recon.sql.
"""
from pathlib import Path

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

SQL = Path(__file__).resolve().parents[1] / "0006_recon.sql"


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("Restore from a backup instead of downgrading.")
