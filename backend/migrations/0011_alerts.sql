-- Hardening (plan section 9; Day 16): Telegram alerts, each sent once.
alter table public.telegram_state add column alert_event_id bigint not null default 0;  -- last case_event forwarded
create table public.telegram_alert (
  user_id uuid not null references auth.users(id) on delete cascade,
  key text not null,                       -- what it was about, e.g. failing:connector:2026-11-28
  sent_at timestamptz not null default now(),
  primary key (user_id, key)
);
