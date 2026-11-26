-- Courier, connections and Telegram (plan sections 4, 9.4; Day 5).

-- Approval order must not depend on the clock (Docker's VM clock can step backwards):
-- autonomy counts "the last N approvals" by this sequence.
alter table public.approval add column seq bigint generated always as identity;
create index approval_seq_idx on public.approval (user_id, seq desc);

-- Connections hold OAuth secrets for the token broker, encrypted with ENCRYPTION_KEY.
-- Agents never read this table; only Courier executors do.
create table public.connection (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  provider text not null check (provider in ('google')),
  account_email text not null default '',
  scopes text[] not null default '{}',
  secret_enc text not null,                 -- Fernet token of the refresh token
  status text not null default 'active' check (status in ('active','expired','revoked')),
  connected_at timestamptz not null default now(),
  expires_hint timestamptz,                 -- Testing-mode refresh tokens end after 7 days
  warned_at timestamptz,
  last_error text,
  unique (user_id, provider)
);

-- Telegram: the one allowed chat, the long-polling offset, and which approval messages went out.
create table public.telegram_state (
  user_id uuid primary key references auth.users(id) on delete cascade,
  chat_id bigint not null,
  update_offset bigint not null default 0,
  linked_at timestamptz not null default now()
);

create table public.telegram_message (
  action_id uuid primary key references public.action(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  chat_id bigint not null,
  message_id bigint not null,
  notified_status text not null,            -- the action status the message last showed
  sent_at timestamptz not null default now()
);

alter table public.agent_runs drop constraint agent_runs_kind_check;
alter table public.agent_runs add constraint agent_runs_kind_check check (kind in
  ('application','scan','digest','mail_send','mail_sync','company_research','recommendation','backup','agent','courier'));
insert into public.run_kind_limits values ('courier', 1);

-- Courier runs for one action never overlap.
create or replace function public.agent_run_concurrency_default() returns trigger
  language plpgsql set search_path to '' as $$
begin
  if new.concurrency_key is null then
    new.concurrency_key = new.user_id::text || ':' || case
      when new.kind = 'courier' and new.inputs->>'action_id' is not null then 'action:' || (new.inputs->>'action_id')
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
