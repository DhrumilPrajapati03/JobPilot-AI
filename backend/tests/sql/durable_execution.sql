-- Run only on an isolated test database after all migrations. All fixture data
-- rolls back, including auth users. Sequence gaps are expected after rollback.
begin;
do $$
declare owner_id uuid := gen_random_uuid(); stranger uuid := gen_random_uuid();
begin
  if exists(select 1 from public.agent_runs) then raise exception 'Use an empty test queue'; end if;
  insert into auth.users(id,email) values(owner_id,owner_id::text||'@example.invalid'),(stranger,stranger::text||'@example.invalid');
  perform set_config('test.owner',owner_id::text,true);
  perform set_config('test.stranger',stranger::text,true);
end $$;

do $$
declare uid uuid := current_setting('test.owner')::uuid;
  other_uid uuid := current_setting('test.stranger')::uuid;
  a jsonb; b jsonb; claimed jsonb; resumed jsonb; saved jsonb; second jsonb;
  old_token uuid; run_id uuid; before_count integer; posting_id uuid; contact_uuid uuid;
begin
  insert into public.job_postings(user_id,ats,external_id,title,company,location)
    values(uid,'lever','smoke-posting','Engineer','Smoke Inc','India') returning id into posting_id;
  a=public.enqueue_agent_run(uid,'application',jsonb_build_object('jd_text','Test JD','posting_id',posting_id,'auto',true),'smoke-application');
  b=public.enqueue_agent_run(uid,'application',jsonb_build_object('jd_text','Test JD','posting_id',posting_id,'auto',false),'smoke-application');
  assert a->>'id'=b->>'id', 'request deduplication failed';
  assert (select status from public.job_postings where id=posting_id)='drafting';
  run_id=(a->>'id')::uuid;
  perform set_config('test.run',run_id::text,true);
  begin
    perform public.enqueue_agent_run(uid,'application','{"jd_text":"Different JD"}','smoke-application');
    raise exception 'different inputs accepted';
  exception when raise_exception then
    if sqlerrm<>'idempotency_key_conflict' then raise; end if;
  end;
  claimed=public.claim_agent_run('first-worker',120);
  assert claimed->>'id'=run_id::text;
  old_token=(claimed->>'lease_token')::uuid;
  perform public.enqueue_agent_run(uid,'scan','{}','scan-after-application');
  -- Per-case concurrency: the scan has its own key, so it runs beside the application.
  second=public.claim_agent_run('concurrent-worker',120);
  assert second->>'kind'='scan', 'scan should run beside a running application';
  assert public.claim_agent_run('third-worker',120) is null, 'nothing else is runnable';
  -- Park the scan so the recovery checks below see only the application run.
  update public.agent_runs set status='queued',attempts=0,worker_id=null,lease_token=null,lease_expires_at=null,
    available_at=clock_timestamp()+interval '1 hour' where id=(second->>'id')::uuid;
  perform public.checkpoint_agent_run(run_id,old_token,'jd_parsing','{"role":"Engineer"}');
  assert public.renew_agent_run(run_id,old_token,120);
  update public.agent_runs set lease_expires_at=clock_timestamp()-interval '1 second' where id=run_id;
  resumed=public.claim_agent_run('replacement-worker',120);
  assert resumed->>'id'=run_id::text;
  assert resumed->>'lease_token'<>old_token::text;
  assert resumed->'checkpoints'->'jd_parsing'->>'role'='Engineer';
  assert not public.renew_agent_run(run_id,old_token,120), 'stale heartbeat accepted';
  begin
    perform public.checkpoint_agent_run(run_id,old_token,'illegal','{}');
    raise exception 'stale checkpoint accepted';
  exception when raise_exception then
    if sqlerrm<>'lease_lost' then raise; end if;
  end;
  begin
    perform public.enqueue_agent_run(other_uid,'scan','{}','cross-account-child',now(),run_id,(resumed->>'lease_token')::uuid);
    raise exception 'cross-account child accepted';
  exception when raise_exception then
    if sqlerrm<>'lease_lost' then raise; end if;
  end;
  select count(*) into before_count from public.job_applications where user_id=uid;
  begin
    perform public.save_run_application(run_id,(resumed->>'lease_token')::uuid,
      '{"company":"Smoke Inc","role":"Engineer","jd_analysis":{}}',
      '{"content":{},"keyword_match_score":75,"missing_keywords":[]}',
      '[{"subject":"Test","body":"Draft only","sequence_number":"bad-number"}]');
    raise exception 'invalid material accepted';
  exception when invalid_text_representation then null;
  end;
  assert (select count(*) from public.job_applications where user_id=uid)=before_count, 'partial application committed';
  saved=public.save_run_application(run_id,(resumed->>'lease_token')::uuid,
    '{"company":"Smoke Inc","role":"Engineer","jd_analysis":{}}',
    '{"content":{},"keyword_match_score":75,"missing_keywords":[]}',
    '[{"subject":"Test","body":"Draft only","sequence_number":1}]');
  second=public.save_run_application(run_id,(resumed->>'lease_token')::uuid,'{}','{}','[]');
  assert saved=second, 'duplicate application on replay';
  assert (select count(*) from public.job_applications where user_id=uid)=before_count+1;
  assert (select count(*) from public.tailored_resumes where application_id=(saved->>'application_id')::uuid)=1;
  assert (select count(*) from public.cold_emails where application_id=(saved->>'application_id')::uuid)=1;
  assert (select application_id from public.job_postings where id=posting_id)=(saved->>'application_id')::uuid;
  insert into public.network_contacts(user_id,full_name,dedupe_key) values(uid,'Smoke Contact','smoke-contact') returning id into contact_uuid;
  perform public.save_run_referral(run_id,(resumed->>'lease_token')::uuid,contact_uuid,'Generated draft');
  update public.referral_requests set message='User edited',status='sent' where contact_id=contact_uuid and user_id=uid;
  perform public.save_run_referral(run_id,(resumed->>'lease_token')::uuid,contact_uuid,'Must not overwrite');
  assert (select count(*) from public.referral_requests where user_id=uid)=1;
  assert (select message from public.referral_requests where user_id=uid)='User edited';
  perform public.save_run_prepared(run_id,(resumed->>'lease_token')::uuid,(saved->>'application_id')::uuid,'{"fields":[]}');
  perform public.finish_agent_run(run_id,(resumed->>'lease_token')::uuid,'succeeded',saved);
  update public.agent_runs set available_at=clock_timestamp() where kind='scan' and user_id=uid;
  claimed=public.claim_agent_run('worker',120);
  assert claimed->>'kind'='scan';
  perform public.finish_agent_run((claimed->>'id')::uuid,(claimed->>'lease_token')::uuid,'retry_wait','{}','temporary',0);
  resumed=public.claim_agent_run('worker',120);
  assert (resumed->>'attempts')::int=2;
  perform public.finish_agent_run((resumed->>'id')::uuid,(resumed->>'lease_token')::uuid,'failed','{}','test failure');
  begin
    perform public.retry_agent_run((resumed->>'id')::uuid,other_uid);
    raise exception 'foreign retry accepted';
  exception when raise_exception then
    if sqlerrm<>'run_not_found' then raise; end if;
  end;
  perform public.retry_agent_run((resumed->>'id')::uuid,uid);
  claimed=public.claim_agent_run('worker',120);
  assert (claimed->>'attempts')::int=1;
  update public.agent_runs set attempts=max_attempts,lease_expires_at=clock_timestamp()-interval '1 second' where id=(claimed->>'id')::uuid;
  assert public.claim_agent_run('worker',120) is null;
  assert (select status from public.agent_runs where id=(claimed->>'id')::uuid)='failed';
  perform public.enqueue_agent_run(other_uid,'digest','{}','other-account');
  assert (select count(*) from public.agent_runs where user_id=uid)=2;
  assert (select count(*) from public.agent_runs where user_id=other_uid)=1;
  assert not exists(select 1 from public.agent_run_events where agent_run_events.run_id=current_setting('test.run')::uuid and user_id<>uid), 'run events tagged with another owner';
end $$;
rollback;
select 'durable_execution_smoke_passed' as result;
