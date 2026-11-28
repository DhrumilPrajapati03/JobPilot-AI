-- Custom experts (plan section 3.2; Day 14): what they write is a note on the case.
alter table public.artifact drop constraint artifact_kind_check;
alter table public.artifact add constraint artifact_kind_check check (kind in ('resume_version','company_brief',
  'comp_report','contact_list','draft','answer_set','interview_prep','invite_set','dm_set','note'));
