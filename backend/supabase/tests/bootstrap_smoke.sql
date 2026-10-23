-- Run against a NEW disposable Supabase project AFTER all migrations.
-- Requires the SQL editor/admin connection. Everything below is rolled back.
begin;
-- Simulate an old permissive policy. The new restrictive guard must still win.
create policy smoke_legacy_allow_all on public.job_applications using (true) with check (true);
insert into auth.users(id, email) values
  ('11111111-1111-4111-8111-111111111111', 'alice-smoke@example.test'),
  ('22222222-2222-4222-8222-222222222222', 'bob-smoke@example.test');

set local role authenticated;
set local request.jwt.claims = '{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}';
insert into public.user_profiles(id, name) values (auth.uid(), 'Smoke Alice');
insert into public.resumes(user_id, version) values (auth.uid(), 'base');
insert into public.job_applications(id, user_id, company, role) values
  ('33333333-3333-4333-8333-333333333333', auth.uid(), 'Example', 'Engineer');
insert into public.tailored_resumes(application_id, user_id, content) values
  ('33333333-3333-4333-8333-333333333333', auth.uid(), '{}');
insert into public.cold_emails(application_id, user_id, body) values
  ('33333333-3333-4333-8333-333333333333', auth.uid(), 'Private draft');
insert into public.qa_answers(user_id, question, answer, sensitive) values
  (auth.uid(), 'Private question', 'Private answer', true);

set local request.jwt.claims = '{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}';
do $$
begin
  if exists(select 1 from public.user_profiles where name = 'Smoke Alice')
    or exists(select 1 from public.resumes where user_id = '11111111-1111-4111-8111-111111111111')
    or exists(select 1 from public.job_applications where id = '33333333-3333-4333-8333-333333333333')
    or exists(select 1 from public.tailored_resumes where application_id = '33333333-3333-4333-8333-333333333333')
    or exists(select 1 from public.cold_emails where application_id = '33333333-3333-4333-8333-333333333333')
    or exists(select 1 from public.qa_answers where question = 'Private question') then
    raise exception 'RLS leaked Alice data to Bob';
  end if;
  begin
    insert into public.tailored_resumes(application_id, user_id, version) values
      ('33333333-3333-4333-8333-333333333333', auth.uid(), 2);
    raise exception 'Bob wrote a tailored resume to Alice application';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.cold_emails(application_id, user_id) values
      ('33333333-3333-4333-8333-333333333333', auth.uid());
    raise exception 'Bob wrote an email to Alice application';
  exception when insufficient_privilege then null;
  end;
end $$;
rollback;
