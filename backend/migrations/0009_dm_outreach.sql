-- DM Outreach (plan sections 2.1, 2.4; Day 11): its messages and referral asks for one case.
alter table public.artifact drop constraint artifact_kind_check;
alter table public.artifact add constraint artifact_kind_check check (kind in ('resume_version','company_brief',
  'comp_report','contact_list','draft','answer_set','interview_prep','invite_set','dm_set'));
