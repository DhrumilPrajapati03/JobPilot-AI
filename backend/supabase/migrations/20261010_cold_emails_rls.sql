-- JobPilot AI: let users manage email drafts for applications they own.
-- cold_emails has no user_id of its own; ownership comes from the parent job_application.
-- Run once in the Supabase SQL editor. Safe to re-run.
--
-- Policies are permissive (OR-ed), so these grant access alongside any existing ones.

alter table public.cold_emails enable row level security;

drop policy if exists "cold_emails_select_own_application" on public.cold_emails;
create policy "cold_emails_select_own_application" on public.cold_emails
  for select using (
    exists (select 1 from public.job_applications a where a.id = cold_emails.application_id and a.user_id = auth.uid())
  );

drop policy if exists "cold_emails_insert_own_application" on public.cold_emails;
create policy "cold_emails_insert_own_application" on public.cold_emails
  for insert with check (
    exists (select 1 from public.job_applications a where a.id = cold_emails.application_id and a.user_id = auth.uid())
  );

drop policy if exists "cold_emails_update_own_application" on public.cold_emails;
create policy "cold_emails_update_own_application" on public.cold_emails
  for update
  using (exists (select 1 from public.job_applications a where a.id = cold_emails.application_id and a.user_id = auth.uid()))
  with check (exists (select 1 from public.job_applications a where a.id = cold_emails.application_id and a.user_id = auth.uid()));

drop policy if exists "cold_emails_delete_own_application" on public.cold_emails;
create policy "cold_emails_delete_own_application" on public.cold_emails
  for delete using (
    exists (select 1 from public.job_applications a where a.id = cold_emails.application_id and a.user_id = auth.uid())
  );
