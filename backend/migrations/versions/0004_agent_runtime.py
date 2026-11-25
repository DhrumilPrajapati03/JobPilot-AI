"""Agent runtime: agent_spec, run_step traces, routines, job_case.posting_id, 'agent' runs.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-25

The SQL lives in migrations/0004_agent_runtime.sql.
"""
from pathlib import Path

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SQL = Path(__file__).resolve().parents[1] / "0004_agent_runtime.sql"


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("Restore from a backup instead of downgrading.")
