-- Immutable document snapshots and append-only browser observations.
-- An observation is not an independently verified employer receipt.
create table public.application_documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  application_id uuid not null references public.job_applications(id) on delete no action deferrable initially deferred,
  resume_version integer not null,
  name text not null,
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes integer not null check (size_bytes between 5 and 2097152),
  pdf_base64 text not null check (length(pdf_base64) <= 2796204),
  created_at timestamptz not null default clock_timestamp(),
  unique(id,user_id)
);
create index application_documents_owner_app on public.application_documents(user_id,application_id);
create index application_documents_app on public.application_documents(application_id);

create table public.application_execution_sessions (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  application_id uuid not null references public.job_applications(id) on delete no action deferrable initially deferred,
  page_url text not null check (length(page_url) <= 2000),
  link_method text not null check (link_method in ('url_match','user_confirmed','manual_report')),
  document_id uuid,
  created_at timestamptz not null default clock_timestamp(),
  expires_at timestamptz not null default (clock_timestamp()+interval '24 hours'),
  unique(id,user_id),
  foreign key(document_id,user_id) references public.application_documents(id,user_id)
);
create index application_sessions_owner_app on public.application_execution_sessions(user_id,application_id,created_at desc);
create index application_sessions_app on public.application_execution_sessions(application_id);
create index application_sessions_document on public.application_execution_sessions(document_id,user_id);

create table public.application_events (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  session_id uuid not null,
  kind text not null check (kind in ('form_prepared','submission_attempted','submission_confirmation_observed','user_reported_submitted')),
  request_key uuid not null,
  details jsonb not null default '{}' check (jsonb_typeof(details)='object' and octet_length(details::text)<=65536),
  created_at timestamptz not null default clock_timestamp(),
  foreign key(session_id,user_id) references public.application_execution_sessions(id,user_id) on delete cascade,
  unique(session_id,request_key)
);
create index application_events_owner_session on public.application_events(user_id,session_id,id);

alter table public.application_documents enable row level security;
alter table public.application_execution_sessions enable row level security;
alter table public.application_events enable row level security;
revoke all on public.application_documents,public.application_execution_sessions,public.application_events from anon,authenticated;
grant select(id,user_id,application_id,resume_version,name,sha256,size_bytes,created_at) on public.application_documents to authenticated;
grant select on public.application_execution_sessions,public.application_events to authenticated;
grant all on public.application_documents,public.application_execution_sessions,public.application_events to service_role;
grant usage,select on sequence public.application_events_id_seq to service_role;
create policy application_documents_owner on public.application_documents for select to authenticated using ((select auth.uid())=user_id);
create policy application_sessions_owner on public.application_execution_sessions for select to authenticated using ((select auth.uid())=user_id);
create policy application_events_owner on public.application_events for select to authenticated using ((select auth.uid())=user_id);

create function public.create_application_session(p_user_id uuid,p_id uuid,p_application_id uuid,p_page_url text,p_link_method text,p_document jsonb default null)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.application_execution_sessions; doc uuid;
begin
  perform 1 from public.job_applications where id=p_application_id and user_id=p_user_id for update;
  if not found then raise exception 'execution_not_found'; end if;
  select * into s from public.application_execution_sessions where id=p_id;
  if found then
    if s.user_id<>p_user_id or s.application_id<>p_application_id or s.page_url<>p_page_url then raise exception 'execution_conflict'; end if;
    if s.expires_at<=clock_timestamp() then raise exception 'execution_expired'; end if;
    return to_jsonb(s);
  end if;
  if p_document is not null then
    insert into public.application_documents(user_id,application_id,resume_version,name,sha256,size_bytes,pdf_base64)
    values(p_user_id,p_application_id,(p_document->>'resume_version')::integer,p_document->>'name',p_document->>'sha256',
      (p_document->>'size_bytes')::integer,p_document->>'pdf_base64') returning id into doc;
  end if;
  insert into public.application_execution_sessions(id,user_id,application_id,page_url,link_method,document_id)
    values(p_id,p_user_id,p_application_id,p_page_url,p_link_method,doc) returning * into s;
  return to_jsonb(s);
end $$;

create function public.append_application_event(p_user_id uuid,p_session_id uuid,p_kind text,p_key uuid,p_details jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.application_execution_sessions; e public.application_events; a public.job_applications; attempt public.application_events;
begin
  -- Consistent lock order with session creation / other reports for the same app.
  select j.* into a from public.job_applications j join public.application_execution_sessions x on x.application_id=j.id
    where x.id=p_session_id and x.user_id=p_user_id and j.user_id=p_user_id for update of j;
  if not found then raise exception 'execution_not_found'; end if;
  select * into s from public.application_execution_sessions where id=p_session_id and user_id=p_user_id for update;
  select * into e from public.application_events where session_id=s.id and request_key=p_key;
  if found then
    if e.kind<>p_kind or e.details<>p_details then raise exception 'execution_conflict'; end if;
    return to_jsonb(e);
  end if;
  if s.expires_at<=clock_timestamp() then raise exception 'execution_expired'; end if;
  if p_kind='submission_attempted' and not exists(select 1 from public.application_events where session_id=s.id and kind='form_prepared') then
    raise exception 'execution_preparation_required';
  end if;
  if p_kind='submission_confirmation_observed' then
    select * into attempt from public.application_events where session_id=s.id and kind='submission_attempted'
      and request_key=(p_details->>'attempt_key')::uuid;
    if not found or attempt.created_at<clock_timestamp()-interval '15 minutes' then raise exception 'execution_attempt_required'; end if;
    if exists(select 1 from public.application_events where session_id=s.id and kind=p_kind and details->>'attempt_key'=p_details->>'attempt_key') then
      raise exception 'execution_conflict';
    end if;
  end if;
  if p_kind='user_reported_submitted' then
    if a.status not in ('saved','applied') then raise exception 'execution_status_conflict'; end if;
    update public.job_applications set status='applied',applied_at=coalesce(applied_at,clock_timestamp()),
      follow_up_at=coalesce(follow_up_at,clock_timestamp()+interval '5 days') where id=a.id and user_id=p_user_id;
  end if;
  insert into public.application_events(user_id,session_id,kind,request_key,details)
    values(p_user_id,s.id,p_kind,p_key,p_details) returning * into e;
  return to_jsonb(e);
end $$;
revoke all on function public.create_application_session(uuid,uuid,uuid,text,text,jsonb) from public,anon,authenticated;
revoke all on function public.append_application_event(uuid,uuid,text,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.create_application_session(uuid,uuid,uuid,text,text,jsonb) to service_role;
grant execute on function public.append_application_event(uuid,uuid,text,uuid,jsonb) to service_role;
