-- JobPilot AI: supervised autopilot — prepared application forms, the Chrome extension,
-- and the daily schedule (scan + morning digest). Run after the earlier migrations. Safe to re-run.

-- Answers prepared overnight for each application's form (fields, values, flags).
alter table public.job_applications add column if not exists prepared_form jsonb;

-- Personal tokens for the Chrome extension. Only a SHA-256 hash is stored.
create table if not exists public.extension_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  token_hash text not null unique,
  label text not null default 'Chrome extension',
  created_at timestamptz not null default now(),
  last_used_at timestamptz
);

-- When the daily scan and digest last ran for each user.
create table if not exists public.autopilot_state (
  user_id uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  last_scan_on date,
  last_scan_at timestamptz,
  last_digest_on date,
  last_digest_at timestamptz,
  last_digest_error text,
  updated_at timestamptz not null default now()
);

alter table public.extension_tokens enable row level security;
alter table public.autopilot_state enable row level security;

do $$
declare t text;
begin
  foreach t in array array['extension_tokens', 'autopilot_state'] loop
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
