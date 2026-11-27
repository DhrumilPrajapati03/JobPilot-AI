-- Inbox (plan sections 2.1, 2.4; Day 10): what Inbox read from Gmail, acceptances, and
-- routines that run every N minutes.

-- One row per Gmail message Inbox handled (never processed twice). Bodies are not stored;
-- a short snippet is, for the case timeline.
create table public.inbox_message (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  gmail_id text not null,
  thread_id text not null default '',
  case_id uuid references public.job_case(id) on delete set null,
  contact_id uuid references public.contact(id) on delete set null,
  action_id uuid references public.action(id) on delete set null,     -- the email it answers, when known
  kind text not null check (kind in ('reply','interview','rejection','auto_reply','accepted','other')),
  from_email text not null default '',
  from_name text not null default '',
  subject text not null default '',
  snippet text not null default '',
  received_at timestamptz not null,
  created_at timestamptz not null default now(),
  unique (user_id, gmail_id)
);
create index inbox_message_case_idx on public.inbox_message (user_id, case_id, received_at desc);
create index inbox_message_thread_idx on public.inbox_message (user_id, thread_id);

-- When someone accepted your LinkedIn invitation (from LinkedIn's own notification email).
alter table public.contact add column accepted_at timestamptz;

-- Routines owned by an expert that run on an interval (Inbox polling) or daily (follow-ups).
alter table public.routine drop constraint routine_kind_check;
alter table public.routine add constraint routine_kind_check check (kind in ('scout_scan','backup','expert'));
alter table public.routine add column task text not null default '';

-- The Gmail thread of a sent email, so Inbox can match replies and follow-ups stay in it.
alter table public.action add column thread_id text;
