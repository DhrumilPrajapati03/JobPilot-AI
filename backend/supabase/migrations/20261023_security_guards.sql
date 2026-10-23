-- Restrictive guards remain AND-ed with any older permissive policies. Service
-- role access still bypasses RLS and must retain explicit server-side filtering.
do $$
declare t text;
begin
  foreach t in array array['resumes','job_applications','tailored_resumes','qa_answers',
                          'job_sources','job_postings','network_contacts','referral_requests',
                          'extension_tokens','autopilot_state'] loop
    execute format('drop policy if exists security_owner_guard on public.%I', t);
    execute format('create policy security_owner_guard on public.%I as restrictive using (user_id = auth.uid()) with check (user_id = auth.uid())', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated, service_role', t);
  end loop;
end $$;

drop policy if exists security_profile_guard on public.user_profiles;
create policy security_profile_guard on public.user_profiles as restrictive
  using (id = auth.uid()) with check (id = auth.uid());

drop policy if exists security_tailored_parent on public.tailored_resumes;
create policy security_tailored_parent on public.tailored_resumes as restrictive
  using (exists(select 1 from public.job_applications a where a.id = application_id and a.user_id = auth.uid()))
  with check (exists(select 1 from public.job_applications a where a.id = application_id and a.user_id = auth.uid()));

drop policy if exists security_email_parent on public.cold_emails;
create policy security_email_parent on public.cold_emails as restrictive
  using (exists(select 1 from public.job_applications a where a.id = application_id and a.user_id = auth.uid()))
  with check (exists(select 1 from public.job_applications a where a.id = application_id and a.user_id = auth.uid()));

drop policy if exists security_referral_parents on public.referral_requests;
create policy security_referral_parents on public.referral_requests as restrictive
  using (exists(select 1 from public.job_applications a where a.id = application_id and a.user_id = auth.uid())
    and exists(select 1 from public.network_contacts c where c.id = contact_id and c.user_id = auth.uid()))
  with check (exists(select 1 from public.job_applications a where a.id = application_id and a.user_id = auth.uid())
    and exists(select 1 from public.network_contacts c where c.id = contact_id and c.user_id = auth.uid()));

drop policy if exists security_posting_parents on public.job_postings;
create policy security_posting_parents on public.job_postings as restrictive
  using ((source_id is null or exists(select 1 from public.job_sources s where s.id = source_id and s.user_id = auth.uid()))
    and (application_id is null or exists(select 1 from public.job_applications a where a.id = application_id and a.user_id = auth.uid())))
  with check ((source_id is null or exists(select 1 from public.job_sources s where s.id = source_id and s.user_id = auth.uid()))
    and (application_id is null or exists(select 1 from public.job_applications a where a.id = application_id and a.user_id = auth.uid())));

-- Resume originals must never be served through public-bucket URLs.
update storage.buckets set public = false, file_size_limit = 10485760,
  allowed_mime_types = array['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document']
where id = 'resumes';
drop policy if exists security_resume_object_guard on storage.objects;
create policy security_resume_object_guard on storage.objects as restrictive
  using (bucket_id <> 'resumes' or (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id <> 'resumes' or (storage.foldername(name))[1] = auth.uid()::text);
