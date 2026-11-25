-- JobDots baseline schema (Alembic revision 0001).
--
-- Generated on 25 Nov 2026 from the 19 legacy JobPilot Supabase migrations
-- (kept on branch legacy/jobpilot-v1, supabase/migrations/), applied to Postgres 17
-- and dumped with pg_dump --schema-only. Then, for a single-owner local database:
--   * Row Level Security, policies, grants and the anon/authenticated/service_role
--     roles are removed. The API enforces ownership; there is one owner.
--   * Supabase's auth schema is replaced by a minimal local one: auth.users holds
--     the owner, and auth.uid() reads the per-transaction setting app.user_id,
--     which the database layer sets. Functions and column defaults that used
--     auth.uid() keep working unchanged.
--   * jobpilot_session_active() (Supabase session guard) is dropped.
-- Do not edit; add new Alembic revisions instead.

-- pg_dump order creates functions before the tables they reference; skip body
-- validation for this transaction only (the bodies are checked at first call).
set local check_function_bodies = false;

create extension if not exists pgcrypto;
create extension if not exists vector;

create schema if not exists auth;

create table auth.users (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  created_at timestamptz not null default now()
);

create function auth.uid() returns uuid
  language sql stable
  as $$ select nullif(current_setting('app.user_id', true), '')::uuid $$;

-- FUNCTION: append_agent_run_event(uuid, uuid, jsonb)
CREATE FUNCTION public.append_agent_run_event(p_run_id uuid, p_token uuid, p_event jsonb) RETURNS bigint
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
declare r public.agent_runs; event_id bigint;
begin
  select * into r from public.agent_runs where id=p_run_id and lease_token=p_token
    and status='running' and lease_expires_at>clock_timestamp() for update;
  if not found then raise exception 'lease_lost'; end if;
  insert into public.agent_run_events(run_id,user_id,event) values(r.id,r.user_id,p_event) returning id into event_id;
  return event_id;
end $$;

-- FUNCTION: append_application_event(uuid, uuid, text, uuid, jsonb)
CREATE FUNCTION public.append_application_event(p_user_id uuid, p_session_id uuid, p_kind text, p_key uuid, p_details jsonb) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
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

-- FUNCTION: begin_mail_send(uuid, uuid, uuid)
CREATE FUNCTION public.begin_mail_send(p_run_id uuid, p_token uuid, p_message_id uuid) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
declare r public.agent_runs; m public.outreach_messages; c public.mail_connections;
begin
  select * into r from public.agent_runs where id=p_run_id and lease_token=p_token and status='running' and lease_expires_at>clock_timestamp() and kind='mail_send' for update;
  if not found then raise exception 'lease_lost'; end if;
  select * into m from public.outreach_messages where id=p_message_id and user_id=r.user_id for update;
  if not found or m.run_id is distinct from r.id then raise exception 'mail_not_found'; end if;
  select * into c from public.mail_connections where id=m.connection_id and user_id=r.user_id and status='active';
  if not found then raise exception 'mail_connection_required'; end if;
  if m.state<>'queued' then return jsonb_build_object('dispatch',false,'message',to_jsonb(m),'connection',to_jsonb(c)); end if;
  if m.approved_revision is distinct from m.revision then raise exception 'mail_approval_required'; end if;
  if m.from_email is distinct from c.email then raise exception 'mail_connection_required'; end if;
  update public.outreach_messages set state='sending',attempt_id=gen_random_uuid(),attempt_started_at=clock_timestamp(),
    rfc_message_id='<jobpilot.'||id::text||'@'||split_part(c.email,'@',2)||'>',updated_at=clock_timestamp() where id=m.id returning * into m;
  return jsonb_build_object('dispatch',true,'message',to_jsonb(m),'connection',to_jsonb(c));
end $$;

-- FUNCTION: checkpoint_agent_run(uuid, uuid, text, jsonb)
CREATE FUNCTION public.checkpoint_agent_run(p_run_id uuid, p_token uuid, p_stage text, p_value jsonb) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
declare r public.agent_runs;
begin
  update public.agent_runs set checkpoints=jsonb_set(checkpoints,array[p_stage],p_value),
    stage=p_stage,updated_at=clock_timestamp()
    where id=p_run_id and lease_token=p_token and status='running' and lease_expires_at>clock_timestamp() returning * into r;
  if not found then raise exception 'lease_lost'; end if;
  return to_jsonb(r);
end $$;

-- FUNCTION: claim_agent_run(text, integer)
CREATE FUNCTION public.claim_agent_run(p_worker text, p_lease_seconds integer DEFAULT 120) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
declare r public.agent_runs;
begin
  if p_lease_seconds not between 30 and 1800 then raise exception 'invalid_lease_duration'; end if;
  for r in select q.* from public.agent_runs q
    where ((q.status in ('queued','retry_wait') and q.available_at<=clock_timestamp())
      or (q.status='running' and q.lease_expires_at<=clock_timestamp()))
      and not exists(select 1 from public.agent_runs active where active.user_id=q.user_id and active.id<>q.id and active.status='running')
    order by q.available_at,q.created_at limit 100 for update skip locked
  loop
    perform 1 from public.agent_run_locks where user_id=r.user_id for update skip locked;
    if not found then continue; end if;
    if exists(select 1 from public.agent_runs active where active.user_id=r.user_id and active.id<>r.id and active.status='running') then continue; end if;
    if r.attempts>=r.max_attempts then
      update public.agent_runs set status='failed',last_error='Worker recovery limit reached',
        lease_token=null,lease_expires_at=null,updated_at=clock_timestamp() where id=r.id;
      insert into public.agent_run_events(run_id,user_id,event) values(r.id,r.user_id,
        jsonb_build_object('type','status','step','execution','status','error','message','Worker recovery limit reached'));
      if r.kind='application' and r.inputs->>'posting_id' is not null then
        update public.job_postings set status='new', drafted_at=null, auto_drafted=false
          where id=(r.inputs->>'posting_id')::uuid and user_id=r.user_id and application_id is null;
      end if;
      continue;
    end if;
    update public.agent_runs set status='running',worker_id=p_worker,lease_token=gen_random_uuid(),
      lease_expires_at=clock_timestamp()+make_interval(secs=>p_lease_seconds),
      attempts=attempts+1,updated_at=clock_timestamp() where id=r.id returning * into r;
    insert into public.agent_run_events(run_id,user_id,event) values(r.id,r.user_id,
      jsonb_build_object('type','status','step','execution','status','running','message','Worker started or resumed the run','attempt',r.attempts));
    return to_jsonb(r);
  end loop;
  return null;
end $$;

-- FUNCTION: create_application_session(uuid, uuid, uuid, text, text, jsonb)
CREATE FUNCTION public.create_application_session(p_user_id uuid, p_id uuid, p_application_id uuid, p_page_url text, p_link_method text, p_document jsonb DEFAULT NULL::jsonb) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
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

-- FUNCTION: enqueue_agent_run(uuid, text, jsonb, text, timestamp with time zone, uuid, uuid)
CREATE FUNCTION public.enqueue_agent_run(p_user_id uuid, p_kind text, p_inputs jsonb, p_key text, p_available_at timestamp with time zone DEFAULT now(), p_parent_id uuid DEFAULT NULL::uuid, p_parent_token uuid DEFAULT NULL::uuid) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
declare r public.agent_runs;
begin
  if p_parent_id is not null then
    perform 1 from public.agent_runs where id=p_parent_id and user_id=p_user_id and status='running'
      and lease_token=p_parent_token and lease_expires_at>clock_timestamp() for update;
    if not found then raise exception 'lease_lost'; end if;
  end if;
  insert into public.agent_run_locks(user_id) values(p_user_id) on conflict do nothing;
  insert into public.agent_runs(user_id,kind,inputs,idempotency_key,available_at)
    values(p_user_id,p_kind,p_inputs,p_key,p_available_at)
    on conflict(user_id,kind,idempotency_key) do nothing returning * into r;
  if r.id is null then
    select * into strict r from public.agent_runs where user_id=p_user_id and kind=p_kind and idempotency_key=p_key;
    if (r.inputs - 'auto')<>(p_inputs - 'auto') then raise exception 'idempotency_key_conflict'; end if;
  else
    if p_kind='application' and p_inputs->>'posting_id' is not null then
      perform 1 from public.job_postings where id=(p_inputs->>'posting_id')::uuid and user_id=p_user_id
        and application_id is null and status not in ('drafted','dismissed','skipped') for update;
      if not found then raise exception 'posting_unavailable'; end if;
      update public.job_postings set status='drafting',drafted_at=clock_timestamp(),
        auto_drafted=coalesce((p_inputs->>'auto')::boolean,false)
        where id=(p_inputs->>'posting_id')::uuid and user_id=p_user_id;
    end if;
    insert into public.agent_run_events(run_id,user_id,event) values(r.id,r.user_id,
      jsonb_build_object('type','status','step','queued','status','running','message','Queued for a background worker'));
  end if;
  return to_jsonb(r);
end $$;

