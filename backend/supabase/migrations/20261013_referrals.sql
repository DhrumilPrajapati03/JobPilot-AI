-- JobPilot AI: referral first — the people you know, and referral requests per application.
-- Run once in the Supabase SQL editor (after the earlier migrations). Safe to re-run.

-- People in your network: imported from LinkedIn's Connections.csv or added by hand.
create table if not exists public.network_contacts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  full_name text not null,
  first_name text not null default '',
  last_name text not null default '',
  email text not null default '',
  linkedin_url text not null default '',
  company text not null default '',
  company_key text not null default '',  -- normalised company name used for matching
  position text not null default '',
  connected_on date,
  source text not null default 'manual' check (source in ('linkedin', 'manual')),
  notes text not null default '',
  dedupe_key text not null,  -- LinkedIn URL, else email, else name + company
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, dedupe_key)
);

create index if not exists network_contacts_user_company_idx on public.network_contacts (user_id, company_key);

-- A referral request to one contact for one application. Nothing is sent by JobPilot:
-- you send the message yourself and record what happened.
create table if not exists public.referral_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  application_id uuid not null references public.job_applications (id) on delete cascade,
  contact_id uuid not null references public.network_contacts (id) on delete cascade,
  status text not null default 'drafted' check (status in ('drafted', 'sent', 'referred', 'declined', 'no_reply')),
  message text not null default '',
  sent_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (application_id, contact_id)
);

alter table public.network_contacts enable row level security;
alter table public.referral_requests enable row level security;

-- Also defined by earlier migrations; repeated so this file runs on its own.
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

do $$
declare t text;
begin
  foreach t in array array['network_contacts', 'referral_requests'] loop
    execute format('drop policy if exists "%1$s_select_own" on public.%1$s', t);
    execute format('create policy "%1$s_select_own" on public.%1$s for select using (auth.uid() = user_id)', t);
    execute format('drop policy if exists "%1$s_insert_own" on public.%1$s', t);
    execute format('create policy "%1$s_insert_own" on public.%1$s for insert with check (auth.uid() = user_id)', t);
    execute format('drop policy if exists "%1$s_update_own" on public.%1$s', t);
    execute format('create policy "%1$s_update_own" on public.%1$s for update using (auth.uid() = user_id) with check (auth.uid() = user_id)', t);
    execute format('drop policy if exists "%1$s_delete_own" on public.%1$s', t);
    execute format('create policy "%1$s_delete_own" on public.%1$s for delete using (auth.uid() = user_id)', t);
    execute format('drop trigger if exists %1$s_set_updated_at on public.%1$s', t);
    execute format('create trigger %1$s_set_updated_at before update on public.%1$s for each row execute function public.set_updated_at()', t);
  end loop;
end $$;
