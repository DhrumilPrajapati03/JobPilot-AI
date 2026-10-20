-- JobPilot AI: dedicated columns for generated application materials.
-- Run once in the Supabase SQL editor. Until it runs, the backend keeps
-- storing these drafts inside job_applications.notes (see app/services/materials.py).

alter table public.job_applications
  add column if not exists cover_letter text not null default '',
  add column if not exists linkedin_dm jsonb not null default '{}'::jsonb,
  add column if not exists follow_up_at timestamptz,
  add column if not exists applied_at timestamptz,
  add column if not exists updated_at timestamptz not null default now();

alter table public.cold_emails
  add column if not exists sent_at timestamptz,
  add column if not exists replied boolean not null default false;

create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists job_applications_set_updated_at on public.job_applications;
create trigger job_applications_set_updated_at
  before update on public.job_applications
  for each row execute function public.set_updated_at();
