-- Trigger execution continues under its owner. Public clients must not call
-- the privileged event-trigger helper; bodies and trigger bindings stay intact.
do $$
begin
  if to_regprocedure('public.rls_auto_enable()') is not null then
    execute 'revoke all on function public.rls_auto_enable() from public, anon, authenticated';
  end if;
  if to_regprocedure('public.update_updated_at_column()') is not null then
    execute 'alter function public.update_updated_at_column() set search_path=pg_catalog';
  end if;
  if to_regprocedure('public.set_updated_at()') is not null then
    execute 'alter function public.set_updated_at() set search_path=pg_catalog';
  end if;
end $$;
-- Complement Sprint 1's restrictive guard with narrowly scoped permissions.
drop policy if exists resume_owner_access on storage.objects;
create policy resume_owner_access on storage.objects for all to authenticated
  using (bucket_id='resumes' and (storage.foldername(name))[1]=(select auth.uid())::text)
  with check (bucket_id='resumes' and (storage.foldername(name))[1]=(select auth.uid())::text);