-- FUNCTION: finish_agent_run(uuid, uuid, text, jsonb, text, integer)
CREATE FUNCTION public.finish_agent_run(p_run_id uuid, p_token uuid, p_status text, p_result jsonb DEFAULT '{}'::jsonb, p_error text DEFAULT NULL::text, p_delay integer DEFAULT 0) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
declare r public.agent_runs; event jsonb;
begin
  if p_status not in ('succeeded','failed','retry_wait') or p_delay not between 0 and 86400 then raise exception 'invalid_run_transition'; end if;
  update public.agent_runs set status=p_status,result=p_result,last_error=left(p_error,500),
    available_at=clock_timestamp()+make_interval(secs=>p_delay),lease_token=null,lease_expires_at=null,updated_at=clock_timestamp()
    where id=p_run_id and lease_token=p_token and status='running' and lease_expires_at>clock_timestamp() returning * into r;
  if not found then raise exception 'lease_lost'; end if;
  event = case when p_status='succeeded' then jsonb_build_object('type','status','step','complete','status','success',
      'message','Background run completed','application_id',p_result->>'application_id','data',p_result)
    else jsonb_build_object('type','status','step','execution','status',case when p_status='failed' then 'error' else 'warning' end,
      'message',case when p_status='failed' then coalesce(p_error,'Run failed') else 'Temporary failure. A worker will retry from saved checkpoints.' end) end;
  insert into public.agent_run_events(run_id,user_id,event) values(r.id,r.user_id,event);
  if p_status='succeeded' and r.inputs->>'scheduled_on' is not null then
    if r.kind='scan' then
      insert into public.autopilot_state(user_id,last_scan_on,last_scan_at)
        values(r.user_id,(r.inputs->>'scheduled_on')::date,clock_timestamp())
        on conflict(user_id) do update set last_scan_on=greatest(public.autopilot_state.last_scan_on,excluded.last_scan_on),last_scan_at=excluded.last_scan_at;
    elsif r.kind='digest' then
      insert into public.autopilot_state(user_id,last_digest_on,last_digest_at,last_digest_error)
        values(r.user_id,(r.inputs->>'scheduled_on')::date,clock_timestamp(),null)
        on conflict(user_id) do update set last_digest_on=greatest(public.autopilot_state.last_digest_on,excluded.last_digest_on),last_digest_at=excluded.last_digest_at,last_digest_error=null;
    end if;
  elsif p_status='failed' and r.kind='digest' then
    insert into public.autopilot_state(user_id,last_digest_error) values(r.user_id,left(p_error,500))
      on conflict(user_id) do update set last_digest_error=excluded.last_digest_error;
  end if;
  if p_status='failed' and r.kind='application' and r.inputs->>'posting_id' is not null then
    update public.job_postings set status='new',drafted_at=null,auto_drafted=false
      where id=(r.inputs->>'posting_id')::uuid and user_id=r.user_id and application_id is null;
  end if;
  return to_jsonb(r);
end $$;

-- FUNCTION: get_execution_health()
CREATE FUNCTION public.get_execution_health() RETURNS jsonb
    LANGUAGE sql
    SET search_path TO ''
    AS $$
  select jsonb_build_object(
    'healthy_workers',(select count(*) from public.execution_workers w where w.seen_at>now()-interval '45 seconds'
      and (w.last_poll_at>now()-interval '45 seconds' or exists(select 1 from public.agent_runs r
        where r.id=w.active_run_id and r.worker_id=w.id::text and r.status='running' and r.lease_expires_at>now()))),
    'queued',(select count(*) from public.agent_runs where status in ('queued','retry_wait') and available_at<=now()),
    'expired_leases',(select count(*) from public.agent_runs where status='running' and lease_expires_at<now()),
    'failed_24h',(select count(*) from public.agent_runs where status='failed' and updated_at>now()-interval '24 hours'),
    'oldest_ready_seconds',(select coalesce(greatest(0,extract(epoch from now()-min(available_at))),0) from public.agent_runs
      where status in ('queued','retry_wait') and available_at<=now())
  );
$$;

-- FUNCTION: get_product_metrics()
CREATE FUNCTION public.get_product_metrics() RETURNS jsonb
    LANGUAGE sql STABLE
    SET search_path TO ''
    AS $_$
with apps as (select id,created_at,status from public.job_applications where user_id=(select auth.uid())),
sessions as (select id,application_id from public.application_execution_sessions where user_id=(select auth.uid())),
events as (select e.id,s.application_id,e.kind,e.details,e.created_at from public.application_events e join sessions s on s.id=e.session_id where e.user_id=(select auth.uid())),
latest_preparation as (select distinct on(application_id) * from events where kind='form_prepared' order by application_id,id desc),
accepted as (select id from public.outreach_messages where user_id=(select auth.uid()) and state='sent' and provider_message_id is not null and sent_at is not null),
replies as (select r.message_id,r.reviewed,r.classification from public.mail_replies r join accepted a on a.id=r.message_id where r.user_id=(select auth.uid())),
durations as (select greatest(0,extract(epoch from min(e.created_at)-a.created_at)) as seconds from apps a join events e on e.application_id=a.id and e.kind='form_prepared'
  group by a.id,a.created_at having min(e.created_at)>=a.created_at),
stages as (select event->>'step' as stage,(event->'data'->>'duration_ms')::numeric as duration_ms from public.agent_run_events
  where user_id=(select auth.uid()) and length(event->'data'->>'duration_ms')<20 and event->'data'->>'duration_ms' ~ '^[0-9]+([.][0-9]+)?$'),
stage_metrics as (select stage,count(*) samples,percentile_cont(0.5) within group(order by duration_ms) as median_ms,
  percentile_cont(0.95) within group(order by duration_ms) as p95_ms from stages group by stage)
select jsonb_build_object(
  'generated_applications',(select count(*) from apps),
  'prepared_applications',(select count(*) from latest_preparation),
  'attempted_applications',(select count(distinct application_id) from events where kind='submission_attempted'),
  'browser_observed_applications',(select count(distinct application_id) from events where kind='submission_confirmation_observed'),
  'user_reported_applications',(select count(distinct application_id) from events where kind='user_reported_submitted'),
  'independently_verified_submissions',null,
  'preparation',jsonb_build_object(
    'inspected_fields',(select coalesce(sum((details->'summary'->>'total')::integer),0) from latest_preparation),
    'filled_fields',(select coalesce(sum((details->'summary'->>'filled')::integer),0) from latest_preparation),
    'preserved_fields',(select coalesce(sum((details->'summary'->>'preserved')::integer),0) from latest_preparation),
    'review_fields',(select coalesce(sum((details->'summary'->>'review')::integer),0) from latest_preparation),
    'invalid_fields',(select coalesce(sum((details->'summary'->>'invalid')::integer),0) from latest_preparation),
    'truncated_applications',(select count(*) from latest_preparation where details->>'truncated'='true'),
    'time_samples',(select count(*) from durations),
    'median_seconds',(select percentile_cont(0.5) within group(order by seconds) from durations),
    'p95_seconds',(select percentile_cont(0.95) within group(order by seconds) from durations)),
  'gmail',jsonb_build_object(
    'accepted_messages',(select count(*) from accepted),
    'correlated_replied_messages',(select count(distinct message_id) from replies),
    'reviewed_human_replied_messages',(select count(distinct message_id) from replies where reviewed and classification in ('positive','negative','interview')),
    'bounce_observed_messages',(select count(*) from public.outreach_messages where user_id=(select auth.uid()) and delivery_status='bounce_observed'),
    'unknown_outcomes',(select count(*) from public.outreach_messages where user_id=(select auth.uid()) and state='send_unknown')),
  'runs',jsonb_build_object(
    'failed',(select count(*) from public.agent_runs where user_id=(select auth.uid()) and status='failed'),
    'recovered',(select count(*) from public.agent_runs where user_id=(select auth.uid()) and status='succeeded' and attempts>1),
    'pending',(select count(*) from public.agent_runs where user_id=(select auth.uid()) and status in ('queued','running','retry_wait'))),
  'stage_timings',(select coalesce(jsonb_agg(to_jsonb(s) order by stage),'[]') from stage_metrics s),
  'cost_per_application',null,
  'measurement_note','Browser observations and user reports are not independent employer verification. Gmail acceptance is not delivery. Cost is not instrumented.'
);
$_$;

-- FUNCTION: heartbeat_execution_worker(uuid, timestamp with time zone, uuid)
CREATE FUNCTION public.heartbeat_execution_worker(p_worker uuid, p_last_poll timestamp with time zone, p_active_run uuid DEFAULT NULL::uuid) RETURNS boolean
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
begin
  delete from public.execution_workers where seen_at<clock_timestamp()-interval '1 day';
  insert into public.execution_workers(id,last_poll_at,active_run_id) values(p_worker,p_last_poll,p_active_run)
    on conflict(id) do update set seen_at=clock_timestamp(),last_poll_at=excluded.last_poll_at,active_run_id=excluded.active_run_id;
  return true;
end $$;

