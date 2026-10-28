-- Isolated test-project only; fixtures and all messages roll back. No Gmail calls.
begin;
do $$
declare a uuid:=gen_random_uuid(); b uuid:=gen_random_uuid(); app uuid;
begin
  if exists(select 1 from public.agent_runs) then raise exception 'Use an empty test queue'; end if;
  insert into auth.users(id,email) values(a,a::text||'@example.invalid'),(b,b::text||'@example.invalid');
  insert into public.job_applications(user_id,company,role) values(a,'Smoke Co','Engineer') returning id into app;
  perform set_config('test.mail_owner',a::text,true); perform set_config('test.mail_stranger',b::text,true);
  perform set_config('test.mail_app',app::text,true);
end $$;
set local role service_role;
do $$
declare uid uuid:=current_setting('test.mail_owner')::uuid;
  m jsonb; approved jsonb; edited jsonb; run jsonb; reserved jsonb; repeated jsonb;
  id uuid; token uuid; run_id uuid;
begin
  perform public.mail_command(uid,'connect',jsonb_build_object('provider_account_id','ca_test_'||uid::text,'email','owner@example.invalid'));
  m=public.mail_command(uid,'create',jsonb_build_object('application_id',current_setting('test.mail_app'),'request_key','test-draft',
    'to_email','recruiter@example.invalid','subject','Original','body','Draft, not sent'));
  id=(m->>'id')::uuid; perform set_config('test.mail_message',id::text,true);
  assert m->>'state'='draft';
  begin
    perform public.mail_command(uid,'queue',jsonb_build_object('id',id,'revision',1));
    raise exception 'Unapproved send accepted';
  exception when raise_exception then if sqlerrm<>'mail_approval_required' then raise; end if; end;
  begin
    perform public.mail_command(current_setting('test.mail_stranger')::uuid,'approve',jsonb_build_object('id',id,'revision',1));
    raise exception 'Foreign approval accepted';
  exception when raise_exception then if sqlerrm<>'mail_not_found' then raise; end if; end;
  approved=public.mail_command(uid,'approve',jsonb_build_object('id',id,'revision',1));
  assert approved->>'state'='approved';
  edited=public.mail_command(uid,'edit',jsonb_build_object('id',id,'revision',1,'to_email','changed@example.invalid','subject','Changed','body','Must review again'));
  assert edited->>'state'='draft' and (edited->>'revision')::int=2 and edited->>'approved_revision' is null;
  begin
    perform public.mail_command(uid,'approve',jsonb_build_object('id',id,'revision',1));
    raise exception 'Stale revision approved';
  exception when raise_exception then if sqlerrm<>'mail_revision_conflict' then raise; end if; end;
  perform public.mail_command(uid,'approve',jsonb_build_object('id',id,'revision',2));
  m=public.mail_command(uid,'queue',jsonb_build_object('id',id,'revision',2));
  repeated=public.mail_command(uid,'queue',jsonb_build_object('id',id,'revision',2));
  assert m->>'run_id'=repeated->>'run_id' and (select count(*) from public.agent_runs)=1;
  run=public.claim_agent_run('mail-smoke',120); run_id=(run->>'id')::uuid; token=(run->>'lease_token')::uuid;
  assert m->>'from_email'='owner@example.invalid', 'Sender was not frozen at approval';
  update public.mail_connections set email='changed-sender@example.invalid' where user_id=uid;
  begin
    perform public.begin_mail_send(run_id,token,id);
    raise exception 'Changed sender bypassed approval';
  exception when raise_exception then if sqlerrm<>'mail_connection_required' then raise; end if; end;
  update public.mail_connections set email='owner@example.invalid' where user_id=uid;
  reserved=public.begin_mail_send(run_id,token,id);
  assert (reserved->>'dispatch')::boolean and reserved->'message'->>'state'='sending';
  repeated=public.begin_mail_send(run_id,token,id);
  assert not (repeated->>'dispatch')::boolean, 'Duplicate dispatch allowed';
  begin
    perform public.mail_command(uid,'cancel',jsonb_build_object('id',id,'revision',2));
    raise exception 'In-flight send cancelled as if safe';
  exception when raise_exception then if sqlerrm<>'mail_immutable' then raise; end if; end;
  perform public.mail_worker_result(run_id,token,id,'send_unknown','{"error":"Uncertain provider response"}');
  assert not (public.begin_mail_send(run_id,token,id)->>'dispatch')::boolean, 'Unknown send was replayed';
  begin
    perform public.mail_worker_result(run_id,gen_random_uuid(),id,'sent','{"provider_message_id":"fake"}');
    raise exception 'Stale worker committed';
  exception when raise_exception then if sqlerrm<>'lease_lost' then raise; end if; end;
  m=public.mail_worker_result(run_id,token,id,'sent','{"provider_message_id":"actualreceipt","provider_thread_id":"thread1"}');
  assert m->>'state'='sent' and m->>'sent_at' is not null and m->>'delivery_status'='unknown';
  perform public.mail_worker_result(run_id,token,id,'replies','{"replies":[{"provider_message_id":"reply1","from_email":"changed@example.invalid","excerpt":"Interview invite","received_at":"2026-10-28T00:00:00Z","classification":"interview"}]}');
  update public.mail_replies set classification='other',reviewed=true,classification_source='user' where message_id=(m->>'id')::uuid;
  perform public.mail_worker_result(run_id,token,id,'replies','{"replies":[{"provider_message_id":"reply1","from_email":"changed@example.invalid","excerpt":"Interview invite","received_at":"2026-10-28T00:00:00Z","classification":"interview"}]}');
  assert (select count(*) from public.mail_replies where message_id=(m->>'id')::uuid)=1;
  assert (select classification from public.mail_replies where message_id=(m->>'id')::uuid)='other', 'Human classification overwritten';
  perform public.finish_agent_run(run_id,token,'succeeded','{}');
  begin
    perform public.mail_command(uid,'edit',jsonb_build_object('id',id,'revision',2,'to_email','x@example.invalid','subject','x','body','x'));
    raise exception 'Sent record rewritten';
  exception when raise_exception then if sqlerrm<>'mail_immutable' then raise; end if; end;
  assert not has_function_privilege('authenticated','public.mail_command(uuid,text,jsonb)','execute');
  assert not has_table_privilege('authenticated','public.outreach_messages','update');
end $$;
set local role authenticated;
select set_config('request.jwt.claims',json_build_object('sub',current_setting('test.mail_owner'),'role','authenticated')::text,true);
do $$ begin
  assert (select count(*) from public.outreach_messages where id=current_setting('test.mail_message')::uuid)=1;
  assert (select count(*) from public.mail_replies where message_id=current_setting('test.mail_message')::uuid)=1;
end $$;
select set_config('request.jwt.claims',json_build_object('sub',current_setting('test.mail_stranger'),'role','authenticated')::text,true);
do $$ begin
  assert not exists(select 1 from public.outreach_messages where id=current_setting('test.mail_message')::uuid);
  assert not exists(select 1 from public.mail_replies where message_id=current_setting('test.mail_message')::uuid);
  assert not exists(select 1 from public.mail_connections where user_id=current_setting('test.mail_owner')::uuid);
end $$;
reset role;
rollback;
select 'gmail_outreach_smoke_passed' as result;
