-- Sprint 2: durable runs, worker leases, transactional application saving and replay.
create table public.agent_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null check (kind in ('application','scan','digest')),
  idempotency_key text not null check (length(idempotency_key) between 1 and 200),
  inputs jsonb not null default '{}', checkpoints jsonb not null default '{}',
  result jsonb not null default '{}',
  status text not null default 'queued' check (status in ('queued','running','retry_wait','succeeded','failed')),
  stage text not null default 'queued', attempts integer not null default 0,
  max_attempts integer not null default 3 check (max_attempts between 1 and 10),
  worker_id text, lease_token uuid, lease_expires_at timestamptz,
  available_at timestamptz not null default now(), last_error text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(user_id, kind, idempotency_key), unique(id, user_id)
);
create index agent_runs_ready_idx on public.agent_runs(available_at, created_at)
  where status in ('queued','retry_wait','running');
create index agent_runs_user_created_idx on public.agent_runs(user_id, created_at desc);
create unique index agent_runs_one_running_user_idx on public.agent_runs(user_id) where status='running';

create table public.agent_run_events (
  id bigint generated always as identity primary key,
  run_id uuid not null, user_id uuid not null, event jsonb not null,
  created_at timestamptz not null default now(),
  foreign key(run_id,user_id) references public.agent_runs(id,user_id) on delete cascade
);
create index agent_run_events_replay_idx on public.agent_run_events(run_id,id);
create table public.agent_run_locks (
  user_id uuid primary key references auth.users(id) on delete cascade
);

alter table public.agent_runs enable row level security;
alter table public.agent_run_events enable row level security;
alter table public.agent_run_locks enable row level security;
create policy run_owner_read on public.agent_runs for select to authenticated
  using (user_id = (select auth.uid()));
create policy run_event_owner_read on public.agent_run_events for select to authenticated
  using (user_id = (select auth.uid()));
revoke all on public.agent_runs, public.agent_run_events, public.agent_run_locks from anon, authenticated;
grant select on public.agent_runs, public.agent_run_events to authenticated;
grant all on public.agent_runs, public.agent_run_events, public.agent_run_locks to service_role;
grant usage, select on sequence public.agent_run_events_id_seq to service_role;

create function public.enqueue_agent_run(p_user_id uuid, p_kind text, p_inputs jsonb, p_key text,
  p_available_at timestamptz default now(), p_parent_id uuid default null, p_parent_token uuid default null)
returns jsonb language plpgsql security invoker set search_path='' as $$
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

create function public.claim_agent_run(p_worker text, p_lease_seconds integer default 120)
returns jsonb language plpgsql security invoker set search_path='' as $$
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

create function public.renew_agent_run(p_run_id uuid,p_token uuid,p_lease_seconds integer default 120)
returns boolean language plpgsql security invoker set search_path='' as $$
begin
  if p_lease_seconds not between 30 and 1800 then raise exception 'invalid_lease_duration'; end if;
  update public.agent_runs set lease_expires_at=clock_timestamp()+make_interval(secs=>p_lease_seconds),updated_at=clock_timestamp()
    where id=p_run_id and lease_token=p_token and status='running' and lease_expires_at>clock_timestamp();
  return found;
end $$;

create function public.checkpoint_agent_run(p_run_id uuid,p_token uuid,p_stage text,p_value jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare r public.agent_runs;
begin
  update public.agent_runs set checkpoints=jsonb_set(checkpoints,array[p_stage],p_value),
    stage=p_stage,updated_at=clock_timestamp()
    where id=p_run_id and lease_token=p_token and status='running' and lease_expires_at>clock_timestamp() returning * into r;
  if not found then raise exception 'lease_lost'; end if;
  return to_jsonb(r);
end $$;

create function public.append_agent_run_event(p_run_id uuid,p_token uuid,p_event jsonb)
returns bigint language plpgsql security invoker set search_path='' as $$
declare r public.agent_runs; event_id bigint;
begin
  select * into r from public.agent_runs where id=p_run_id and lease_token=p_token
    and status='running' and lease_expires_at>clock_timestamp() for update;
  if not found then raise exception 'lease_lost'; end if;
  insert into public.agent_run_events(run_id,user_id,event) values(r.id,r.user_id,p_event) returning id into event_id;
  return event_id;
end $$;

create function public.finish_agent_run(p_run_id uuid,p_token uuid,p_status text,p_result jsonb default '{}',p_error text default null,p_delay integer default 0)
returns jsonb language plpgsql security invoker set search_path='' as $$
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

create function public.save_run_application(p_run_id uuid,p_token uuid,p_application jsonb,p_tailored jsonb,p_emails jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
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

create function public.save_run_referral(p_run_id uuid,p_token uuid,p_contact_id uuid,p_message text)
returns boolean language plpgsql security invoker set search_path='' as $$
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

create function public.save_run_prepared(p_run_id uuid,p_token uuid,p_application_id uuid,p_prepared jsonb)
returns boolean language plpgsql security invoker set search_path='' as $$
declare r public.agent_runs;
begin
  select * into r from public.agent_runs where id=p_run_id and lease_token=p_token and status='running'
    and lease_expires_at>clock_timestamp() for update;
  if not found then raise exception 'lease_lost'; end if;
  if r.checkpoints->'database_saving'->>'application_id' is distinct from p_application_id::text then raise exception 'application_not_owned'; end if;
  update public.job_applications set prepared_form=p_prepared where id=p_application_id and user_id=r.user_id;
  return found;
end $$;

-- Workers alone can mutate execution state. No SECURITY DEFINER RPCs are needed.
create function public.retry_agent_run(p_run_id uuid,p_user_id uuid)
returns jsonb language plpgsql security invoker set search_path='' as $$
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

do $$
declare f regprocedure;
begin
  for f in select p.oid::regprocedure from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and p.proname in ('enqueue_agent_run','claim_agent_run','renew_agent_run',
      'checkpoint_agent_run','append_agent_run_event','finish_agent_run','save_run_application','save_run_referral','save_run_prepared','retry_agent_run')
  loop
    execute format('revoke all on function %s from public, anon, authenticated',f);
    execute format('grant execute on function %s to service_role',f);
  end loop;
end $$;
