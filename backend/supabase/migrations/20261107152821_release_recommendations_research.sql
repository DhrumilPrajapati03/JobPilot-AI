-- Release additions. Existing application/profile data is not rewritten.
alter table public.agent_runs drop constraint if exists agent_runs_kind_check;
alter table public.agent_runs add constraint agent_runs_kind_check
  check (kind in ('application','scan','digest','mail_send','mail_sync','company_research','recommendation'));
create unique index if not exists job_postings_id_owner_release_idx on public.job_postings(id,user_id);
create unique index if not exists job_applications_id_owner_release_idx on public.job_applications(id,user_id);

create table public.recommendation_runs (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  request_key uuid not null, model_version text not null, profile_digest text not null,
  items jsonb not null check (jsonb_typeof(items)='array' and jsonb_array_length(items) between 1 and 100),
  created_at timestamptz not null default now(), unique(user_id,request_key), unique(id,user_id)
);
create index recommendation_runs_owner_created_idx on public.recommendation_runs(user_id,created_at desc);
create table public.recommendation_impressions (
  id uuid primary key default gen_random_uuid(), user_id uuid not null,
  run_id uuid not null, posting_id uuid not null, request_key uuid not null,
  position integer not null check(position between 1 and 100),
  visible_ms integer not null check(visible_ms between 500 and 60000),
  created_at timestamptz not null default now(), unique(user_id,request_key), unique(run_id,posting_id),
  foreign key(run_id,user_id) references public.recommendation_runs(id,user_id) on delete cascade,
  foreign key(posting_id,user_id) references public.job_postings(id,user_id) on delete cascade
);
create index recommendation_impressions_owner_idx on public.recommendation_impressions(user_id,created_at desc);
create index recommendation_impressions_posting_idx on public.recommendation_impressions(posting_id,user_id);
create table public.recommendation_feedback (
  user_id uuid not null, posting_id uuid not null,
  signal text not null check(signal in ('interested','not_relevant')),
  reason text check(reason in ('wrong_role','location','seniority','skills','other')),
  updated_at timestamptz not null default now(), primary key(user_id,posting_id),
  foreign key(posting_id,user_id) references public.job_postings(id,user_id) on delete cascade,
  check(signal='not_relevant' or reason is null)
);
create index recommendation_feedback_posting_idx on public.recommendation_feedback(posting_id,user_id);
create table public.company_research (
  run_id uuid primary key, user_id uuid not null, application_id uuid not null,
  company text not null, sources jsonb not null check(jsonb_typeof(sources)='array' and jsonb_array_length(sources)<=3),
  warnings jsonb not null default '[]', created_at timestamptz not null default now(),
  foreign key(run_id,user_id) references public.agent_runs(id,user_id) on delete cascade,
  foreign key(application_id,user_id) references public.job_applications(id,user_id) on delete cascade
);
create index company_research_owner_app_idx on public.company_research(user_id,application_id,created_at desc);
create table public.writing_templates (
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  kind text not null check(kind in ('email','dm','cover_letter')),
  content text not null check(length(content)<=10000), updated_at timestamptz not null default now(),
  primary key(user_id,kind)
);
alter table public.writing_templates enable row level security;
create policy template_owner on public.writing_templates for all to authenticated
  using(user_id=(select auth.uid())) with check(user_id=(select auth.uid()));
revoke all on public.writing_templates from public,anon,authenticated;
grant select,insert,update,delete on public.writing_templates to authenticated;
grant all on public.writing_templates to service_role;
create table public.usage_windows (
  user_id uuid not null references auth.users(id) on delete cascade, bucket text not null,
  window_start timestamptz not null, used integer not null check(used>=0), primary key(user_id,bucket,window_start)
);
create table public.usage_receipts (
  user_id uuid not null references auth.users(id) on delete cascade, bucket text not null,
  request_key text not null, created_at timestamptz not null default now(), primary key(user_id,bucket,request_key)
);

