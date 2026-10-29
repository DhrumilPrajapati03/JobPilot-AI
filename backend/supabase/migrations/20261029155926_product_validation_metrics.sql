-- Operational heartbeat data is service-role only; never exposed to app users.
create table public.execution_workers (
  id uuid primary key,
  seen_at timestamptz not null default clock_timestamp(),
  last_poll_at timestamptz,
  active_run_id uuid
);
create index execution_workers_seen on public.execution_workers(seen_at);
alter table public.execution_workers enable row level security;
revoke all on public.execution_workers from public,anon,authenticated;
grant all on public.execution_workers to service_role;
create policy execution_workers_service_only on public.execution_workers for all to service_role using(true) with check(true);
-- active_run_id is a diagnostic reference, not a FK; completed run retention
-- must not be coupled to stale process heartbeats.
create function public.heartbeat_execution_worker(p_worker uuid,p_last_poll timestamptz,p_active_run uuid default null)
returns boolean language plpgsql security invoker set search_path='' as $$
begin
  delete from public.execution_workers where seen_at<clock_timestamp()-interval '1 day';
  insert into public.execution_workers(id,last_poll_at,active_run_id) values(p_worker,p_last_poll,p_active_run)
    on conflict(id) do update set seen_at=clock_timestamp(),last_poll_at=excluded.last_poll_at,active_run_id=excluded.active_run_id;
  return true;
end $$;
create function public.get_execution_health()
returns jsonb language sql security invoker set search_path='' as $$
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
revoke all on function public.heartbeat_execution_worker(uuid,timestamptz,uuid),public.get_execution_health() from public,anon,authenticated;
grant execute on function public.heartbeat_execution_worker(uuid,timestamptz,uuid),public.get_execution_health() to service_role;

-- Read-only invoker aggregate. RLS remains in force, and every input relation
-- explicitly filters auth.uid(). No document bytes or mail bodies are read.
create function public.get_product_metrics()
returns jsonb language sql stable security invoker set search_path='' as $$
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
$$;
revoke all on function public.get_product_metrics() from public,anon;
grant execute on function public.get_product_metrics() to authenticated;
