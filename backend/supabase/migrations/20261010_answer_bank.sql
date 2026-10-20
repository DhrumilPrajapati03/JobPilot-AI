-- JobPilot AI: answer bank for application screening questions.
-- Run once in the Supabase SQL editor.

create table if not exists public.qa_answers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  question text not null,
  answer text not null default '',
  category text not null default 'custom',
  -- Sensitive answers (e.g. EEO self-identification) are never sent to an LLM.
  sensitive boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, question)
);

alter table public.qa_answers enable row level security;

-- Also defined by 20261006_application_materials.sql; repeated so this file runs on its own.
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop policy if exists "qa_answers_select_own" on public.qa_answers;
create policy "qa_answers_select_own" on public.qa_answers for select using (auth.uid() = user_id);

drop policy if exists "qa_answers_insert_own" on public.qa_answers;
create policy "qa_answers_insert_own" on public.qa_answers for insert with check (auth.uid() = user_id);

drop policy if exists "qa_answers_update_own" on public.qa_answers;
create policy "qa_answers_update_own" on public.qa_answers for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "qa_answers_delete_own" on public.qa_answers;
create policy "qa_answers_delete_own" on public.qa_answers for delete using (auth.uid() = user_id);

drop trigger if exists qa_answers_set_updated_at on public.qa_answers;
create trigger qa_answers_set_updated_at
  before update on public.qa_answers
  for each row execute function public.set_updated_at();
