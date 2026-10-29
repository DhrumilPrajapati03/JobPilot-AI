-- Development-only transactional checks. No provider calls or surviving fixtures.
begin;
do $$
declare a uuid:=gen_random_uuid(); b uuid:=gen_random_uuid(); app uuid; other_app uuid; sid uuid:=gen_random_uuid();
  message uuid; run uuid; worker uuid:=gen_random_uuid(); attempt uuid:=gen_random_uuid();
begin
  insert into auth.users(id,email) values(a,a::text||'@example.invalid'),(b,b::text||'@example.invalid');
  insert into public.job_applications(user_id,company,role) values(a,'Metric Fixture','Engineer') returning id into app;
  insert into public.job_applications(user_id,company,role) values(b,'Private Fixture','Engineer') returning id into other_app;
  perform set_config('test.metrics.a',a::text,true); perform set_config('test.metrics.b',b::text,true);
  perform public.create_application_session(a,sid,app,'https://jobs.lever.co/example/job/apply','url_match',null);
  perform public.append_application_event(a,sid,'form_prepared',gen_random_uuid(),'{"summary":{"total":3,"filled":2,"preserved":0,"review":1,"invalid":0}}');
  perform public.append_application_event(a,sid,'form_prepared',gen_random_uuid(),'{"summary":{"total":4,"filled":1,"preserved":1,"review":1,"invalid":1}}');
  perform public.append_application_event(a,sid,'submission_attempted',attempt,'{}');
  perform public.append_application_event(a,sid,'submission_confirmation_observed',gen_random_uuid(),jsonb_build_object('attempt_key',attempt));
  perform public.append_application_event(a,sid,'user_reported_submitted',gen_random_uuid(),'{}');
  insert into public.outreach_messages(user_id,application_id,request_key,to_email,subject,body,state,provider_message_id,sent_at,delivery_status)
    values(a,app,'accepted','fixture@example.invalid','Fixture','PRIVATE BODY','sent','provider-fixture',now(),'bounce_observed') returning id into message;
  insert into public.outreach_messages(user_id,application_id,request_key,to_email,subject,body,state)
    values(a,app,'unknown','fixture@example.invalid','Fixture','PRIVATE BODY','send_unknown'),(a,app,'draft','fixture@example.invalid','Fixture','PRIVATE BODY','draft');
  insert into public.outreach_messages(user_id,application_id,request_key,to_email,subject,body,state,provider_message_id,sent_at)
    values(b,other_app,'private','fixture@example.invalid','Fixture','PRIVATE BODY','sent','private-provider',now());
  insert into public.mail_replies(user_id,message_id,provider_message_id,from_email,excerpt,received_at,classification,reviewed)
    values(a,message,'reply-1','fixture@example.invalid','PRIVATE REPLY',now(),'positive',true),
          (a,message,'reply-2','fixture@example.invalid','PRIVATE REPLY',now(),'bounce',false);
  insert into public.agent_runs(user_id,kind,idempotency_key,status,attempts) values(a,'application','recovered-fixture','succeeded',2) returning id into run;
  insert into public.agent_run_events(run_id,user_id,event) values
    (run,a,'{"step":"resume_tailoring","data":{"duration_ms":200}}'),(run,a,'{"step":"resume_tailoring","data":{"duration_ms":400}}'),
    (run,a,'{"step":"resume_tailoring","status":"done","message":"Restored; no new timing"}');
  perform public.heartbeat_execution_worker(worker,null,null);
  assert (public.get_execution_health()->>'healthy_workers')::int=0, 'Non-polling process declared ready';
  perform public.heartbeat_execution_worker(worker,now(),null);
  assert (public.get_execution_health()->>'healthy_workers')::int=1;
  insert into public.agent_runs(user_id,kind,idempotency_key,status,worker_id,lease_expires_at)
    values(a,'scan','active-fixture','running',worker::text,now()+interval '30 seconds') returning id into run;
  perform public.heartbeat_execution_worker(worker,now()-interval '1 hour',run);
  assert (public.get_execution_health()->>'healthy_workers')::int=1, 'Busy lease-fenced worker declared unhealthy';
  update public.agent_runs set lease_expires_at=now()-interval '1 second' where id=run;
  assert (public.get_execution_health()->>'healthy_workers')::int=0;
  assert (public.get_execution_health()->>'expired_leases')::int=1;
end $$;
set local role authenticated;
select set_config('request.jwt.claim.sub',current_setting('test.metrics.a'),true);
do $$ declare m jsonb:=public.get_product_metrics(); begin
  assert (m->>'generated_applications')::int=1;
  assert (m->>'prepared_applications')::int=1 and (m->>'attempted_applications')::int=1;
  assert (m->>'browser_observed_applications')::int=1 and (m->>'user_reported_applications')::int=1;
  assert m->'independently_verified_submissions'='null'::jsonb and m->'cost_per_application'='null'::jsonb;
  assert (m->'preparation'->>'inspected_fields')::int=4, 'Repeated preparations double counted';
  assert (m->'gmail'->>'accepted_messages')::int=1 and (m->'gmail'->>'correlated_replied_messages')::int=1;
  assert (m->'gmail'->>'reviewed_human_replied_messages')::int=1 and (m->'gmail'->>'unknown_outcomes')::int=1;
  assert (m->'runs'->>'recovered')::int=1;
  assert (m->'stage_timings'->0->>'samples')::int=2 and (m->'stage_timings'->0->>'median_ms')::numeric=300;
  assert m::text not like '%PRIVATE%';
  assert not has_table_privilege('authenticated','public.execution_workers','SELECT');
  assert not has_function_privilege('authenticated','public.get_execution_health()','EXECUTE');
end $$;
select set_config('request.jwt.claim.sub',current_setting('test.metrics.b'),true);
do $$ declare m jsonb:=public.get_product_metrics(); begin
  assert (m->>'prepared_applications')::int=0 and (m->'gmail'->>'accepted_messages')::int=1;
  assert jsonb_array_length(m->'stage_timings')=0;
end $$;
set local role anon;
do $$ begin assert not has_function_privilege('anon','public.get_product_metrics()','EXECUTE'); end $$;
rollback;