-- FUNCTION: mail_command(uuid, text, jsonb)
CREATE FUNCTION public.mail_command(p_user_id uuid, p_action text, p_data jsonb) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
declare m public.outreach_messages; c public.mail_connections; job jsonb; other public.outreach_messages;
begin
  if p_action='connect' then
    insert into public.agent_run_locks(user_id) values(p_user_id) on conflict do nothing;
    perform 1 from public.agent_run_locks where user_id=p_user_id for update;
    if exists(select 1 from public.mail_connections where provider_account_id=p_data->>'provider_account_id' and user_id<>p_user_id) then raise exception 'mail_account_not_owned'; end if;
    if exists(select 1 from public.mail_connections where user_id=p_user_id and status='active' and provider_account_id<>p_data->>'provider_account_id') then raise exception 'disconnect_existing_mailbox_first'; end if;
    insert into public.mail_connections(user_id,provider_account_id,email) values(p_user_id,p_data->>'provider_account_id',p_data->>'email')
      on conflict(provider_account_id) do update set status='active',email=excluded.email returning * into c;
    return to_jsonb(c);
  elsif p_action='disconnect' then
    update public.mail_connections set status='disconnected' where id=(p_data->>'id')::uuid and user_id=p_user_id returning * into c;
    if not found then raise exception 'mail_not_found'; end if;
    update public.outreach_messages set state='draft',revision=revision+1,approved_revision=null,approved_at=null,from_email=null,connection_id=null,run_id=null,updated_at=clock_timestamp()
      where connection_id=c.id and user_id=p_user_id and state in ('approved','queued');
    return to_jsonb(c);
  elsif p_action='create' then
    if not exists(select 1 from public.job_applications where id=(p_data->>'application_id')::uuid and user_id=p_user_id) then raise exception 'mail_not_found'; end if;
    if p_data->>'cold_email_id' is not null and not exists(select 1 from public.cold_emails where id=(p_data->>'cold_email_id')::uuid and user_id=p_user_id and application_id=(p_data->>'application_id')::uuid) then raise exception 'mail_not_found'; end if;
    insert into public.outreach_messages(user_id,application_id,cold_email_id,request_key,to_email,subject,body,attachment)
      values(p_user_id,(p_data->>'application_id')::uuid,(p_data->>'cold_email_id')::uuid,p_data->>'request_key',p_data->>'to_email',p_data->>'subject',p_data->>'body',nullif(p_data->'attachment','null'))
      on conflict(user_id,request_key) do nothing returning * into m;
    if m.id is null then
      select * into m from public.outreach_messages where user_id=p_user_id and request_key=p_data->>'request_key';
      if m.application_id::text<>p_data->>'application_id' or m.to_email<>p_data->>'to_email' or m.subject<>p_data->>'subject' or m.body<>p_data->>'body' then raise exception 'mail_revision_conflict'; end if;
    end if;
    return to_jsonb(m);
  end if;
  select * into m from public.outreach_messages where id=(p_data->>'id')::uuid and user_id=p_user_id for update;
  if not found then raise exception 'mail_not_found'; end if;
  if p_action='queue' and m.state in ('queued','sending','sent','send_unknown') then return to_jsonb(m); end if;
  if m.revision is distinct from (p_data->>'revision')::integer then raise exception 'mail_revision_conflict'; end if;
  if p_action='cancel' then
    if m.state not in ('queued','approved','draft','failed') then raise exception 'mail_immutable'; end if;
    update public.outreach_messages set state='draft',revision=revision+1,approved_revision=null,approved_at=null,from_email=null,connection_id=null,run_id=null,updated_at=clock_timestamp() where id=m.id returning * into m;
    return to_jsonb(m);
  end if;
  if p_action='edit' then
    if m.state not in ('draft','approved','failed') then raise exception 'mail_immutable'; end if;
    update public.outreach_messages set to_email=p_data->>'to_email',subject=p_data->>'subject',body=p_data->>'body',attachment=nullif(p_data->'attachment','null'),
      revision=revision+1,state='draft',approved_revision=null,approved_at=null,from_email=null,connection_id=null,run_id=null,last_error=null,updated_at=clock_timestamp()
      where id=m.id returning * into m;
  elsif p_action='approve' then
    if m.state not in ('draft','approved') then raise exception 'mail_immutable'; end if;
    select * into c from public.mail_connections where user_id=p_user_id and status='active' for update;
    if not found then raise exception 'mail_connection_required'; end if;
    if m.to_email='' or m.subject='' or m.body='' then raise exception 'mail_incomplete'; end if;
    update public.outreach_messages set state='approved',approved_revision=revision,approved_at=clock_timestamp(),from_email=c.email,connection_id=c.id,updated_at=clock_timestamp()
      where id=m.id returning * into m;
  elsif p_action='queue' then
    if m.state<>'approved' or m.approved_revision is distinct from m.revision then raise exception 'mail_approval_required'; end if;
    if not exists(select 1 from public.mail_connections where id=m.connection_id and user_id=p_user_id and status='active') then raise exception 'mail_connection_required'; end if;
    job=public.enqueue_agent_run(p_user_id,'mail_send',jsonb_build_object('message_id',m.id),'outreach-send:'||m.id::text||':'||m.revision::text);
    update public.outreach_messages set state='queued',run_id=(job->>'id')::uuid,updated_at=clock_timestamp() where id=m.id returning * into m;
  else raise exception 'invalid_mail_action'; end if;
  return to_jsonb(m);
end $$;

-- FUNCTION: mail_worker_result(uuid, uuid, uuid, text, jsonb)
CREATE FUNCTION public.mail_worker_result(p_run_id uuid, p_token uuid, p_message_id uuid, p_state text, p_data jsonb) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
declare r public.agent_runs; m public.outreach_messages; reply jsonb;
begin
  select * into r from public.agent_runs where id=p_run_id and lease_token=p_token and status='running' and lease_expires_at>clock_timestamp() and kind in ('mail_send','mail_sync') for update;
  if not found then raise exception 'lease_lost'; end if;
  select * into m from public.outreach_messages where id=p_message_id and user_id=r.user_id for update;
  if not found then raise exception 'mail_not_found'; end if;
  if (r.kind='mail_send' and m.run_id is distinct from r.id) or (r.kind='mail_sync' and m.connection_id::text is distinct from r.inputs->>'connection_id') then raise exception 'mail_not_found'; end if;
  if p_state='sent' then
    if m.state not in ('sending','send_unknown','sent') or coalesce(p_data->>'provider_message_id','')='' then raise exception 'invalid_mail_transition'; end if;
    update public.outreach_messages set state='sent',provider_message_id=p_data->>'provider_message_id',provider_thread_id=p_data->>'provider_thread_id',
      sent_at=coalesce(sent_at,clock_timestamp()),last_error=null,updated_at=clock_timestamp() where id=m.id returning * into m;
  elsif p_state in ('send_unknown','failed') then
    if m.state in ('sending','send_unknown') then
      update public.outreach_messages set state=p_state,last_error=left(p_data->>'error',500),updated_at=clock_timestamp() where id=m.id returning * into m;
    end if;
  elsif p_state<>'replies' then raise exception 'invalid_mail_transition'; end if;
  for reply in select value from jsonb_array_elements(coalesce(p_data->'replies','[]')) loop
    insert into public.mail_replies(user_id,message_id,provider_message_id,from_email,excerpt,received_at,classification)
      values(r.user_id,m.id,reply->>'provider_message_id',reply->>'from_email',left(reply->>'excerpt',4000),(reply->>'received_at')::timestamptz,reply->>'classification')
      on conflict(message_id,provider_message_id) do nothing;
    if reply->>'classification'='bounce' then update public.outreach_messages set delivery_status='bounce_observed' where id=m.id; end if;
  end loop;
  if p_state='replies' then update public.mail_connections set last_sync_at=clock_timestamp() where id=m.connection_id and user_id=r.user_id; end if;
  return to_jsonb(m);
end $$;

-- FUNCTION: prune_release_telemetry(timestamp with time zone)
CREATE FUNCTION public.prune_release_telemetry(p_before timestamp with time zone) RETURNS void
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
begin
  if p_before>now()-interval '30 days' then raise exception 'minimum_retention_30_days'; end if;
  delete from public.recommendation_runs where created_at<p_before;
  delete from public.usage_receipts where created_at<p_before;
  delete from public.usage_windows where window_start<p_before;
end $$;

-- FUNCTION: record_recommendation_impression(uuid, uuid, uuid, uuid, integer, integer)
CREATE FUNCTION public.record_recommendation_impression(p_user_id uuid, p_run_id uuid, p_posting_id uuid, p_key uuid, p_position integer, p_visible_ms integer) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
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

-- FUNCTION: release_schema_ready()
CREATE FUNCTION public.release_schema_ready() RETURNS boolean
    LANGUAGE sql
    SET search_path TO ''
    AS $$
 select to_regclass('public.recommendation_runs') is not null and to_regclass('public.company_research') is not null
   and to_regclass('public.writing_templates') is not null and to_regclass('public.usage_windows') is not null;
$$;

-- FUNCTION: renew_agent_run(uuid, uuid, integer)
CREATE FUNCTION public.renew_agent_run(p_run_id uuid, p_token uuid, p_lease_seconds integer DEFAULT 120) RETURNS boolean
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
begin
  if p_lease_seconds not between 30 and 1800 then raise exception 'invalid_lease_duration'; end if;
  update public.agent_runs set lease_expires_at=clock_timestamp()+make_interval(secs=>p_lease_seconds),updated_at=clock_timestamp()
    where id=p_run_id and lease_token=p_token and status='running' and lease_expires_at>clock_timestamp();
  return found;
end $$;

-- FUNCTION: reserve_release_usage(uuid, text, text, integer, integer)
CREATE FUNCTION public.reserve_release_usage(p_user_id uuid, p_bucket text, p_key text, p_limit integer, p_seconds integer DEFAULT 86400) RETURNS boolean
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
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

-- FUNCTION: retry_agent_run(uuid, uuid)
CREATE FUNCTION public.retry_agent_run(p_run_id uuid, p_user_id uuid) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
declare r public.agent_runs;
begin
  select * into r from public.agent_runs where id=p_run_id and user_id=p_user_id for update;
  if not found then raise exception 'run_not_found'; end if;
  if r.status<>'failed' then raise exception 'run_not_failed'; end if;
  -- Frozen digest messages must never be deliberately retried beyond the
  -- provider window. A new manual digest request has a new delivery identity.
  if r.kind='digest' then raise exception 'request_a_new_digest'; end if;
  if r.kind='application' and r.inputs->>'posting_id' is not null then
    perform 1 from public.job_postings where id=(r.inputs->>'posting_id')::uuid and user_id=r.user_id
      and status not in ('dismissed','skipped') for update;
    if not found then raise exception 'posting_unavailable'; end if;
    update public.job_postings set status='drafting',drafted_at=clock_timestamp()
      where id=(r.inputs->>'posting_id')::uuid and user_id=r.user_id and application_id is null;
  end if;
  update public.agent_runs set status='queued',attempts=0,last_error=null,available_at=clock_timestamp(),
    lease_token=null,lease_expires_at=null,updated_at=clock_timestamp() where id=r.id returning * into r;
  insert into public.agent_run_events(run_id,user_id,event) values(r.id,r.user_id,
    jsonb_build_object('type','status','step','queued','status','running','message','Retry requested; completed stages will be reused'));
  return to_jsonb(r);
end $$;

-- FUNCTION: save_company_research(uuid, uuid, uuid, text, jsonb, jsonb)
CREATE FUNCTION public.save_company_research(p_run_id uuid, p_token uuid, p_application_id uuid, p_company text, p_sources jsonb, p_warnings jsonb) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
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

