-- Confirmation is self-attestation of a saved resume snapshot, not an
-- independent credential/background check. Content is always re-derived.
create table public.identity_confirmations (
  user_id uuid not null references auth.users(id) on delete cascade,
  fact_id text not null check (fact_id ~ '^[0-9a-f]{64}$'),
  source_digest text not null check (source_digest ~ '^[0-9a-f]{64}$'),
  confirmed_at timestamptz not null default now(),
  primary key(user_id,source_digest,fact_id)
);
alter table public.identity_confirmations enable row level security;
revoke all on public.identity_confirmations from anon,authenticated;
grant select,insert,delete on public.identity_confirmations to authenticated;
grant all on public.identity_confirmations to service_role;
create policy identity_owner_read on public.identity_confirmations for select to authenticated using (user_id=(select auth.uid()));
create policy identity_owner_confirm on public.identity_confirmations for insert to authenticated with check (user_id=(select auth.uid()));
create policy identity_owner_revoke on public.identity_confirmations for delete to authenticated using (user_id=(select auth.uid()));

alter table public.job_postings add column matching_details jsonb not null default '{}';
alter table public.job_postings add column dedupe_key text not null default '';
-- Old rows remain untouched; do not delete or merge existing user applications.
create unique index job_postings_owner_identity_idx on public.job_postings(user_id,dedupe_key) where dedupe_key<>'';
