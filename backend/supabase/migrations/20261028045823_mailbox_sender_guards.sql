-- Approval includes the exact sending address, not only its connection ID.
alter table public.outreach_messages add column from_email text;
create or replace function public.mail_command(p_user_id uuid,p_action text,p_data jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare m public.outreach_messages; c public.mail_connections; job jsonb; other public.outreach_messages;
begin
  if p_action='connect' then
    insert into public.agent_run_locks(user_id) values(p_user_id) on conflict do nothing;
    perform 1 from public.agent_run_locks where user_id=p_user_id for update;
    if exists(select 1 from public.mail_connections where provider_account_id=p_data->>'provider_account_id' and user_id<>p_user_id) then raise exception 'mail_account_not_owned'; end if;
    if exists(select 1 from public.mail_connections where user_id=p_user_id and status='active' and provider_account_id<>p_data->>'provider_account_id') then raise exception 'disconnect_existing_mailbox_first'; end if;
    insert into public.mail_connections(user_id,provider_account_id,email) values(p_user_id,p_data->>'provider_account_id',p_data->>'email')
      on conflict(provider_account_id) do update set status='active',email=excluded.email returning * into c;
    return to_jsonb(c);
  elsif p_action='disconnect' then
    update public.mail_connections set status='disconnected' where id=(p_data->>'id')::uuid and user_id=p_user_id returning * into c;
    if not found then raise exception 'mail_not_found'; end if;
    update public.outreach_messages set state='draft',revision=revision+1,approved_revision=null,approved_at=null,from_email=null,connection_id=null,run_id=null,updated_at=clock_timestamp()
      where connection_id=c.id and user_id=p_user_id and state in ('approved','queued');
    return to_jsonb(c);
  elsif p_action='create' then
    if not exists(select 1 from public.job_applications where id=(p_data->>'application_id')::uuid and user_id=p_user_id) then raise exception 'mail_not_found'; end if;
    if p_data->>'cold_email_id' is not null and not exists(select 1 from public.cold_emails where id=(p_data->>'cold_email_id')::uuid and user_id=p_user_id and application_id=(p_data->>'application_id')::uuid) then raise exception 'mail_not_found'; end if;
    insert into public.outreach_messages(user_id,application_id,cold_email_id,request_key,to_email,subject,body,attachment)
      values(p_user_id,(p_data->>'application_id')::uuid,(p_data->>'cold_email_id')::uuid,p_data->>'request_key',p_data->>'to_email',p_data->>'subject',p_data->>'body',nullif(p_data->'attachment','null'))
      on conflict(user_id,request_key) do nothing returning * into m;
    if m.id is null then
      select * into m from public.outreach_messages where user_id=p_user_id and request_key=p_data->>'request_key';
      if m.application_id::text<>p_data->>'application_id' or m.to_email<>p_data->>'to_email' or m.subject<>p_data->>'subject' or m.body<>p_data->>'body' then raise exception 'mail_revision_conflict'; end if;
    end if;
    return to_jsonb(m);
  end if;
  select * into m from public.outreach_messages where id=(p_data->>'id')::uuid and user_id=p_user_id for update;
  if not found then raise exception 'mail_not_found'; end if;
  if p_action='queue' and m.state in ('queued','sending','sent','send_unknown') then return to_jsonb(m); end if;
  if m.revision is distinct from (p_data->>'revision')::integer then raise exception 'mail_revision_conflict'; end if;
  if p_action='cancel' then
    if m.state not in ('queued','approved','draft','failed') then raise exception 'mail_immutable'; end if;
    update public.outreach_messages set state='draft',revision=revision+1,approved_revision=null,approved_at=null,from_email=null,connection_id=null,run_id=null,updated_at=clock_timestamp() where id=m.id returning * into m;
    return to_jsonb(m);
  end if;
  if p_action='edit' then
    if m.state not in ('draft','approved','failed') then raise exception 'mail_immutable'; end if;
    update public.outreach_messages set to_email=p_data->>'to_email',subject=p_data->>'subject',body=p_data->>'body',attachment=nullif(p_data->'attachment','null'),
      revision=revision+1,state='draft',approved_revision=null,approved_at=null,from_email=null,connection_id=null,run_id=null,last_error=null,updated_at=clock_timestamp()
      where id=m.id returning * into m;
  elsif p_action='approve' then
    if m.state not in ('draft','approved') then raise exception 'mail_immutable'; end if;
    select * into c from public.mail_connections where user_id=p_user_id and status='active' for update;
    if not found then raise exception 'mail_connection_required'; end if;
    if m.to_email='' or m.subject='' or m.body='' then raise exception 'mail_incomplete'; end if;
    update public.outreach_messages set state='approved',approved_revision=revision,approved_at=clock_timestamp(),from_email=c.email,connection_id=c.id,updated_at=clock_timestamp()
      where id=m.id returning * into m;
  elsif p_action='queue' then
    if m.state<>'approved' or m.approved_revision is distinct from m.revision then raise exception 'mail_approval_required'; end if;
    if not exists(select 1 from public.mail_connections where id=m.connection_id and user_id=p_user_id and status='active') then raise exception 'mail_connection_required'; end if;
    job=public.enqueue_agent_run(p_user_id,'mail_send',jsonb_build_object('message_id',m.id),'outreach-send:'||m.id::text||':'||m.revision::text);
    update public.outreach_messages set state='queued',run_id=(job->>'id')::uuid,updated_at=clock_timestamp() where id=m.id returning * into m;
  else raise exception 'invalid_mail_action'; end if;
  return to_jsonb(m);
end $$;

create or replace function public.begin_mail_send(p_run_id uuid,p_token uuid,p_message_id uuid)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare r public.agent_runs; m public.outreach_messages; c public.mail_connections;
begin
  select * into r from public.agent_runs where id=p_run_id and lease_token=p_token and status='running' and lease_expires_at>clock_timestamp() and kind='mail_send' for update;
  if not found then raise exception 'lease_lost'; end if;
  select * into m from public.outreach_messages where id=p_message_id and user_id=r.user_id for update;
  if not found or m.run_id is distinct from r.id then raise exception 'mail_not_found'; end if;
  select * into c from public.mail_connections where id=m.connection_id and user_id=r.user_id and status='active';
  if not found then raise exception 'mail_connection_required'; end if;
  if m.state<>'queued' then return jsonb_build_object('dispatch',false,'message',to_jsonb(m),'connection',to_jsonb(c)); end if;
  if m.approved_revision is distinct from m.revision then raise exception 'mail_approval_required'; end if;
  if m.from_email is distinct from c.email then raise exception 'mail_connection_required'; end if;
  update public.outreach_messages set state='sending',attempt_id=gen_random_uuid(),attempt_started_at=clock_timestamp(),
    rfc_message_id='<jobpilot.'||id::text||'@'||split_part(c.email,'@',2)||'>',updated_at=clock_timestamp() where id=m.id returning * into m;
  return jsonb_build_object('dispatch',true,'message',to_jsonb(m),'connection',to_jsonb(c));
end $$;


revoke all on function public.mail_command(uuid,text,jsonb),public.begin_mail_send(uuid,uuid,uuid) from public,anon,authenticated;
grant execute on function public.mail_command(uuid,text,jsonb),public.begin_mail_send(uuid,uuid,uuid) to service_role;
