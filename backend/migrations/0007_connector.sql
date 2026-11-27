-- Connector and the LinkedIn queue (plan sections 2.1, 2.4; Day 8).

-- Connector's invite notes for one case, as an artifact (the actions hold the frozen payloads).
alter table public.artifact drop constraint artifact_kind_check;
alter table public.artifact add constraint artifact_kind_check check (kind in ('resume_version','company_brief',
  'comp_report','contact_list','draft','answer_set','interview_prep','invite_set'));

-- The queue reads approved LinkedIn actions oldest first.
create index action_linkedin_queue_idx on public.action (user_id, created_at)
  where kind in ('send_linkedin_invite', 'send_linkedin_dm') and status in ('approved', 'executing');