-- FUNCTION: save_run_application(uuid, uuid, jsonb, jsonb, jsonb)
CREATE FUNCTION public.save_run_application(p_run_id uuid, p_token uuid, p_application jsonb, p_tailored jsonb, p_emails jsonb) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
declare r public.agent_runs; app_id uuid; email jsonb; output jsonb; posting public.job_postings;
begin
  select * into r from public.agent_runs where id=p_run_id and lease_token=p_token
    and status='running' and kind='application' and lease_expires_at>clock_timestamp() for update;
  if not found then raise exception 'lease_lost'; end if;
  if r.checkpoints ? 'database_saving' then
    output=r.checkpoints->'database_saving';
    if not exists(select 1 from public.job_applications where id=(output->>'application_id')::uuid and user_id=r.user_id) then
      raise exception 'generated_application_was_deleted';
    end if;
    return output;
  end if;
  if r.inputs->>'posting_id' is not null then
    select * into strict posting from public.job_postings where id=(r.inputs->>'posting_id')::uuid and user_id=r.user_id for update;
    if posting.application_id is not null then raise exception 'posting_already_has_application'; end if;
  end if;
  insert into public.job_applications(user_id,company,role,jd_url,jd_text,jd_analysis,status,source,notes,cover_letter,linkedin_dm)
    values(r.user_id,p_application->>'company',p_application->>'role',coalesce(p_application->>'jd_url',''),
      coalesce(p_application->>'jd_text',''),p_application->'jd_analysis','saved',coalesce(p_application->>'source','manual'),'',
      coalesce(p_application->>'cover_letter',''),coalesce(p_application->'linkedin_dm','{}')) returning id into app_id;
  insert into public.tailored_resumes(application_id,user_id,version,content,pdf_url,keyword_match_score,missing_keywords)
    values(app_id,r.user_id,1,p_tailored->'content','',(p_tailored->>'keyword_match_score')::numeric,p_tailored->'missing_keywords');
  for email in select value from jsonb_array_elements(p_emails) loop
    insert into public.cold_emails(application_id,user_id,to_email,to_name,subject,body,sequence_number,opened,replied)
      values(app_id,r.user_id,'','Hiring Manager',email->>'subject',email->>'body',(email->>'sequence_number')::integer,false,false);
  end loop;
  output=jsonb_build_object('application_id',app_id,'company',p_application->>'company','role',p_application->>'role','score',p_tailored->'keyword_match_score');
  update public.agent_runs set checkpoints=jsonb_set(checkpoints,'{database_saving}',output),result=output,updated_at=clock_timestamp() where id=r.id;
  if posting.id is not null then
    update public.job_postings set status='drafted',application_id=app_id where id=posting.id and user_id=r.user_id;
  end if;
  return output;
end $$;

-- FUNCTION: save_run_prepared(uuid, uuid, uuid, jsonb)
CREATE FUNCTION public.save_run_prepared(p_run_id uuid, p_token uuid, p_application_id uuid, p_prepared jsonb) RETURNS boolean
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
declare r public.agent_runs;
begin
  select * into r from public.agent_runs where id=p_run_id and lease_token=p_token and status='running'
    and lease_expires_at>clock_timestamp() for update;
  if not found then raise exception 'lease_lost'; end if;
  if r.checkpoints->'database_saving'->>'application_id' is distinct from p_application_id::text then raise exception 'application_not_owned'; end if;
  update public.job_applications set prepared_form=p_prepared where id=p_application_id and user_id=r.user_id;
  return found;
end $$;

-- FUNCTION: save_run_referral(uuid, uuid, uuid, text)
CREATE FUNCTION public.save_run_referral(p_run_id uuid, p_token uuid, p_contact_id uuid, p_message text) RETURNS boolean
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
declare r public.agent_runs;
begin
  select * into r from public.agent_runs where id=p_run_id and lease_token=p_token and status='running'
    and lease_expires_at>clock_timestamp() for update;
  if not found then raise exception 'lease_lost'; end if;
  if not exists(select 1 from public.network_contacts where id=p_contact_id and user_id=r.user_id) then raise exception 'contact_not_owned'; end if;
  insert into public.referral_requests(user_id,application_id,contact_id,message,status)
    values(r.user_id,(r.checkpoints->'database_saving'->>'application_id')::uuid,p_contact_id,left(p_message,900),'drafted')
    on conflict(application_id,contact_id) do nothing;
  return true;
end $$;

-- FUNCTION: set_updated_at()
CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- TABLE: agent_run_events
CREATE TABLE public.agent_run_events (
    id bigint NOT NULL,
    run_id uuid NOT NULL,
    user_id uuid NOT NULL,
    event jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

-- SEQUENCE: agent_run_events_id_seq
ALTER TABLE public.agent_run_events ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.agent_run_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

-- TABLE: agent_run_locks
CREATE TABLE public.agent_run_locks (
    user_id uuid NOT NULL
);

-- TABLE: agent_runs
CREATE TABLE public.agent_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    kind text NOT NULL,
    idempotency_key text NOT NULL,
    inputs jsonb DEFAULT '{}'::jsonb NOT NULL,
    checkpoints jsonb DEFAULT '{}'::jsonb NOT NULL,
    result jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    stage text DEFAULT 'queued'::text NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 3 NOT NULL,
    worker_id text,
    lease_token uuid,
    lease_expires_at timestamp with time zone,
    available_at timestamp with time zone DEFAULT now() NOT NULL,
    last_error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_runs_idempotency_key_check CHECK (((length(idempotency_key) >= 1) AND (length(idempotency_key) <= 200))),
    CONSTRAINT agent_runs_kind_check CHECK ((kind = ANY (ARRAY['application'::text, 'scan'::text, 'digest'::text, 'mail_send'::text, 'mail_sync'::text, 'company_research'::text, 'recommendation'::text]))),
    CONSTRAINT agent_runs_max_attempts_check CHECK (((max_attempts >= 1) AND (max_attempts <= 10))),
    CONSTRAINT agent_runs_status_check CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'retry_wait'::text, 'succeeded'::text, 'failed'::text])))
);

-- TABLE: application_documents
CREATE TABLE public.application_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    application_id uuid NOT NULL,
    resume_version integer NOT NULL,
    name text NOT NULL,
    sha256 text NOT NULL,
    size_bytes integer NOT NULL,
    pdf_base64 text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT application_documents_pdf_base64_check CHECK ((length(pdf_base64) <= 2796204)),
    CONSTRAINT application_documents_sha256_check CHECK ((sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT application_documents_size_bytes_check CHECK (((size_bytes >= 5) AND (size_bytes <= 2097152)))
);

-- TABLE: application_events
CREATE TABLE public.application_events (
    id bigint NOT NULL,
    user_id uuid NOT NULL,
    session_id uuid NOT NULL,
    kind text NOT NULL,
    request_key uuid NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT application_events_details_check CHECK (((jsonb_typeof(details) = 'object'::text) AND (octet_length((details)::text) <= 65536))),
    CONSTRAINT application_events_kind_check CHECK ((kind = ANY (ARRAY['form_prepared'::text, 'submission_attempted'::text, 'submission_confirmation_observed'::text, 'user_reported_submitted'::text])))
);

-- SEQUENCE: application_events_id_seq
ALTER TABLE public.application_events ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.application_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

-- TABLE: application_execution_sessions
CREATE TABLE public.application_execution_sessions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    application_id uuid NOT NULL,
    page_url text NOT NULL,
    link_method text NOT NULL,
    document_id uuid,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    expires_at timestamp with time zone DEFAULT (clock_timestamp() + '24:00:00'::interval) NOT NULL,
    CONSTRAINT application_execution_sessions_link_method_check CHECK ((link_method = ANY (ARRAY['url_match'::text, 'user_confirmed'::text, 'manual_report'::text]))),
    CONSTRAINT application_execution_sessions_page_url_check CHECK ((length(page_url) <= 2000))
);