do $$ declare t text; begin
  foreach t in array array['recommendation_runs','recommendation_impressions','recommendation_feedback','company_research'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('create policy owner_read on public.%I for select to authenticated using (user_id=(select auth.uid()))',t);
    execute format('revoke all on public.%I from public,anon,authenticated',t);
    execute format('grant select on public.%I to authenticated',t);
    execute format('grant all on public.%I to service_role',t);
  end loop;
end $$;
alter table public.usage_windows enable row level security;
alter table public.usage_receipts enable row level security;
revoke all on public.usage_windows,public.usage_receipts from public,anon,authenticated;
grant all on public.usage_windows,public.usage_receipts to service_role;

create function public.reserve_release_usage(p_user_id uuid,p_bucket text,p_key text,p_limit integer,p_seconds integer default 86400)
returns boolean language plpgsql security invoker set search_path='' as $$
declare w timestamptz; n integer;
begin
  if p_limit<1 or p_seconds not between 60 and 86400 or length(p_key) not between 1 and 200 or length(p_bucket)>40 then raise exception 'invalid_budget'; end if;
  -- Serialize same-user reservations including idempotent receipt creation.
  perform pg_advisory_xact_lock(hashtextextended(p_user_id::text||p_bucket,0));
  if exists(select 1 from public.usage_receipts where user_id=p_user_id and bucket=p_bucket and request_key=p_key) then return true; end if;
  w := to_timestamp(floor(extract(epoch from clock_timestamp())/p_seconds)*p_seconds);
  insert into public.usage_windows values(p_user_id,p_bucket,w,1)
    on conflict(user_id,bucket,window_start) do update set used=public.usage_windows.used+1
    where public.usage_windows.used<p_limit returning used into n;
  if n is null then return false; end if;
  insert into public.usage_receipts(user_id,bucket,request_key) values(p_user_id,p_bucket,p_key);
  return true;
end $$;

create function public.record_recommendation_impression(p_user_id uuid,p_run_id uuid,p_posting_id uuid,p_key uuid,p_position integer,p_visible_ms integer)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare r public.recommendation_impressions;
begin
  if not exists(select 1 from public.recommendation_runs q, jsonb_array_elements(q.items) item
    where q.id=p_run_id and q.user_id=p_user_id and item->>'posting_id'=p_posting_id::text and (item->>'position')::integer=p_position)
    then raise exception 'recommendation_not_found'; end if;
  insert into public.recommendation_impressions(user_id,run_id,posting_id,request_key,position,visible_ms)
    values(p_user_id,p_run_id,p_posting_id,p_key,p_position,p_visible_ms) on conflict do nothing returning * into r;
  if r.id is null then
    select * into r from public.recommendation_impressions where user_id=p_user_id and run_id=p_run_id and posting_id=p_posting_id;
    if r.id is null then raise exception 'idempotency_key_conflict'; end if;
  end if;
  return jsonb_build_object('recorded',true);
end $$;

create function public.save_company_research(p_run_id uuid,p_token uuid,p_application_id uuid,p_company text,p_sources jsonb,p_warnings jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare u uuid;
begin
  select user_id into u from public.agent_runs where id=p_run_id and lease_token=p_token and status='running' and lease_expires_at>clock_timestamp() for update;
  if u is null then raise exception 'lease_lost'; end if;
  if not exists(select 1 from public.agent_runs where id=p_run_id and kind='company_research' and inputs->>'application_id'=p_application_id::text)
    then raise exception 'research_input_mismatch'; end if;
  insert into public.company_research(run_id,user_id,application_id,company,sources,warnings)
    values(p_run_id,u,p_application_id,p_company,p_sources,p_warnings) on conflict(run_id) do nothing;
  return jsonb_build_object('application_id',p_application_id,'research_id',p_run_id);
end $$;

-- Every new RPC is service-only; JWT clients read their own rows through RLS.
revoke all on function public.reserve_release_usage(uuid,text,text,integer,integer),
  public.record_recommendation_impression(uuid,uuid,uuid,uuid,integer,integer),
  public.save_company_research(uuid,uuid,uuid,text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.reserve_release_usage(uuid,text,text,integer,integer),
  public.record_recommendation_impression(uuid,uuid,uuid,uuid,integer,integer),
  public.save_company_research(uuid,uuid,uuid,text,jsonb,jsonb) to service_role;

create function public.prune_release_telemetry(p_before timestamptz)
returns void language plpgsql security invoker set search_path='' as $$
begin
  if p_before>now()-interval '30 days' then raise exception 'minimum_retention_30_days'; end if;
  delete from public.recommendation_runs where created_at<p_before;
  delete from public.usage_receipts where created_at<p_before;
  delete from public.usage_windows where window_start<p_before;
end $$;
revoke all on function public.prune_release_telemetry(timestamptz) from public,anon,authenticated;
grant execute on function public.prune_release_telemetry(timestamptz) to service_role;

create function public.release_schema_ready() returns boolean language sql security invoker set search_path='' as $$
 select to_regclass('public.recommendation_runs') is not null and to_regclass('public.company_research') is not null
   and to_regclass('public.writing_templates') is not null and to_regclass('public.usage_windows') is not null;
$$;
revoke all on function public.release_schema_ready() from public,anon,authenticated;
grant execute on function public.release_schema_ready() to service_role;

-- Strict production API checks a signed JWT's session before serving private data.
-- The auth schema stays outside the Data API. Only these columns are granted.
grant select(id,user_id,not_after) on auth.sessions to service_role;
create function public.jobpilot_session_active(p_user_id uuid,p_session_id uuid)
returns boolean language sql stable security invoker set search_path='' as $$
 select exists(select 1 from auth.sessions where id=p_session_id and user_id=p_user_id
   and (not_after is null or not_after>now()));
$$;
revoke all on function public.jobpilot_session_active(uuid,uuid) from public,anon,authenticated;
grant execute on function public.jobpilot_session_active(uuid,uuid) to service_role;
