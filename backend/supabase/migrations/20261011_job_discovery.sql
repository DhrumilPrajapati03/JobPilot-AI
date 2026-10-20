-- JobPilot AI: job discovery from public Greenhouse / Lever / Ashby job boards.
-- Run once in the Supabase SQL editor. Safe to re-run.

-- Company job boards the user follows.
create table if not exists public.job_sources (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  ats text not null check (ats in ('greenhouse', 'lever', 'ashby')),
  slug text not null,
  company text not null default '',
  enabled boolean not null default true,
  job_count integer not null default 0,
  last_scanned_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  unique (user_id, ats, slug)
);

-- Postings found on those boards, scored against the user's resume and preferences.
create table if not exists public.job_postings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  source_id uuid references public.job_sources (id) on delete cascade,
  ats text not null,
  external_id text not null,
  company text not null default '',
  title text not null default '',
  location text not null default '',
  remote boolean,
  url text not null default '',
  description text not null default '',
  posted_at timestamptz,
  fit_score numeric not null default 0,
  title_match numeric not null default 0,
  matched_skills jsonb not null default '[]'::jsonb,
  missing_skills jsonb not null default '[]'::jsonb,
  skip_flags jsonb not null default '[]'::jsonb,
  -- new → (dismissed | drafting → drafted); skipped = breaks a skip rule
  status text not null default 'new' check (status in ('new', 'dismissed', 'skipped', 'drafting', 'drafted')),
  application_id uuid references public.job_applications (id) on delete set null,
  auto_drafted boolean not null default false,
  drafted_at timestamptz,
  closed_at timestamptz,  -- set when the posting disappears from the board
  discovered_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, ats, external_id)
);

create index if not exists job_postings_user_status_idx on public.job_postings (user_id, status, fit_score desc);

alter table public.job_sources enable row level security;
alter table public.job_postings enable row level security;

-- Also defined by earlier migrations; repeated so this file runs on its own.
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists job_postings_set_updated_at on public.job_postings;
create trigger job_postings_set_updated_at
  before update on public.job_postings
  for each row execute function public.set_updated_at();

do $$
declare t text;
begin
  foreach t in array array['job_sources', 'job_postings'] loop
    execute format('drop policy if exists "%1$s_select_own" on public.%1$s', t);
    execute format('create policy "%1$s_select_own" on public.%1$s for select using (auth.uid() = user_id)', t);
    execute format('drop policy if exists "%1$s_insert_own" on public.%1$s', t);
    execute format('create policy "%1$s_insert_own" on public.%1$s for insert with check (auth.uid() = user_id)', t);
    execute format('drop policy if exists "%1$s_update_own" on public.%1$s', t);
    execute format('create policy "%1$s_update_own" on public.%1$s for update using (auth.uid() = user_id) with check (auth.uid() = user_id)', t);
    execute format('drop policy if exists "%1$s_delete_own" on public.%1$s', t);
    execute format('create policy "%1$s_delete_own" on public.%1$s for delete using (auth.uid() = user_id)', t);
  end loop;
end $$;
