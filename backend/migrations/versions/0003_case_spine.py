"""Case spine: job_case, case_event, artifact, action/approval state machine, budgets,
contacts, answer bank, login identities and sessions, legacy import, backup log, eval
results, and per-case queue concurrency (replaces the one-run-per-user lock).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-25

The SQL lives in migrations/0003_case_spine.sql.
"""
from pathlib import Path

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SQL = Path(__file__).resolve().parents[1] / "0003_case_spine.sql"


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("Restore from a backup instead of downgrading the spine.")
