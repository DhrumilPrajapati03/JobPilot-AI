-- Agent runtime schema (migrations/0004). Everything rolls back.
begin;
do $$
declare uid uuid := gen_random_uuid(); c uuid; p uuid; r1 jsonb; r2 jsonb; r3 jsonb;
begin
  if exists(select 1 from public.agent_runs where status='running') then raise exception 'Use an idle test queue'; end if;
  insert into auth.users(id,email) values(uid,uid::text||'@example.invalid');
  -- Scout runs without a case are one at a time; an expert on a case waits for that case.
  r1=public.enqueue_agent_run(uid,'agent','{"agent":"scout","trigger":"routine"}','scout-1');
  r2=public.enqueue_agent_run(uid,'agent','{"agent":"scout","trigger":"manual"}','scout-2');
  assert r1->>'concurrency_key'=uid::text||':agent:scout';
  assert (public.claim_agent_run('w1',120))->>'id'=r1->>'id';
  assert public.claim_agent_run('w2',120) is null, 'two Scout runs at once';
  insert into public.job_case(user_id,company) values(uid,'Acme') returning id into c;
  r3=public.enqueue_agent_run(uid,'agent','{"agent":"researcher"}','research-1',now(),null,null,c);
  assert (public.claim_agent_run('w3',120))->>'id'=r3->>'id', 'researcher on a case runs beside Scout';
  -- One case per posting.
  insert into public.job_postings(user_id,ats,external_id,title,company) values(uid,'lever','x1','Engineer','Acme') returning id into p;
  insert into public.job_case(user_id,posting_id) values(uid,p);
  begin
    insert into public.job_case(user_id,posting_id) values(uid,p);
    raise exception 'second case for the same posting';
  exception when unique_violation then null;
  end;
  -- Specs: built-ins have no owner, user specs must have one.
  begin
    insert into public.agent_spec(id,owner,name,spec_sha256) values('mine','user','Mine',repeat('a',64));
    raise exception 'user spec without owner';
  exception when check_violation then null;
  end;
end $$;
rollback;
select 'agent_runtime_passed' as result;
