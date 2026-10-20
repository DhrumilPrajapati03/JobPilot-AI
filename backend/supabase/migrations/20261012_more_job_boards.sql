-- JobPilot AI: more job board types for discovery — SmartRecruiters company boards
-- and the Himalayas / Remotive remote job boards. Run after 20261011_job_discovery.sql.
-- Safe to re-run.

alter table public.job_sources drop constraint if exists job_sources_ats_check;
alter table public.job_sources
  add constraint job_sources_ats_check
  check (ats in ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'himalayas', 'remotive'));
