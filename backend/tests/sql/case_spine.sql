-- Case spine guards and per-case queue concurrency (migrations/0003). Everything rolls back.
begin;
do $$
declare uid uuid := gen_random_uuid(); case_a uuid; case_b uuid; act uuid; h text := repeat('a',64);
  r1 jsonb; r2 jsonb; r3 jsonb; r4 jsonb;
begin
  if exists(select 1 from public.agent_runs where status='running') then raise exception 'Use an idle test queue'; end if;
  insert into auth.users(id,email) values(uid,uid::text||'@example.invalid');
  insert into public.job_case(user_id,company,role) values(uid,'A Co','Engineer') returning id into case_a;
  insert into public.job_case(user_id,company,role) values(uid,'B Co','Engineer') returning id into case_b;

  -- Actions must start proposed (or blocked) and follow the state machine.
  begin
    insert into public.action(user_id,kind,mode,payload,payload_sha256,status,idempotency_key)
      values(uid,'send_email','ask_first','{}',h,'approved','k0');
    raise exception 'action inserted as approved';
  exception when raise_exception then
    if sqlerrm<>'action_must_start_proposed' then raise; end if;
  end;
  insert into public.action(user_id,case_id,kind,mode,payload,payload_sha256,idempotency_key)
    values(uid,case_a,'send_email','ask_first','{"to":"x@example.invalid"}',h,'k1') returning id into act;
  begin
    update public.action set status='executing' where id=act;
    raise exception 'proposed jumped to executing';
  exception when raise_exception then
    if sqlerrm not like 'invalid_action_transition%' then raise; end if;
  end;
  update public.action set status='reviewed' where id=act;
  begin
    update public.action set status='approved' where id=act;
    raise exception 'approved without an approval row';
  exception when raise_exception then
    if sqlerrm<>'approval_required' then raise; end if;
  end;
  insert into public.approval(action_id,user_id,decision,payload_sha256,channel) values(act,uid,'approved',h,'web');
  update public.action set status='approved' where id=act;
  begin
    update public.action set payload='{"to":"other@example.invalid"}' where id=act;
    raise exception 'approved payload changed without going back to proposed';
  exception when raise_exception then
    if sqlerrm<>'action_payload_frozen' then raise; end if;
  end;
  update public.action set status='executing' where id=act;
  assert (select executing_at is not null from public.action where id=act), 'executing_at not stamped';
  begin
    update public.action set payload='{}', payload_sha256=repeat('b',64), status='proposed' where id=act;
    raise exception 'executing payload edited';
  exception when raise_exception then
    if sqlerrm<>'action_payload_frozen' and sqlerrm not like 'invalid_action_transition%' then raise; end if;
  end;
  update public.action set status='send_unknown' where id=act;
  update public.action set status='delivered' where id=act;

  -- hand_off actions can never execute, even with an approval.
  insert into public.action(user_id,kind,mode,payload,payload_sha256,idempotency_key)
    values(uid,'captcha_or_2fa','hand_off','{}',h,'k2') returning id into act;
  update public.action set status='reviewed' where id=act;
  insert into public.approval(action_id,user_id,decision,payload_sha256,channel) values(act,uid,'approved',h,'web');
  update public.action set status='approved' where id=act;
  begin
    update public.action set status='executing' where id=act;
    raise exception 'hand_off executed';
  exception when raise_exception then
    if sqlerrm<>'action_not_executable' then raise; end if;
  end;

  -- Per-case concurrency: runs on the same case wait; different cases run side by side.
  r1=public.enqueue_agent_run(uid,'company_research','{"application_id":"00000000-0000-4000-8000-000000000001"}','c1',now(),null,null,case_a);
  r2=public.enqueue_agent_run(uid,'company_research','{"application_id":"00000000-0000-4000-8000-000000000002"}','c2',now(),null,null,case_a);
  r3=public.enqueue_agent_run(uid,'company_research','{"application_id":"00000000-0000-4000-8000-000000000003"}','c3',now(),null,null,case_b);
  assert r1->>'concurrency_key'=uid::text||':case:'||case_a::text, 'case key not derived';
  begin
    perform public.enqueue_agent_run(uid,'company_research','{"application_id":"00000000-0000-4000-8000-000000000001"}','c1',now(),null,null,case_b);
    raise exception 'same key moved to another case';
  exception when raise_exception then
    if sqlerrm<>'idempotency_key_conflict' then raise; end if;
  end;
  r4=public.claim_agent_run('w1',120);
  assert r4->>'id'=r1->>'id';
  r4=public.claim_agent_run('w2',120);
  assert r4->>'id'=r3->>'id', 'a different case should run beside the first';
  assert public.claim_agent_run('w3',120) is null, 'same case ran twice at once';
  -- The kind cap (company_research = 2) also applies across cases.
  perform public.finish_agent_run((r1->>'id')::uuid,(select lease_token from public.agent_runs where id=(r1->>'id')::uuid),'succeeded');
  r4=public.claim_agent_run('w3',120);
  assert r4->>'id'=r2->>'id', 'next run on the case starts once the first finishes';
  update public.run_kind_limits set max_running=1 where kind='scan';
  perform public.enqueue_agent_run(uid,'scan','{}','scan-1');
  r4=public.claim_agent_run('w4',120);
  assert r4->>'kind'='scan', 'scan has its own key and runs beside research';
  begin
    perform public.enqueue_agent_run(uid,'scan','{}','scan-2',now(),null,null,gen_random_uuid());
    raise exception 'unknown case accepted';
  exception when raise_exception then
    if sqlerrm<>'case_not_found' then raise; end if;
  end;
end $$;
rollback;
select 'case_spine_passed' as result;
