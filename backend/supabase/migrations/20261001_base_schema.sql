-- Fresh Supabase baseline. Apply BEFORE all other migrations, using an admin
-- SQL connection. Existing tables/data are retained; this is not an upgrade
-- reconciler for an arbitrary pre-existing schema or its older policies.

create table if not exists public.user_profiles (
  id uuid primary key default auth.uid() references auth.users(id) on delete cascade,
  name text not null default '', headline text not null default '',
  location text not null default '', salary_range text not null default '',
  linkedin_url text not null default '', work_preferences jsonb not null default '{}',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.resumes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  version text not null default 'base', name text not null default '',
  headline text not null default '', summary text not null default '',
  experience jsonb not null default '[]', skills jsonb not null default '{"primary":[],"secondary":[]}',
  projects jsonb not null default '[]', education jsonb not null default '[]',
  certifications jsonb not null default '[]',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(user_id, version)
);

create table if not exists public.job_applications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  company text not null default '', role text not null default '',
  jd_url text not null default '', jd_text text not null default '', jd_analysis jsonb,
  status text not null default 'saved' check (status in ('saved','applied','interviewing','offer','rejected','archived')),
  source text not null default 'manual', notes text not null default '',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists job_applications_user_created_idx on public.job_applications(user_id, created_at desc);

create table if not exists public.tailored_resumes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  application_id uuid not null references public.job_applications(id) on delete cascade,
  version integer not null default 1, content jsonb not null default '{}',
  pdf_url text not null default '', keyword_match_score numeric not null default 0,
  missing_keywords jsonb not null default '[]',
  generated_at timestamptz not null default now(), created_at timestamptz not null default now(),
  unique(application_id, version)
);

create table if not exists public.cold_emails (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  application_id uuid not null references public.job_applications(id) on delete cascade,
  to_email text not null default '', to_name text not null default '',
  subject text not null default '', body text not null default '', sequence_number integer not null default 1,
  opened boolean not null default false, opened_at timestamptz, replied_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists cold_emails_application_idx on public.cold_emails(application_id);

alter table public.user_profiles enable row level security;
alter table public.resumes enable row level security;
alter table public.job_applications enable row level security;
alter table public.tailored_resumes enable row level security;
alter table public.cold_emails enable row level security;

drop policy if exists profiles_owner on public.user_profiles;
create policy profiles_owner on public.user_profiles to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

do $$
declare t text;
begin
  foreach t in array array['resumes','job_applications'] loop
    execute format('drop policy if exists baseline_owner on public.%I', t);
    execute format('create policy baseline_owner on public.%I to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid())', t);
  end loop;
end $$;

drop policy if exists tailored_owner on public.tailored_resumes;
create policy tailored_owner on public.tailored_resumes to authenticated
  using (user_id = auth.uid() and exists (
    select 1 from public.job_applications a where a.id = application_id and a.user_id = auth.uid()
  )) with check (user_id = auth.uid() and exists (
    select 1 from public.job_applications a where a.id = application_id and a.user_id = auth.uid()
  ));
-- cold_emails ownership policies are created by 20261010_cold_emails_rls.sql.

grant usage on schema public to authenticated, service_role;
grant select, insert, update, delete on public.user_profiles, public.resumes,
  public.job_applications, public.tailored_resumes, public.cold_emails to authenticated, service_role;

insert into storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
values ('resumes', 'resumes', false, 10485760,
        array['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document'])
on conflict (id) do nothing;

drop policy if exists resume_objects_owner on storage.objects;
create policy resume_objects_owner on storage.objects to authenticated
  using (bucket_id = 'resumes' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'resumes' and (storage.foldername(name))[1] = auth.uid()::text);
