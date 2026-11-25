"""Resume section embeddings in pgvector (replaces the local Chroma store).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-25
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UP = """
create table public.resume_sections (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  model text not null,                 -- embedding model; vectors from different models never mix
  source_digest text not null,         -- digest of the base resume these rows were built from
  section_type text not null,
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  embedding vector not null,
  created_at timestamptz not null default now()
);
create index resume_sections_owner_model_idx on public.resume_sections (user_id, model);
"""


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(UP)


def downgrade() -> None:
    op.get_bind().connection.driver_connection.execute("drop table public.resume_sections;")