-- TABLE: autopilot_state
CREATE TABLE public.autopilot_state (
    user_id uuid DEFAULT auth.uid() NOT NULL,
    last_scan_on date,
    last_scan_at timestamp with time zone,
    last_digest_on date,
    last_digest_at timestamp with time zone,
    last_digest_error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

-- TABLE: cold_emails
CREATE TABLE public.cold_emails (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid DEFAULT auth.uid() NOT NULL,
    application_id uuid NOT NULL,
    to_email text DEFAULT ''::text NOT NULL,
    to_name text DEFAULT ''::text NOT NULL,
    subject text DEFAULT ''::text NOT NULL,
    body text DEFAULT ''::text NOT NULL,
    sequence_number integer DEFAULT 1 NOT NULL,
    opened boolean DEFAULT false NOT NULL,
    opened_at timestamp with time zone,
    replied_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    sent_at timestamp with time zone,
    replied boolean DEFAULT false NOT NULL
);

-- TABLE: company_research
CREATE TABLE public.company_research (
    run_id uuid NOT NULL,
    user_id uuid NOT NULL,
    application_id uuid NOT NULL,
    company text NOT NULL,
    sources jsonb NOT NULL,
    warnings jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT company_research_sources_check CHECK (((jsonb_typeof(sources) = 'array'::text) AND (jsonb_array_length(sources) <= 3)))
);

-- TABLE: execution_workers
CREATE TABLE public.execution_workers (
    id uuid NOT NULL,
    seen_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    last_poll_at timestamp with time zone,
    active_run_id uuid
);

-- TABLE: extension_tokens
CREATE TABLE public.extension_tokens (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid DEFAULT auth.uid() NOT NULL,
    token_hash text NOT NULL,
    label text DEFAULT 'Chrome extension'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_used_at timestamp with time zone
);

-- TABLE: identity_confirmations
CREATE TABLE public.identity_confirmations (
    user_id uuid NOT NULL,
    fact_id text NOT NULL,
    source_digest text NOT NULL,
    confirmed_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT identity_confirmations_fact_id_check CHECK ((fact_id ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT identity_confirmations_source_digest_check CHECK ((source_digest ~ '^[0-9a-f]{64}$'::text))
);

-- TABLE: job_applications
CREATE TABLE public.job_applications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid DEFAULT auth.uid() NOT NULL,
    company text DEFAULT ''::text NOT NULL,
    role text DEFAULT ''::text NOT NULL,
    jd_url text DEFAULT ''::text NOT NULL,
    jd_text text DEFAULT ''::text NOT NULL,
    jd_analysis jsonb,
    status text DEFAULT 'saved'::text NOT NULL,
    source text DEFAULT 'manual'::text NOT NULL,
    notes text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    cover_letter text DEFAULT ''::text NOT NULL,
    linkedin_dm jsonb DEFAULT '{}'::jsonb NOT NULL,
    follow_up_at timestamp with time zone,
    applied_at timestamp with time zone,
    prepared_form jsonb,
    CONSTRAINT job_applications_status_check CHECK ((status = ANY (ARRAY['saved'::text, 'applied'::text, 'interviewing'::text, 'offer'::text, 'rejected'::text, 'archived'::text])))
);

-- TABLE: job_postings
CREATE TABLE public.job_postings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid DEFAULT auth.uid() NOT NULL,
    source_id uuid,
    ats text NOT NULL,
    external_id text NOT NULL,
    company text DEFAULT ''::text NOT NULL,
    title text DEFAULT ''::text NOT NULL,
    location text DEFAULT ''::text NOT NULL,
    remote boolean,
    url text DEFAULT ''::text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    posted_at timestamp with time zone,
    fit_score numeric DEFAULT 0 NOT NULL,
    title_match numeric DEFAULT 0 NOT NULL,
    matched_skills jsonb DEFAULT '[]'::jsonb NOT NULL,
    missing_skills jsonb DEFAULT '[]'::jsonb NOT NULL,
    skip_flags jsonb DEFAULT '[]'::jsonb NOT NULL,
    status text DEFAULT 'new'::text NOT NULL,
    application_id uuid,
    auto_drafted boolean DEFAULT false NOT NULL,
    drafted_at timestamp with time zone,
    closed_at timestamp with time zone,
    discovered_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    matching_details jsonb DEFAULT '{}'::jsonb NOT NULL,
    dedupe_key text DEFAULT ''::text NOT NULL,
    CONSTRAINT job_postings_status_check CHECK ((status = ANY (ARRAY['new'::text, 'dismissed'::text, 'skipped'::text, 'drafting'::text, 'drafted'::text])))
);

-- TABLE: job_sources
CREATE TABLE public.job_sources (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid DEFAULT auth.uid() NOT NULL,
    ats text NOT NULL,
    slug text NOT NULL,
    company text DEFAULT ''::text NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    job_count integer DEFAULT 0 NOT NULL,
    last_scanned_at timestamp with time zone,
    last_error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT job_sources_ats_check CHECK ((ats = ANY (ARRAY['greenhouse'::text, 'lever'::text, 'ashby'::text, 'smartrecruiters'::text, 'himalayas'::text, 'remotive'::text])))
);

-- TABLE: mail_connections
CREATE TABLE public.mail_connections (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    provider_account_id text NOT NULL,
    email text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_sync_at timestamp with time zone,
    CONSTRAINT mail_connections_status_check CHECK ((status = ANY (ARRAY['active'::text, 'disconnected'::text])))
);

-- TABLE: mail_replies
CREATE TABLE public.mail_replies (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    message_id uuid NOT NULL,
    provider_message_id text NOT NULL,
    from_email text NOT NULL,
    excerpt text NOT NULL,
    received_at timestamp with time zone NOT NULL,
    classification text NOT NULL,
    classification_source text DEFAULT 'rule_suggestion'::text NOT NULL,
    reviewed boolean DEFAULT false NOT NULL
);

-- TABLE: network_contacts
CREATE TABLE public.network_contacts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid DEFAULT auth.uid() NOT NULL,
    full_name text NOT NULL,
    first_name text DEFAULT ''::text NOT NULL,
    last_name text DEFAULT ''::text NOT NULL,
    email text DEFAULT ''::text NOT NULL,
    linkedin_url text DEFAULT ''::text NOT NULL,
    company text DEFAULT ''::text NOT NULL,
    company_key text DEFAULT ''::text NOT NULL,
    "position" text DEFAULT ''::text NOT NULL,
    connected_on date,
    source text DEFAULT 'manual'::text NOT NULL,
    notes text DEFAULT ''::text NOT NULL,
    dedupe_key text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT network_contacts_source_check CHECK ((source = ANY (ARRAY['linkedin'::text, 'manual'::text])))
);

-- TABLE: outreach_messages
CREATE TABLE public.outreach_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    application_id uuid NOT NULL,
    cold_email_id uuid,
    request_key text NOT NULL,
    to_email text NOT NULL,
    subject text NOT NULL,
    body text NOT NULL,
    attachment jsonb,
    revision integer DEFAULT 1 NOT NULL,
    approved_revision integer,
    approved_at timestamp with time zone,
    connection_id uuid,
    state text DEFAULT 'draft'::text NOT NULL,
    run_id uuid,
    attempt_id uuid,
    attempt_started_at timestamp with time zone,
    rfc_message_id text,
    provider_message_id text,
    provider_thread_id text,
    sent_at timestamp with time zone,
    delivery_status text DEFAULT 'unknown'::text NOT NULL,
    last_error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    from_email text,
    CONSTRAINT outreach_messages_delivery_status_check CHECK ((delivery_status = ANY (ARRAY['unknown'::text, 'bounce_observed'::text]))),
    CONSTRAINT outreach_messages_state_check CHECK ((state = ANY (ARRAY['draft'::text, 'approved'::text, 'queued'::text, 'sending'::text, 'sent'::text, 'send_unknown'::text, 'failed'::text])))
);

-- TABLE: qa_answers
CREATE TABLE public.qa_answers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid DEFAULT auth.uid() NOT NULL,
    question text NOT NULL,
    answer text DEFAULT ''::text NOT NULL,
    category text DEFAULT 'custom'::text NOT NULL,
    sensitive boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

-- TABLE: recommendation_feedback
CREATE TABLE public.recommendation_feedback (
    user_id uuid NOT NULL,
    posting_id uuid NOT NULL,
    signal text NOT NULL,
    reason text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT recommendation_feedback_check CHECK (((signal = 'not_relevant'::text) OR (reason IS NULL))),
    CONSTRAINT recommendation_feedback_reason_check CHECK ((reason = ANY (ARRAY['wrong_role'::text, 'location'::text, 'seniority'::text, 'skills'::text, 'other'::text]))),
    CONSTRAINT recommendation_feedback_signal_check CHECK ((signal = ANY (ARRAY['interested'::text, 'not_relevant'::text])))
);

-- TABLE: recommendation_impressions
CREATE TABLE public.recommendation_impressions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    run_id uuid NOT NULL,
    posting_id uuid NOT NULL,
    request_key uuid NOT NULL,
    "position" integer NOT NULL,
    visible_ms integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT recommendation_impressions_position_check CHECK ((("position" >= 1) AND ("position" <= 100))),
    CONSTRAINT recommendation_impressions_visible_ms_check CHECK (((visible_ms >= 500) AND (visible_ms <= 60000)))
);

-- TABLE: recommendation_runs
CREATE TABLE public.recommendation_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    request_key uuid NOT NULL,
    model_version text NOT NULL,
    profile_digest text NOT NULL,
    items jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT recommendation_runs_items_check CHECK (((jsonb_typeof(items) = 'array'::text) AND ((jsonb_array_length(items) >= 1) AND (jsonb_array_length(items) <= 100))))
);

-- TABLE: recruiter_leads
CREATE TABLE public.recruiter_leads (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    application_id uuid NOT NULL,
    email text NOT NULL,
    full_name text NOT NULL,
    "position" text NOT NULL,
    domain text NOT NULL,
    sources jsonb DEFAULT '[]'::jsonb NOT NULL,
    verification text NOT NULL,
    verified_at timestamp with time zone DEFAULT now() NOT NULL
);

-- TABLE: referral_requests
CREATE TABLE public.referral_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid DEFAULT auth.uid() NOT NULL,
    application_id uuid NOT NULL,
    contact_id uuid NOT NULL,
    status text DEFAULT 'drafted'::text NOT NULL,
    message text DEFAULT ''::text NOT NULL,
    sent_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT referral_requests_status_check CHECK ((status = ANY (ARRAY['drafted'::text, 'sent'::text, 'referred'::text, 'declined'::text, 'no_reply'::text])))
);

-- TABLE: resumes
CREATE TABLE public.resumes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid DEFAULT auth.uid() NOT NULL,
    version text DEFAULT 'base'::text NOT NULL,
    name text DEFAULT ''::text NOT NULL,
    headline text DEFAULT ''::text NOT NULL,
    summary text DEFAULT ''::text NOT NULL,
    experience jsonb DEFAULT '[]'::jsonb NOT NULL,
    skills jsonb DEFAULT '{"primary": [], "secondary": []}'::jsonb NOT NULL,
    projects jsonb DEFAULT '[]'::jsonb NOT NULL,
    education jsonb DEFAULT '[]'::jsonb NOT NULL,
    certifications jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

-- TABLE: tailored_resumes
CREATE TABLE public.tailored_resumes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid DEFAULT auth.uid() NOT NULL,
    application_id uuid NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    content jsonb DEFAULT '{}'::jsonb NOT NULL,
    pdf_url text DEFAULT ''::text NOT NULL,
    keyword_match_score numeric DEFAULT 0 NOT NULL,
    missing_keywords jsonb DEFAULT '[]'::jsonb NOT NULL,
    generated_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

