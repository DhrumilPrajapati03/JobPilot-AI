-- Test-project only. No employer/provider calls; fixtures roll back.
begin;
do $$
declare a uuid:=gen_random_uuid(); b uuid:=gen_random_uuid(); app uuid;
begin
  insert into auth.users(id,email) values(a,a::text||'@example.invalid'),(b,b::text||'@example.invalid');
  insert into public.job_applications(user_id,company,role) values(a,'Execution Smoke','Engineer') returning id into app;
  perform set_config('test.execution.owner',a::text,true); perform set_config('test.execution.stranger',b::text,true);
  perform set_config('test.execution.app',app::text,true); perform set_config('test.execution.session',gen_random_uuid()::text,true);
end $$;
set local role service_role;
do $$
declare uid uuid:=current_setting('test.execution.owner')::uuid; app uuid:=current_setting('test.execution.app')::uuid;
  sid uuid:=current_setting('test.execution.session')::uuid; s jsonb; repeated jsonb; e jsonb;
  prepared uuid:=gen_random_uuid(); attempt uuid:=gen_random_uuid(); reported uuid:=gen_random_uuid(); confirmation uuid:=gen_random_uuid();
begin
  s=public.create_application_session(uid,sid,app,'https://job-boards.greenhouse.io/example/jobs/1','url_match',
    jsonb_build_object('resume_version',2,'name','Frozen.pdf','sha256',repeat('a',64),'size_bytes',5,'pdf_base64','JVBERi0='));
  repeated=public.create_application_session(uid,sid,app,'https://job-boards.greenhouse.io/example/jobs/1','url_match',null);
  assert s->>'document_id'=repeated->>'document_id';
  assert (select count(*) from public.application_documents where application_id=app)=1;
  begin
    perform public.append_application_event(uid,sid,'submission_attempted',attempt,'{}');
    raise exception 'Attempt without preparation accepted';
  exception when raise_exception then if sqlerrm<>'execution_preparation_required' then raise; end if; end;
  e=public.append_application_event(uid,sid,'form_prepared',prepared,'{"summary":{"total":1,"filled":1}}');
  repeated=public.append_application_event(uid,sid,'form_prepared',prepared,'{"summary":{"total":1,"filled":1}}');
  assert e->>'id'=repeated->>'id';
  assert (select status from public.job_applications where id=app)='saved';
  begin
    perform public.append_application_event(uid,sid,'form_prepared',prepared,'{"changed":true}');
    raise exception 'Changed replay accepted';
  exception when raise_exception then if sqlerrm<>'execution_conflict' then raise; end if; end;
  begin
    perform public.append_application_event(current_setting('test.execution.stranger')::uuid,sid,'submission_attempted',gen_random_uuid(),'{}');
    raise exception 'Foreign event accepted';
  exception when raise_exception then if sqlerrm<>'execution_not_found' then raise; end if; end;
  begin
    perform public.append_application_event(uid,sid,'submission_confirmation_observed',confirmation,jsonb_build_object('attempt_key',attempt));
    raise exception 'Confirmation without attempt accepted';
  exception when raise_exception then if sqlerrm<>'execution_attempt_required' then raise; end if; end;
  perform public.append_application_event(uid,sid,'submission_attempted',attempt,'{}');
  assert (select status from public.job_applications where id=app)='saved';
  perform public.append_application_event(uid,sid,'submission_confirmation_observed',confirmation,jsonb_build_object('attempt_key',attempt));
  assert (select status from public.job_applications where id=app)='saved', 'Browser observation changed business status';
  perform public.append_application_event(uid,sid,'user_reported_submitted',reported,'{}');
  assert exists(select 1 from public.job_applications where id=app and status='applied' and applied_at is not null and follow_up_at is not null);
  update public.job_applications set status='interviewing' where id=app;
  perform public.append_application_event(uid,sid,'user_reported_submitted',reported,'{}');
  assert (select status from public.job_applications where id=app)='interviewing', 'Retry overwrote later progress';
  update public.application_execution_sessions set expires_at=clock_timestamp()-interval '1 second' where id=sid;
  begin
    perform public.append_application_event(uid,sid,'form_prepared',gen_random_uuid(),'{}');
    raise exception 'Expired session accepted';
  exception when raise_exception then if sqlerrm<>'execution_expired' then raise; end if; end;
end $$;
set local role authenticated;
select set_config('request.jwt.claim.sub',current_setting('test.execution.owner'),true);
do $$
begin
  assert (select count(*) from public.application_events)=4;
  assert (select count(*) from public.application_execution_sessions)=1;
  assert (select count(id) from public.application_documents)=1;
  assert not has_column_privilege('authenticated','public.application_documents','pdf_base64','SELECT');
  assert not has_table_privilege('authenticated','public.application_events','INSERT');
  assert not has_function_privilege('authenticated','public.append_application_event(uuid,uuid,text,uuid,jsonb)','EXECUTE');
end $$;
select set_config('request.jwt.claim.sub',current_setting('test.execution.stranger'),true);
do $$ begin
  assert (select count(*) from public.application_events)=0;
  assert (select count(*) from public.application_execution_sessions)=0;
  assert (select count(id) from public.application_documents)=0;
end $$;
reset role;
delete from auth.users where id=current_setting('test.execution.owner')::uuid;
do $$ begin
  assert not exists(select 1 from public.application_events where user_id=current_setting('test.execution.owner')::uuid);
  assert not exists(select 1 from public.application_documents where user_id=current_setting('test.execution.owner')::uuid);
end $$;
rollback;
