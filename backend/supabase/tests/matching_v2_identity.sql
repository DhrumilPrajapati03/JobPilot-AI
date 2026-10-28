-- Isolated development database only. All rows/users roll back.
begin;
do $$
declare a uuid := gen_random_uuid(); b uuid := gen_random_uuid();
begin
  insert into auth.users(id,email) values(a,a::text||'@example.invalid'),(b,b::text||'@example.invalid');
  perform set_config('test.identity_owner',a::text,true);
  perform set_config('test.identity_stranger',b::text,true);
end $$;
set local role authenticated;
select set_config('request.jwt.claims',json_build_object('sub',current_setting('test.identity_owner'),'role','authenticated')::text,true);
do $$
declare uid uuid := current_setting('test.identity_owner')::uuid;
begin
  insert into public.identity_confirmations(user_id,source_digest,fact_id) values(uid,repeat('a',64),repeat('b',64));
  insert into public.identity_confirmations(user_id,source_digest,fact_id) values(uid,repeat('a',64),repeat('b',64)) on conflict(user_id,source_digest,fact_id) do nothing;
  assert (select count(*) from public.identity_confirmations where user_id=uid)=1;
  begin
    insert into public.identity_confirmations(user_id,source_digest,fact_id) values(current_setting('test.identity_stranger')::uuid,repeat('a',64),repeat('b',64));
    raise exception 'foreign confirmation accepted';
  exception when insufficient_privilege then null;
  end;
  assert not has_table_privilege('authenticated','public.identity_confirmations','update');
  assert not has_table_privilege('anon','public.identity_confirmations','select');
end $$;
select set_config('request.jwt.claims',json_build_object('sub',current_setting('test.identity_stranger'),'role','authenticated')::text,true);
do $$
begin
  assert (select count(*) from public.identity_confirmations)=0, 'foreign facts visible';
  delete from public.identity_confirmations where user_id=current_setting('test.identity_owner')::uuid;
  insert into public.identity_confirmations(user_id,source_digest,fact_id) values(current_setting('test.identity_stranger')::uuid,repeat('a',64),repeat('b',64));
  assert (select count(*) from public.identity_confirmations)=1;
end $$;
reset role;
set local role service_role;
do $$
declare a uuid := current_setting('test.identity_owner')::uuid; b uuid := current_setting('test.identity_stranger')::uuid;
begin
  assert (select count(*) from public.identity_confirmations where user_id=a)=1, 'foreign revoke succeeded';
  insert into public.job_postings(user_id,ats,external_id,title,location,dedupe_key,matching_details)
    values(a,'lever','test-1','ML Engineer','India','requisition-1','{"version":"matching-v2","eligibility":{"status":"eligible"}}');
  begin
    insert into public.job_postings(user_id,ats,external_id,dedupe_key) values(a,'greenhouse','alias-1','requisition-1');
    raise exception 'duplicate opening accepted';
  exception when unique_violation then null;
  end;
  insert into public.job_postings(user_id,ats,external_id,title,location,dedupe_key)
    values(a,'lever','test-2','ML Engineer','India','requisition-2');
  insert into public.job_postings(user_id,ats,external_id,dedupe_key) values(b,'greenhouse','alias-1','requisition-1');
  assert (select count(*) from public.job_postings where user_id=a)=2, 'distinct requisition merged';
  assert (select matching_details->'eligibility'->>'status' from public.job_postings where user_id=a and external_id='test-1')='eligible';
end $$;
reset role;
rollback;
select 'matching_v2_identity_smoke_passed' as result;
