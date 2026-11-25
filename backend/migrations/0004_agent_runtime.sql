-- Agent runtime (plan sections 3, 4, 7.1; Day 3): agents are data (agent_spec), every step
-- is traced (run_step), routines are scheduled with catch-up-on-wake, cases remember the
-- posting Scout found them from.

create table public.agent_spec (
  id text primary key check (id ~ '^[a-z][a-z0-9_]{1,39}$'),
  owner text not null check (owner in ('builtin','user')),
  user_id uuid references auth.users(id) on delete cascade,   -- null for built-ins
  name text not null,
  role text not null default '',              -- one line for the roster
  description text not null default '',
  instructions text not null default '',
  policy_notes text not null default '',
  model jsonb not null default '{}'::jsonb,   -- {provider, model, fallback}
  tools text[] not null default '{}',
  inputs jsonb not null default '[]'::jsonb,
  outputs jsonb not null default '[]'::jsonb,
  triggers jsonb not null default '[]'::jsonb,
  action_kinds text[] not null default '{}',
  budgets jsonb not null default '{}'::jsonb,
  autonomy jsonb not null default '{}'::jsonb,
  status text not null default 'active' check (status in ('active','paused','draft')),
  version integer not null default 1,
  spec_sha256 text not null check (spec_sha256 ~ '^[0-9a-f]{64}$'),
  updated_at timestamptz not null default now(),
  check ((owner = 'builtin') = (user_id is null))
);

create table public.run_step (
  id bigint generated always as identity primary key,
  run_id uuid references public.agent_runs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  case_id uuid references public.job_case(id) on delete cascade,
  agent text not null,
  kind text not null check (kind in ('llm','tool','route','artifact','note','error','blocked')),
  name text not null default '',
  summary text not null default '',      -- plain words, shown on hover in the roster
  detail jsonb not null default '{}'::jsonb,   -- redacted input/output for the Details toggle
  tokens integer not null default 0,
  duration_ms integer not null default 0,
  at timestamptz not null default now()
);
create index run_step_agent_idx on public.run_step (user_id, agent, at desc);
create index run_step_run_idx on public.run_step (run_id, id);
create index run_step_case_idx on public.run_step (case_id, at);

create table public.routine (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  key text not null check (key ~ '^[a-z][a-z0-9_]{1,59}$'),
  agent text not null,                    -- owning expert (its thread shows the results)
  name text not null,
  kind text not null check (kind in ('scout_scan','backup')),
  schedule jsonb not null,                -- {"kind": "daily", "hour": 5}
  params jsonb not null default '{}'::jsonb,
  enabled boolean not null default true,
  last_due_on date,                       -- the local day the last run was scheduled for
  last_run_at timestamptz,
  last_run_id uuid,
  last_status text,
  created_at timestamptz not null default now(),
  unique (user_id, key)
);

alter table public.job_case add column posting_id uuid references public.job_postings(id) on delete set null;
create unique index job_case_posting_idx on public.job_case (user_id, posting_id) where posting_id is not null;

alter table public.agent_runs drop constraint agent_runs_kind_check;
alter table public.agent_runs add constraint agent_runs_kind_check check (kind in
  ('application','scan','digest','mail_send','mail_sync','company_research','recommendation','backup','agent'));
insert into public.run_kind_limits values ('agent', 3);

-- Expert runs without a case (Scout's scan) are one at a time per expert.
create or replace function public.agent_run_concurrency_default() returns trigger
  language plpgsql set search_path to '' as $$
begin
  if new.concurrency_key is null then
    new.concurrency_key = new.user_id::text || ':' || case
      when new.case_id is not null then 'case:' || new.case_id::text
      when new.kind = 'agent' and new.inputs->>'agent' is not null then 'agent:' || (new.inputs->>'agent')
      when new.kind = 'application' and new.inputs->>'posting_id' is not null then 'posting:' || (new.inputs->>'posting_id')
      when new.kind = 'mail_send' and new.inputs->>'message_id' is not null then 'mail:' || (new.inputs->>'message_id')
      when new.kind = 'company_research' and new.inputs->>'application_id' is not null then 'research:' || (new.inputs->>'application_id')
      when new.kind in ('scan','digest','mail_sync','recommendation','backup') then 'kind:' || new.kind
      else 'run:' || new.id::text end;
  end if;
  return new;
end $$;
