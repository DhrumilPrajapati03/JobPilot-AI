-- JobDots spine (plan sections 4, 4.1, 5, 5.1, 9.2; Day 2).
-- Every table carries user_id (the single owner today), so a later multi-user move is a
-- migration, not a rewrite.

-- ---------------------------------------------------------------- cases and timeline
create table public.job_case (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  source_url text not null default '',
  company text not null default '',
  role text not null default '',
  jd_text text not null default '',
  jd_analysis jsonb,
  stage text not null default 'found' check (stage in
    ('found','tailored','researched','ready','applied','replied','interview','offer','closed')),
  status text not null default 'open' check (status in ('open','paused','closed')),
  fit_score real,
  fit_score_legacy real,
  notes text not null default '',
  applied_at timestamptz,
  follow_up_at timestamptz,
  legacy boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index job_case_owner_stage_idx on public.job_case (user_id, stage, updated_at desc);
create trigger job_case_updated_at before update on public.job_case
  for each row execute function public.set_updated_at();

create table public.case_event (
  id bigint generated always as identity primary key,
  case_id uuid not null references public.job_case(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null check (length(kind) between 1 and 60),
  actor text not null check (actor in ('agent','user','courier','system','legacy')),
  actor_name text not null default '',
  summary text not null default '',
  data jsonb not null default '{}'::jsonb,
  at timestamptz not null default now()
);
create index case_event_case_idx on public.case_event (case_id, at, id);

create table public.artifact (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  case_id uuid references public.job_case(id) on delete cascade,
  kind text not null check (kind in ('resume_version','company_brief','comp_report','contact_list',
    'draft','answer_set','interview_prep')),
  version integer not null default 1 check (version >= 1),
  title text not null default '',
  content jsonb not null default '{}'::jsonb,
  file_path text,
  file_sha256 text check (file_sha256 is null or file_sha256 ~ '^[0-9a-f]{64}$'),
  created_by text not null default '',
  legacy boolean not null default false,
  created_at timestamptz not null default now()
);
create index artifact_case_idx on public.artifact (case_id, kind, created_at);

-- ---------------------------------------------------------------- actions and approvals
-- State machine (plan section 4): proposed -> reviewed -> approved -> executing ->
-- provider_accepted -> delivered | failed | cancelled, plus send_unknown (a send whose
-- outcome is unknown; it is never retried blindly) and blocked (refused by policy).
create table public.action (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  case_id uuid references public.job_case(id) on delete set null,
  kind text not null check (kind ~ '^[a-z][a-z0-9_]{1,59}$'),
  mode text not null check (mode in ('act','act_with_preview','ask_first','hand_off','never')),
  agent text not null default '',
  payload jsonb not null,
  payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  revision integer not null default 1 check (revision >= 1),  -- +1 on every edit
  status text not null default 'proposed' check (status in ('proposed','reviewed','approved','executing',
    'provider_accepted','delivered','failed','cancelled','send_unknown','blocked')),
  idempotency_key text not null check (length(idempotency_key) between 1 and 200),
  review jsonb not null default '{}'::jsonb,
  block_reason text,
  provider_ref text,
  error text,
  executing_at timestamptz,       -- when Courier started it; caps count from here
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, idempotency_key)
);
create index action_owner_status_idx on public.action (user_id, status, created_at);
create index action_case_idx on public.action (case_id, created_at);
create index action_kind_executing_idx on public.action (user_id, kind, executing_at) where executing_at is not null;

create table public.approval (
  id uuid primary key default gen_random_uuid(),
  action_id uuid not null references public.action(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  decision text not null check (decision in ('approved','rejected')),
  payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  channel text not null check (channel in ('web','telegram','extension','auto','api')),
  note text not null default '',
  decided_at timestamptz not null default now()
);
create index approval_action_idx on public.approval (action_id, decided_at);

-- Allowed transitions; anything else is refused in the database as well as in code.
create function public.action_transition_allowed(p_from text, p_to text) returns boolean
  language sql immutable set search_path to '' as $$
  select (p_from, p_to) in (
    ('proposed','reviewed'), ('proposed','blocked'), ('proposed','cancelled'),
    ('reviewed','approved'), ('reviewed','proposed'), ('reviewed','blocked'), ('reviewed','cancelled'),
    ('approved','executing'), ('approved','proposed'), ('approved','cancelled'), ('approved','blocked'),
    ('executing','provider_accepted'), ('executing','failed'), ('executing','send_unknown'), ('executing','delivered'),
    ('provider_accepted','delivered'), ('provider_accepted','failed'),
    ('send_unknown','provider_accepted'), ('send_unknown','delivered'), ('send_unknown','failed'),
    ('blocked','cancelled'), ('failed','cancelled'))
$$;

create function public.action_guard() returns trigger
  language plpgsql set search_path to '' as $$
begin
  if tg_op = 'INSERT' then
    if new.status not in ('proposed','blocked') then raise exception 'action_must_start_proposed'; end if;
    return new;
  end if;
  if new.user_id <> old.user_id or new.kind <> old.kind or new.idempotency_key <> old.idempotency_key then
    raise exception 'action_identity_immutable';
  end if;
  if new.payload is distinct from old.payload or new.payload_sha256 <> old.payload_sha256 then
    -- Editing is only possible before execution, and it always clears the approval.
    if old.status not in ('proposed','reviewed','approved') or new.status <> 'proposed' then
      raise exception 'action_payload_frozen';
    end if;
  end if;
  if new.status <> old.status then
    if not public.action_transition_allowed(old.status, new.status) then
      raise exception 'invalid_action_transition: % -> %', old.status, new.status;
    end if;
    if new.status = 'approved' and not exists (select 1 from public.approval a where a.action_id = new.id
        and a.decision = 'approved' and a.payload_sha256 = new.payload_sha256) then
      raise exception 'approval_required';
    end if;
    if new.status = 'executing' then
      if new.mode in ('hand_off','never') then raise exception 'action_not_executable'; end if;
      new.executing_at = clock_timestamp();
    end if;
  end if;
  new.updated_at = clock_timestamp();
  return new;
end $$;
create trigger action_guard before insert or update on public.action
  for each row execute function public.action_guard();

create table public.budget_ledger (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  case_id uuid references public.job_case(id) on delete set null,
  run_id uuid references public.agent_runs(id) on delete set null,
  agent text not null default '',
  unit text not null check (unit in ('steps','tokens','seconds','usd')),
  amount numeric not null check (amount >= 0),
  at timestamptz not null default now()
);
create index budget_ledger_case_idx on public.budget_ledger (case_id, unit);
create index budget_ledger_owner_at_idx on public.budget_ledger (user_id, unit, at);

-- ---------------------------------------------------------------- contacts and answers
create table public.contact (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  company text not null default '',
  name text not null default '',
  title text not null default '',
  linkedin_url text not null default '',
  email text not null default '',
  x_handle text not null default '',
  role_class text not null default 'unknown' check (role_class in
    ('recruiter','hiring_manager','ceo','cto','employee','unknown')),
  stage text not null default 'discovered' check (stage in ('unknown','discovered','classified','invite_proposed',
    'invite_approved','invite_sent','accepted','message_proposed','message_approved','message_sent','replied',
    'no_reply','follow_up','closed')),
  source text not null default '',
  confidence real,
  dedupe_key text not null,
  notes text not null default '',
  legacy boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, dedupe_key)
);
create trigger contact_updated_at before update on public.contact
  for each row execute function public.set_updated_at();

create table public.contact_touch (
  id bigint generated always as identity primary key,
  contact_id uuid not null references public.contact(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  case_id uuid references public.job_case(id) on delete set null,
  channel text not null check (channel in ('email','linkedin_invite','linkedin_dm','referral','x','reddit','other')),
  action_id uuid references public.action(id) on delete set null,
  sent_at timestamptz,
  outcome text not null default '',
  legacy boolean not null default false
);
create index contact_touch_contact_idx on public.contact_touch (contact_id, sent_at);

create table public.answer_bank (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  question_text text not null,
  normalized_question text not null,
  answer text not null default '',
  type text not null default 'text',
  embedding vector,
  embedding_model text,
  source text not null check (source in ('legacy','vault','reused','adapted','generated','user')),
  version integer not null default 1,
  approved_at timestamptz,
  company_scope text not null default '',
  sensitive boolean not null default false,
  created_at timestamptz not null default now()
);
create index answer_bank_owner_idx on public.answer_bank (user_id, normalized_question);

-- ---------------------------------------------------------------- login (plan section 4.1)
create table public.login_identity (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  provider text not null check (provider in ('google','github')),
  provider_user_id text not null check (length(provider_user_id) between 1 and 255),
  email text not null default '',
  display_name text not null default '',
  linked_at timestamptz not null default now(),
  last_login_at timestamptz,
  unique (provider, provider_user_id),
  unique (user_id, provider)
);

create table public.session (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
  method text not null check (method in ('google','github','bearer')),
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz,
  user_agent text not null default ''
);
create index session_owner_idx on public.session (user_id, expires_at);

create table public.oauth_state (
  state_hash text primary key check (state_hash ~ '^[0-9a-f]{64}$'),
  provider text not null check (provider in ('google','github')),
  intent text not null check (intent in ('login','link')),
  code_verifier text not null,
  nonce text not null default '',
  user_id uuid references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);

-- ---------------------------------------------------------------- import, backups, evals
create table public.legacy_import (
  id bigint generated always as identity primary key,
  source_table text not null,
  legacy_id text not null,
  target_table text not null,
  target_id text not null,
  raw jsonb not null,
  raw_sha256 text not null check (raw_sha256 ~ '^[0-9a-f]{64}$'),
  imported_at timestamptz not null default now(),
  unique (source_table, legacy_id, target_table)
);

create table public.backup_log (
  id bigint generated always as identity primary key,
  file_name text not null,
  tier text not null default 'daily' check (tier in ('daily','weekly')),
  size_bytes bigint,
  sha256 text,
  md5 text,
  destination text not null default 'drive' check (destination in ('drive','local')),
  drive_file_id text,
  status text not null default 'started' check (status in ('started','verified','failed','pruned')),
  error text,
  started_at timestamptz not null default now(),
  verified_at timestamptz,
  local_deleted_at timestamptz
);
create index backup_log_status_idx on public.backup_log (status, started_at desc);

create table public.eval_result (
  id bigint generated always as identity primary key,
  agent text not null,
  dataset text not null,
  metric text not null,
  score double precision not null,
  model text not null default '',
  details jsonb not null default '{}'::jsonb,
  run_at timestamptz not null default now()
);
create index eval_result_agent_idx on public.eval_result (agent, dataset, run_at desc);

-- ---------------------------------------------------------------- per-case concurrency
-- The old queue ran one job per user at a time, which would serialise every expert.
-- Now a run waits only for runs with the same concurrency key (same case, same posting,
-- same mail message, or a singleton kind such as the daily scan) and for its kind's cap.
drop index public.agent_runs_one_running_user_idx;
alter table public.agent_runs drop constraint agent_runs_kind_check;
alter table public.agent_runs add constraint agent_runs_kind_check check (kind in
  ('application','scan','digest','mail_send','mail_sync','company_research','recommendation','backup'));
alter table public.agent_runs add column case_id uuid references public.job_case(id) on delete set null;
alter table public.agent_runs add column concurrency_key text;
create index agent_runs_concurrency_idx on public.agent_runs (concurrency_key) where status = 'running';

create table public.run_kind_limits (
  kind text primary key,
  max_running integer not null check (max_running between 1 and 20)
);
insert into public.run_kind_limits values
  ('application', 2), ('company_research', 2), ('mail_send', 1), ('mail_sync', 1),
  ('scan', 1), ('digest', 1), ('recommendation', 1), ('backup', 1);

create function public.agent_run_concurrency_default() returns trigger
  language plpgsql set search_path to '' as $$
begin
  if new.concurrency_key is null then
    new.concurrency_key = new.user_id::text || ':' || case
      when new.case_id is not null then 'case:' || new.case_id::text
      when new.kind = 'application' and new.inputs->>'posting_id' is not null then 'posting:' || (new.inputs->>'posting_id')
      when new.kind = 'mail_send' and new.inputs->>'message_id' is not null then 'mail:' || (new.inputs->>'message_id')
      when new.kind = 'company_research' and new.inputs->>'application_id' is not null then 'research:' || (new.inputs->>'application_id')
      when new.kind in ('scan','digest','mail_sync','recommendation','backup') then 'kind:' || new.kind
      else 'run:' || new.id::text end;
  end if;
  return new;
end $$;
create trigger agent_runs_concurrency_default before insert on public.agent_runs
  for each row execute function public.agent_run_concurrency_default();
update public.agent_runs set concurrency_key = user_id::text || ':run:' || id::text where concurrency_key is null;
alter table public.agent_runs alter column concurrency_key set not null;

drop function public.enqueue_agent_run(uuid, text, jsonb, text, timestamptz, uuid, uuid);
create function public.enqueue_agent_run(p_user_id uuid, p_kind text, p_inputs jsonb, p_key text,
    p_available_at timestamptz default now(), p_parent_id uuid default null, p_parent_token uuid default null,
    p_case_id uuid default null) returns jsonb
  language plpgsql set search_path to '' as $$
declare r public.agent_runs;
begin
  if p_parent_id is not null then
    perform 1 from public.agent_runs where id=p_parent_id and user_id=p_user_id and status='running'
      and lease_token=p_parent_token and lease_expires_at>clock_timestamp() for update;
    if not found then raise exception 'lease_lost'; end if;
  end if;
  if p_case_id is not null and not exists(select 1 from public.job_case where id=p_case_id and user_id=p_user_id) then
    raise exception 'case_not_found';
  end if;
  insert into public.agent_runs(user_id,kind,inputs,idempotency_key,available_at,case_id)
    values(p_user_id,p_kind,p_inputs,p_key,p_available_at,p_case_id)
    on conflict(user_id,kind,idempotency_key) do nothing returning * into r;
  if r.id is null then
    select * into strict r from public.agent_runs where user_id=p_user_id and kind=p_kind and idempotency_key=p_key;
    if (r.inputs - 'auto')<>(p_inputs - 'auto') or r.case_id is distinct from p_case_id then
      raise exception 'idempotency_key_conflict';
    end if;
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

drop function public.claim_agent_run(text, integer);
create function public.claim_agent_run(p_worker text, p_lease_seconds integer default 120) returns jsonb
  language plpgsql set search_path to '' as $$
declare r public.agent_runs; kind_cap integer;
begin
  if p_lease_seconds not between 30 and 1800 then raise exception 'invalid_lease_duration'; end if;
  for r in select q.* from public.agent_runs q
    where ((q.status in ('queued','retry_wait') and q.available_at<=clock_timestamp())
      or (q.status='running' and q.lease_expires_at<=clock_timestamp()))
      and not exists(select 1 from public.agent_runs active where active.concurrency_key=q.concurrency_key
        and active.id<>q.id and active.status='running')
    order by q.available_at,q.created_at limit 100 for update skip locked
  loop
    -- Two workers must not both start runs that share a key or overfill a kind's cap.
    if not pg_try_advisory_xact_lock(hashtextextended('run-key:'||r.concurrency_key,0)) then continue; end if;
    if not pg_try_advisory_xact_lock(hashtextextended('run-kind:'||r.kind,0)) then continue; end if;
    if exists(select 1 from public.agent_runs active where active.concurrency_key=r.concurrency_key
        and active.id<>r.id and active.status='running') then continue; end if;
    select max_running into kind_cap from public.run_kind_limits where kind=r.kind;
    if (select count(*) from public.agent_runs active where active.kind=r.kind and active.id<>r.id
        and active.status='running') >= coalesce(kind_cap,1) then continue; end if;
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
