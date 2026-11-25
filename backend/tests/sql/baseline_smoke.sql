-- Baseline shape after `alembic upgrade head`. Read-only apart from rolled-back fixtures.
begin;
do $$ begin
  assert exists(select 1 from pg_extension where extname='vector'), 'pgvector missing';
  assert exists(select 1 from pg_extension where extname='pgcrypto'), 'pgcrypto missing';
  assert public.release_schema_ready(), 'release_schema_ready() is false';
  -- 31 tables from revision 0001, plus resume_sections (0002).
  assert (select count(*) from pg_tables where schemaname='public' and tablename<>'alembic_version')=32, 'unexpected table count';
  assert (select format_type(atttypid, atttypmod) from pg_attribute where attrelid='public.resume_sections'::regclass and attname='embedding')='vector';
  assert not exists(select 1 from pg_tables where schemaname='public' and rowsecurity), 'RLS still enabled';
  assert not exists(select 1 from pg_policies), 'policies still present';
  assert not exists(select 1 from pg_roles where rolname in ('anon','authenticated','service_role')), 'Supabase roles present';
  assert to_regproc('public.jobpilot_session_active') is null, 'session guard still present';
  assert auth.uid() is null;
end $$;
select set_config('app.user_id','11111111-1111-4111-8111-111111111111',true);
do $$ begin
  assert auth.uid()='11111111-1111-4111-8111-111111111111'::uuid, 'auth.uid() does not read app.user_id';
  perform '[1,2,3]'::vector(3);
end $$;
rollback;
select 'baseline_smoke_passed' as result;