-- TABLE: usage_receipts
CREATE TABLE public.usage_receipts (
    user_id uuid NOT NULL,
    bucket text NOT NULL,
    request_key text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

-- TABLE: usage_windows
CREATE TABLE public.usage_windows (
    user_id uuid NOT NULL,
    bucket text NOT NULL,
    window_start timestamp with time zone NOT NULL,
    used integer NOT NULL,
    CONSTRAINT usage_windows_used_check CHECK ((used >= 0))
);

-- TABLE: user_profiles
CREATE TABLE public.user_profiles (
    id uuid DEFAULT auth.uid() NOT NULL,
    name text DEFAULT ''::text NOT NULL,
    headline text DEFAULT ''::text NOT NULL,
    location text DEFAULT ''::text NOT NULL,
    salary_range text DEFAULT ''::text NOT NULL,
    linkedin_url text DEFAULT ''::text NOT NULL,
    work_preferences jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

-- TABLE: writing_templates
CREATE TABLE public.writing_templates (
    user_id uuid DEFAULT auth.uid() NOT NULL,
    kind text NOT NULL,
    content text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT writing_templates_content_check CHECK ((length(content) <= 10000)),
    CONSTRAINT writing_templates_kind_check CHECK ((kind = ANY (ARRAY['email'::text, 'dm'::text, 'cover_letter'::text])))
);

-- CONSTRAINT: agent_run_events agent_run_events_pkey
ALTER TABLE ONLY public.agent_run_events
    ADD CONSTRAINT agent_run_events_pkey PRIMARY KEY (id);

-- CONSTRAINT: agent_run_locks agent_run_locks_pkey
ALTER TABLE ONLY public.agent_run_locks
    ADD CONSTRAINT agent_run_locks_pkey PRIMARY KEY (user_id);

-- CONSTRAINT: agent_runs agent_runs_id_user_id_key
ALTER TABLE ONLY public.agent_runs
    ADD CONSTRAINT agent_runs_id_user_id_key UNIQUE (id, user_id);

-- CONSTRAINT: agent_runs agent_runs_pkey
ALTER TABLE ONLY public.agent_runs
    ADD CONSTRAINT agent_runs_pkey PRIMARY KEY (id);

-- CONSTRAINT: agent_runs agent_runs_user_id_kind_idempotency_key_key
ALTER TABLE ONLY public.agent_runs
    ADD CONSTRAINT agent_runs_user_id_kind_idempotency_key_key UNIQUE (user_id, kind, idempotency_key);

-- CONSTRAINT: application_documents application_documents_id_user_id_key
ALTER TABLE ONLY public.application_documents
    ADD CONSTRAINT application_documents_id_user_id_key UNIQUE (id, user_id);

-- CONSTRAINT: application_documents application_documents_pkey
ALTER TABLE ONLY public.application_documents
    ADD CONSTRAINT application_documents_pkey PRIMARY KEY (id);

-- CONSTRAINT: application_events application_events_pkey
ALTER TABLE ONLY public.application_events
    ADD CONSTRAINT application_events_pkey PRIMARY KEY (id);

-- CONSTRAINT: application_events application_events_session_id_request_key_key
ALTER TABLE ONLY public.application_events
    ADD CONSTRAINT application_events_session_id_request_key_key UNIQUE (session_id, request_key);

-- CONSTRAINT: application_execution_sessions application_execution_sessions_id_user_id_key
ALTER TABLE ONLY public.application_execution_sessions
    ADD CONSTRAINT application_execution_sessions_id_user_id_key UNIQUE (id, user_id);

-- CONSTRAINT: application_execution_sessions application_execution_sessions_pkey
ALTER TABLE ONLY public.application_execution_sessions
    ADD CONSTRAINT application_execution_sessions_pkey PRIMARY KEY (id);

-- CONSTRAINT: autopilot_state autopilot_state_pkey
ALTER TABLE ONLY public.autopilot_state
    ADD CONSTRAINT autopilot_state_pkey PRIMARY KEY (user_id);

-- CONSTRAINT: cold_emails cold_emails_pkey
ALTER TABLE ONLY public.cold_emails
    ADD CONSTRAINT cold_emails_pkey PRIMARY KEY (id);

-- CONSTRAINT: company_research company_research_pkey
ALTER TABLE ONLY public.company_research
    ADD CONSTRAINT company_research_pkey PRIMARY KEY (run_id);

-- CONSTRAINT: execution_workers execution_workers_pkey
ALTER TABLE ONLY public.execution_workers
    ADD CONSTRAINT execution_workers_pkey PRIMARY KEY (id);

-- CONSTRAINT: extension_tokens extension_tokens_pkey
ALTER TABLE ONLY public.extension_tokens
    ADD CONSTRAINT extension_tokens_pkey PRIMARY KEY (id);

-- CONSTRAINT: extension_tokens extension_tokens_token_hash_key
ALTER TABLE ONLY public.extension_tokens
    ADD CONSTRAINT extension_tokens_token_hash_key UNIQUE (token_hash);

-- CONSTRAINT: identity_confirmations identity_confirmations_pkey
ALTER TABLE ONLY public.identity_confirmations
    ADD CONSTRAINT identity_confirmations_pkey PRIMARY KEY (user_id, source_digest, fact_id);

-- CONSTRAINT: job_applications job_applications_pkey
ALTER TABLE ONLY public.job_applications
    ADD CONSTRAINT job_applications_pkey PRIMARY KEY (id);

-- CONSTRAINT: job_postings job_postings_pkey
ALTER TABLE ONLY public.job_postings
    ADD CONSTRAINT job_postings_pkey PRIMARY KEY (id);

-- CONSTRAINT: job_postings job_postings_user_id_ats_external_id_key
ALTER TABLE ONLY public.job_postings
    ADD CONSTRAINT job_postings_user_id_ats_external_id_key UNIQUE (user_id, ats, external_id);

-- CONSTRAINT: job_sources job_sources_pkey
ALTER TABLE ONLY public.job_sources
    ADD CONSTRAINT job_sources_pkey PRIMARY KEY (id);

-- CONSTRAINT: job_sources job_sources_user_id_ats_slug_key
ALTER TABLE ONLY public.job_sources
    ADD CONSTRAINT job_sources_user_id_ats_slug_key UNIQUE (user_id, ats, slug);

-- CONSTRAINT: mail_connections mail_connections_id_user_id_key
ALTER TABLE ONLY public.mail_connections
    ADD CONSTRAINT mail_connections_id_user_id_key UNIQUE (id, user_id);

-- CONSTRAINT: mail_connections mail_connections_pkey
ALTER TABLE ONLY public.mail_connections
    ADD CONSTRAINT mail_connections_pkey PRIMARY KEY (id);

-- CONSTRAINT: mail_connections mail_connections_provider_account_id_key
ALTER TABLE ONLY public.mail_connections
    ADD CONSTRAINT mail_connections_provider_account_id_key UNIQUE (provider_account_id);

-- CONSTRAINT: mail_replies mail_replies_message_id_provider_message_id_key
ALTER TABLE ONLY public.mail_replies
    ADD CONSTRAINT mail_replies_message_id_provider_message_id_key UNIQUE (message_id, provider_message_id);

-- CONSTRAINT: mail_replies mail_replies_pkey
ALTER TABLE ONLY public.mail_replies
    ADD CONSTRAINT mail_replies_pkey PRIMARY KEY (id);

-- CONSTRAINT: network_contacts network_contacts_pkey
ALTER TABLE ONLY public.network_contacts
    ADD CONSTRAINT network_contacts_pkey PRIMARY KEY (id);

-- CONSTRAINT: network_contacts network_contacts_user_id_dedupe_key_key
ALTER TABLE ONLY public.network_contacts
    ADD CONSTRAINT network_contacts_user_id_dedupe_key_key UNIQUE (user_id, dedupe_key);

-- CONSTRAINT: outreach_messages outreach_messages_id_user_id_key
ALTER TABLE ONLY public.outreach_messages
    ADD CONSTRAINT outreach_messages_id_user_id_key UNIQUE (id, user_id);

-- CONSTRAINT: outreach_messages outreach_messages_pkey
ALTER TABLE ONLY public.outreach_messages
    ADD CONSTRAINT outreach_messages_pkey PRIMARY KEY (id);

-- CONSTRAINT: outreach_messages outreach_messages_user_id_request_key_key
ALTER TABLE ONLY public.outreach_messages
    ADD CONSTRAINT outreach_messages_user_id_request_key_key UNIQUE (user_id, request_key);

-- CONSTRAINT: qa_answers qa_answers_pkey
ALTER TABLE ONLY public.qa_answers
    ADD CONSTRAINT qa_answers_pkey PRIMARY KEY (id);

-- CONSTRAINT: qa_answers qa_answers_user_id_question_key
ALTER TABLE ONLY public.qa_answers
    ADD CONSTRAINT qa_answers_user_id_question_key UNIQUE (user_id, question);

-- CONSTRAINT: recommendation_feedback recommendation_feedback_pkey
ALTER TABLE ONLY public.recommendation_feedback
    ADD CONSTRAINT recommendation_feedback_pkey PRIMARY KEY (user_id, posting_id);

-- CONSTRAINT: recommendation_impressions recommendation_impressions_pkey
ALTER TABLE ONLY public.recommendation_impressions
    ADD CONSTRAINT recommendation_impressions_pkey PRIMARY KEY (id);

-- CONSTRAINT: recommendation_impressions recommendation_impressions_run_id_posting_id_key
ALTER TABLE ONLY public.recommendation_impressions
    ADD CONSTRAINT recommendation_impressions_run_id_posting_id_key UNIQUE (run_id, posting_id);

-- CONSTRAINT: recommendation_impressions recommendation_impressions_user_id_request_key_key
ALTER TABLE ONLY public.recommendation_impressions
    ADD CONSTRAINT recommendation_impressions_user_id_request_key_key UNIQUE (user_id, request_key);

-- CONSTRAINT: recommendation_runs recommendation_runs_id_user_id_key
ALTER TABLE ONLY public.recommendation_runs
    ADD CONSTRAINT recommendation_runs_id_user_id_key UNIQUE (id, user_id);

-- CONSTRAINT: recommendation_runs recommendation_runs_pkey
ALTER TABLE ONLY public.recommendation_runs
    ADD CONSTRAINT recommendation_runs_pkey PRIMARY KEY (id);

-- CONSTRAINT: recommendation_runs recommendation_runs_user_id_request_key_key
ALTER TABLE ONLY public.recommendation_runs
    ADD CONSTRAINT recommendation_runs_user_id_request_key_key UNIQUE (user_id, request_key);

-- CONSTRAINT: recruiter_leads recruiter_leads_pkey
ALTER TABLE ONLY public.recruiter_leads
    ADD CONSTRAINT recruiter_leads_pkey PRIMARY KEY (id);

-- CONSTRAINT: recruiter_leads recruiter_leads_user_id_application_id_email_key
ALTER TABLE ONLY public.recruiter_leads
    ADD CONSTRAINT recruiter_leads_user_id_application_id_email_key UNIQUE (user_id, application_id, email);

-- CONSTRAINT: referral_requests referral_requests_application_id_contact_id_key
ALTER TABLE ONLY public.referral_requests
    ADD CONSTRAINT referral_requests_application_id_contact_id_key UNIQUE (application_id, contact_id);

-- CONSTRAINT: referral_requests referral_requests_pkey
ALTER TABLE ONLY public.referral_requests
    ADD CONSTRAINT referral_requests_pkey PRIMARY KEY (id);

-- CONSTRAINT: resumes resumes_pkey
ALTER TABLE ONLY public.resumes
    ADD CONSTRAINT resumes_pkey PRIMARY KEY (id);

-- CONSTRAINT: resumes resumes_user_id_version_key
ALTER TABLE ONLY public.resumes
    ADD CONSTRAINT resumes_user_id_version_key UNIQUE (user_id, version);

-- CONSTRAINT: tailored_resumes tailored_resumes_application_id_version_key
ALTER TABLE ONLY public.tailored_resumes
    ADD CONSTRAINT tailored_resumes_application_id_version_key UNIQUE (application_id, version);

-- CONSTRAINT: tailored_resumes tailored_resumes_pkey
ALTER TABLE ONLY public.tailored_resumes
    ADD CONSTRAINT tailored_resumes_pkey PRIMARY KEY (id);

-- CONSTRAINT: usage_receipts usage_receipts_pkey
ALTER TABLE ONLY public.usage_receipts
    ADD CONSTRAINT usage_receipts_pkey PRIMARY KEY (user_id, bucket, request_key);

-- CONSTRAINT: usage_windows usage_windows_pkey
ALTER TABLE ONLY public.usage_windows
    ADD CONSTRAINT usage_windows_pkey PRIMARY KEY (user_id, bucket, window_start);

-- CONSTRAINT: user_profiles user_profiles_pkey
ALTER TABLE ONLY public.user_profiles
    ADD CONSTRAINT user_profiles_pkey PRIMARY KEY (id);

-- CONSTRAINT: writing_templates writing_templates_pkey
ALTER TABLE ONLY public.writing_templates
    ADD CONSTRAINT writing_templates_pkey PRIMARY KEY (user_id, kind);

-- INDEX: agent_run_events_parent_owner_idx
CREATE INDEX agent_run_events_parent_owner_idx ON public.agent_run_events USING btree (run_id, user_id);

-- INDEX: agent_run_events_replay_idx
CREATE INDEX agent_run_events_replay_idx ON public.agent_run_events USING btree (run_id, id);

-- INDEX: agent_runs_one_running_user_idx
CREATE UNIQUE INDEX agent_runs_one_running_user_idx ON public.agent_runs USING btree (user_id) WHERE (status = 'running'::text);

-- INDEX: agent_runs_ready_idx
CREATE INDEX agent_runs_ready_idx ON public.agent_runs USING btree (available_at, created_at) WHERE (status = ANY (ARRAY['queued'::text, 'retry_wait'::text, 'running'::text]));

-- INDEX: agent_runs_user_created_idx
CREATE INDEX agent_runs_user_created_idx ON public.agent_runs USING btree (user_id, created_at DESC);

-- INDEX: application_documents_app
CREATE INDEX application_documents_app ON public.application_documents USING btree (application_id);

-- INDEX: application_documents_owner_app
CREATE INDEX application_documents_owner_app ON public.application_documents USING btree (user_id, application_id);

-- INDEX: application_events_owner_session
CREATE INDEX application_events_owner_session ON public.application_events USING btree (user_id, session_id, id);

-- INDEX: application_events_session_owner
CREATE INDEX application_events_session_owner ON public.application_events USING btree (session_id, user_id, id);

-- INDEX: application_sessions_app
CREATE INDEX application_sessions_app ON public.application_execution_sessions USING btree (application_id);

-- INDEX: application_sessions_document
CREATE INDEX application_sessions_document ON public.application_execution_sessions USING btree (document_id, user_id);

-- INDEX: application_sessions_owner_app
CREATE INDEX application_sessions_owner_app ON public.application_execution_sessions USING btree (user_id, application_id, created_at DESC);

-- INDEX: cold_emails_application_idx
CREATE INDEX cold_emails_application_idx ON public.cold_emails USING btree (application_id);

-- INDEX: company_research_owner_app_idx
CREATE INDEX company_research_owner_app_idx ON public.company_research USING btree (user_id, application_id, created_at DESC);

-- INDEX: execution_workers_seen
CREATE INDEX execution_workers_seen ON public.execution_workers USING btree (seen_at);

-- INDEX: job_applications_id_owner_release_idx
CREATE UNIQUE INDEX job_applications_id_owner_release_idx ON public.job_applications USING btree (id, user_id);

-- INDEX: job_applications_user_created_idx
CREATE INDEX job_applications_user_created_idx ON public.job_applications USING btree (user_id, created_at DESC);

-- INDEX: job_postings_id_owner_release_idx
CREATE UNIQUE INDEX job_postings_id_owner_release_idx ON public.job_postings USING btree (id, user_id);

-- INDEX: job_postings_owner_identity_idx
CREATE UNIQUE INDEX job_postings_owner_identity_idx ON public.job_postings USING btree (user_id, dedupe_key) WHERE (dedupe_key <> ''::text);

-- INDEX: job_postings_user_status_idx
CREATE INDEX job_postings_user_status_idx ON public.job_postings USING btree (user_id, status, fit_score DESC);

-- INDEX: mail_one_active_owner_idx
CREATE UNIQUE INDEX mail_one_active_owner_idx ON public.mail_connections USING btree (user_id) WHERE (status = 'active'::text);

-- INDEX: mail_replies_owner_parent_idx
CREATE INDEX mail_replies_owner_parent_idx ON public.mail_replies USING btree (user_id, message_id);

-- INDEX: mail_replies_parent_fk_idx
CREATE INDEX mail_replies_parent_fk_idx ON public.mail_replies USING btree (message_id, user_id);

-- INDEX: network_contacts_user_company_idx
CREATE INDEX network_contacts_user_company_idx ON public.network_contacts USING btree (user_id, company_key);

-- INDEX: outreach_app_fk_idx
CREATE INDEX outreach_app_fk_idx ON public.outreach_messages USING btree (application_id);

-- INDEX: outreach_cold_fk_idx
CREATE INDEX outreach_cold_fk_idx ON public.outreach_messages USING btree (cold_email_id);

-- INDEX: outreach_connection_fk_idx
CREATE INDEX outreach_connection_fk_idx ON public.outreach_messages USING btree (connection_id, user_id);

-- INDEX: outreach_owner_app_idx
CREATE INDEX outreach_owner_app_idx ON public.outreach_messages USING btree (user_id, application_id, created_at DESC);

-- INDEX: outreach_run_fk_idx
CREATE INDEX outreach_run_fk_idx ON public.outreach_messages USING btree (run_id);

-- INDEX: recommendation_feedback_posting_idx
CREATE INDEX recommendation_feedback_posting_idx ON public.recommendation_feedback USING btree (posting_id, user_id);

-- INDEX: recommendation_impressions_owner_idx
CREATE INDEX recommendation_impressions_owner_idx ON public.recommendation_impressions USING btree (user_id, created_at DESC);

-- INDEX: recommendation_impressions_posting_idx
CREATE INDEX recommendation_impressions_posting_idx ON public.recommendation_impressions USING btree (posting_id, user_id);

-- INDEX: recommendation_runs_owner_created_idx
CREATE INDEX recommendation_runs_owner_created_idx ON public.recommendation_runs USING btree (user_id, created_at DESC);

-- INDEX: recruiter_application_fk_idx
CREATE INDEX recruiter_application_fk_idx ON public.recruiter_leads USING btree (application_id);

-- TRIGGER: job_applications job_applications_set_updated_at
CREATE TRIGGER job_applications_set_updated_at BEFORE UPDATE ON public.job_applications FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- TRIGGER: job_postings job_postings_set_updated_at
CREATE TRIGGER job_postings_set_updated_at BEFORE UPDATE ON public.job_postings FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- TRIGGER: network_contacts network_contacts_set_updated_at
CREATE TRIGGER network_contacts_set_updated_at BEFORE UPDATE ON public.network_contacts FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- TRIGGER: qa_answers qa_answers_set_updated_at
CREATE TRIGGER qa_answers_set_updated_at BEFORE UPDATE ON public.qa_answers FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- TRIGGER: referral_requests referral_requests_set_updated_at
CREATE TRIGGER referral_requests_set_updated_at BEFORE UPDATE ON public.referral_requests FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- FK CONSTRAINT: agent_run_events agent_run_events_run_id_user_id_fkey
ALTER TABLE ONLY public.agent_run_events
    ADD CONSTRAINT agent_run_events_run_id_user_id_fkey FOREIGN KEY (run_id, user_id) REFERENCES public.agent_runs(id, user_id) ON DELETE CASCADE;

-- FK CONSTRAINT: agent_run_locks agent_run_locks_user_id_fkey
ALTER TABLE ONLY public.agent_run_locks
    ADD CONSTRAINT agent_run_locks_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: agent_runs agent_runs_user_id_fkey
ALTER TABLE ONLY public.agent_runs
    ADD CONSTRAINT agent_runs_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: application_documents application_documents_application_id_fkey
ALTER TABLE ONLY public.application_documents
    ADD CONSTRAINT application_documents_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.job_applications(id) DEFERRABLE INITIALLY DEFERRED;

-- FK CONSTRAINT: application_documents application_documents_user_id_fkey
ALTER TABLE ONLY public.application_documents
    ADD CONSTRAINT application_documents_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: application_events application_events_session_id_user_id_fkey
ALTER TABLE ONLY public.application_events
    ADD CONSTRAINT application_events_session_id_user_id_fkey FOREIGN KEY (session_id, user_id) REFERENCES public.application_execution_sessions(id, user_id) ON DELETE CASCADE;

-- FK CONSTRAINT: application_events application_events_user_id_fkey
ALTER TABLE ONLY public.application_events
    ADD CONSTRAINT application_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: application_execution_sessions application_execution_sessions_application_id_fkey
ALTER TABLE ONLY public.application_execution_sessions
    ADD CONSTRAINT application_execution_sessions_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.job_applications(id) DEFERRABLE INITIALLY DEFERRED;

-- FK CONSTRAINT: application_execution_sessions application_execution_sessions_document_id_user_id_fkey
ALTER TABLE ONLY public.application_execution_sessions
    ADD CONSTRAINT application_execution_sessions_document_id_user_id_fkey FOREIGN KEY (document_id, user_id) REFERENCES public.application_documents(id, user_id);

-- FK CONSTRAINT: application_execution_sessions application_execution_sessions_user_id_fkey
ALTER TABLE ONLY public.application_execution_sessions
    ADD CONSTRAINT application_execution_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: autopilot_state autopilot_state_user_id_fkey
ALTER TABLE ONLY public.autopilot_state
    ADD CONSTRAINT autopilot_state_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: cold_emails cold_emails_application_id_fkey
ALTER TABLE ONLY public.cold_emails
    ADD CONSTRAINT cold_emails_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.job_applications(id) ON DELETE CASCADE;

-- FK CONSTRAINT: cold_emails cold_emails_user_id_fkey
ALTER TABLE ONLY public.cold_emails
    ADD CONSTRAINT cold_emails_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: company_research company_research_application_id_user_id_fkey
ALTER TABLE ONLY public.company_research
    ADD CONSTRAINT company_research_application_id_user_id_fkey FOREIGN KEY (application_id, user_id) REFERENCES public.job_applications(id, user_id) ON DELETE CASCADE;

-- FK CONSTRAINT: company_research company_research_run_id_user_id_fkey
ALTER TABLE ONLY public.company_research
    ADD CONSTRAINT company_research_run_id_user_id_fkey FOREIGN KEY (run_id, user_id) REFERENCES public.agent_runs(id, user_id) ON DELETE CASCADE;

-- FK CONSTRAINT: extension_tokens extension_tokens_user_id_fkey
ALTER TABLE ONLY public.extension_tokens
    ADD CONSTRAINT extension_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: identity_confirmations identity_confirmations_user_id_fkey
ALTER TABLE ONLY public.identity_confirmations
    ADD CONSTRAINT identity_confirmations_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: job_applications job_applications_user_id_fkey
ALTER TABLE ONLY public.job_applications
    ADD CONSTRAINT job_applications_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: job_postings job_postings_application_id_fkey
ALTER TABLE ONLY public.job_postings
    ADD CONSTRAINT job_postings_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.job_applications(id) ON DELETE SET NULL;

-- FK CONSTRAINT: job_postings job_postings_source_id_fkey
ALTER TABLE ONLY public.job_postings
    ADD CONSTRAINT job_postings_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.job_sources(id) ON DELETE CASCADE;

-- FK CONSTRAINT: job_postings job_postings_user_id_fkey
ALTER TABLE ONLY public.job_postings
    ADD CONSTRAINT job_postings_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: job_sources job_sources_user_id_fkey
ALTER TABLE ONLY public.job_sources
    ADD CONSTRAINT job_sources_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: mail_connections mail_connections_user_id_fkey
ALTER TABLE ONLY public.mail_connections
    ADD CONSTRAINT mail_connections_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: mail_replies mail_replies_message_id_user_id_fkey
ALTER TABLE ONLY public.mail_replies
    ADD CONSTRAINT mail_replies_message_id_user_id_fkey FOREIGN KEY (message_id, user_id) REFERENCES public.outreach_messages(id, user_id) ON DELETE CASCADE;

-- FK CONSTRAINT: mail_replies mail_replies_user_id_fkey
ALTER TABLE ONLY public.mail_replies
    ADD CONSTRAINT mail_replies_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: network_contacts network_contacts_user_id_fkey
ALTER TABLE ONLY public.network_contacts
    ADD CONSTRAINT network_contacts_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: outreach_messages outreach_messages_application_id_fkey
ALTER TABLE ONLY public.outreach_messages
    ADD CONSTRAINT outreach_messages_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.job_applications(id) DEFERRABLE INITIALLY DEFERRED;

-- FK CONSTRAINT: outreach_messages outreach_messages_cold_email_id_fkey
ALTER TABLE ONLY public.outreach_messages
    ADD CONSTRAINT outreach_messages_cold_email_id_fkey FOREIGN KEY (cold_email_id) REFERENCES public.cold_emails(id) ON DELETE SET NULL;

-- FK CONSTRAINT: outreach_messages outreach_messages_connection_id_user_id_fkey
ALTER TABLE ONLY public.outreach_messages
    ADD CONSTRAINT outreach_messages_connection_id_user_id_fkey FOREIGN KEY (connection_id, user_id) REFERENCES public.mail_connections(id, user_id);

-- FK CONSTRAINT: outreach_messages outreach_messages_run_id_fkey
ALTER TABLE ONLY public.outreach_messages
    ADD CONSTRAINT outreach_messages_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.agent_runs(id);

-- FK CONSTRAINT: outreach_messages outreach_messages_user_id_fkey
ALTER TABLE ONLY public.outreach_messages
    ADD CONSTRAINT outreach_messages_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: qa_answers qa_answers_user_id_fkey
ALTER TABLE ONLY public.qa_answers
    ADD CONSTRAINT qa_answers_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: recommendation_feedback recommendation_feedback_posting_id_user_id_fkey
ALTER TABLE ONLY public.recommendation_feedback
    ADD CONSTRAINT recommendation_feedback_posting_id_user_id_fkey FOREIGN KEY (posting_id, user_id) REFERENCES public.job_postings(id, user_id) ON DELETE CASCADE;

-- FK CONSTRAINT: recommendation_impressions recommendation_impressions_posting_id_user_id_fkey
ALTER TABLE ONLY public.recommendation_impressions
    ADD CONSTRAINT recommendation_impressions_posting_id_user_id_fkey FOREIGN KEY (posting_id, user_id) REFERENCES public.job_postings(id, user_id) ON DELETE CASCADE;

-- FK CONSTRAINT: recommendation_impressions recommendation_impressions_run_id_user_id_fkey
ALTER TABLE ONLY public.recommendation_impressions
    ADD CONSTRAINT recommendation_impressions_run_id_user_id_fkey FOREIGN KEY (run_id, user_id) REFERENCES public.recommendation_runs(id, user_id) ON DELETE CASCADE;

-- FK CONSTRAINT: recommendation_runs recommendation_runs_user_id_fkey
ALTER TABLE ONLY public.recommendation_runs
    ADD CONSTRAINT recommendation_runs_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: recruiter_leads recruiter_leads_application_id_fkey
ALTER TABLE ONLY public.recruiter_leads
    ADD CONSTRAINT recruiter_leads_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.job_applications(id) ON DELETE CASCADE;

-- FK CONSTRAINT: recruiter_leads recruiter_leads_user_id_fkey
ALTER TABLE ONLY public.recruiter_leads
    ADD CONSTRAINT recruiter_leads_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: referral_requests referral_requests_application_id_fkey
ALTER TABLE ONLY public.referral_requests
    ADD CONSTRAINT referral_requests_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.job_applications(id) ON DELETE CASCADE;

-- FK CONSTRAINT: referral_requests referral_requests_contact_id_fkey
ALTER TABLE ONLY public.referral_requests
    ADD CONSTRAINT referral_requests_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES public.network_contacts(id) ON DELETE CASCADE;

-- FK CONSTRAINT: referral_requests referral_requests_user_id_fkey
ALTER TABLE ONLY public.referral_requests
    ADD CONSTRAINT referral_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: resumes resumes_user_id_fkey
ALTER TABLE ONLY public.resumes
    ADD CONSTRAINT resumes_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: tailored_resumes tailored_resumes_application_id_fkey
ALTER TABLE ONLY public.tailored_resumes
    ADD CONSTRAINT tailored_resumes_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.job_applications(id) ON DELETE CASCADE;

-- FK CONSTRAINT: tailored_resumes tailored_resumes_user_id_fkey
ALTER TABLE ONLY public.tailored_resumes
    ADD CONSTRAINT tailored_resumes_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: usage_receipts usage_receipts_user_id_fkey
ALTER TABLE ONLY public.usage_receipts
    ADD CONSTRAINT usage_receipts_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: usage_windows usage_windows_user_id_fkey
ALTER TABLE ONLY public.usage_windows
    ADD CONSTRAINT usage_windows_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: user_profiles user_profiles_id_fkey
ALTER TABLE ONLY public.user_profiles
    ADD CONSTRAINT user_profiles_id_fkey FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- FK CONSTRAINT: writing_templates writing_templates_user_id_fkey
ALTER TABLE ONLY public.writing_templates
    ADD CONSTRAINT writing_templates_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
