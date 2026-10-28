alter table public.agent_runs drop constraint agent_runs_kind_check;
alter table public.agent_runs add constraint agent_runs_kind_check check(kind in ('application','scan','digest','mail_send','mail_sync'));

create table public.mail_connections (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  provider_account_id text not null unique, email text not null,
  status text not null default 'active' check(status in ('active','disconnected')),
  created_at timestamptz not null default now(), last_sync_at timestamptz, unique(id,user_id)
);
create unique index mail_one_active_owner_idx on public.mail_connections(user_id) where status='active';
create table public.outreach_messages (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  application_id uuid not null references public.job_applications(id) on delete no action deferrable initially deferred,
  cold_email_id uuid references public.cold_emails(id) on delete set null,
  request_key text not null, to_email text not null, subject text not null, body text not null, attachment jsonb,
  revision integer not null default 1, approved_revision integer, approved_at timestamptz,
  connection_id uuid, state text not null default 'draft' check(state in ('draft','approved','queued','sending','sent','send_unknown','failed')),
  run_id uuid references public.agent_runs(id), attempt_id uuid, attempt_started_at timestamptz,
  rfc_message_id text, provider_message_id text, provider_thread_id text,
  sent_at timestamptz, delivery_status text not null default 'unknown' check(delivery_status in ('unknown','bounce_observed')),
  last_error text, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(user_id,request_key), unique(id,user_id),
  foreign key(connection_id,user_id) references public.mail_connections(id,user_id)
);
create index outreach_owner_app_idx on public.outreach_messages(user_id,application_id,created_at desc);
create index outreach_app_fk_idx on public.outreach_messages(application_id);
create index outreach_cold_fk_idx on public.outreach_messages(cold_email_id);
create index outreach_connection_fk_idx on public.outreach_messages(connection_id,user_id);
create index outreach_run_fk_idx on public.outreach_messages(run_id);
create table public.mail_replies (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  message_id uuid not null, provider_message_id text not null, from_email text not null, excerpt text not null,
  received_at timestamptz not null, classification text not null,
  classification_source text not null default 'rule_suggestion', reviewed boolean not null default false,
  unique(message_id,provider_message_id), foreign key(message_id,user_id) references public.outreach_messages(id,user_id) on delete cascade
);
create index mail_replies_owner_parent_idx on public.mail_replies(user_id,message_id);
create index mail_replies_parent_fk_idx on public.mail_replies(message_id,user_id);
create table public.recruiter_leads (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  application_id uuid not null references public.job_applications(id) on delete cascade,
  email text not null, full_name text not null, position text not null, domain text not null,
  sources jsonb not null default '[]', verification text not null, verified_at timestamptz not null default now(),
  unique(user_id,application_id,email)
);
create index recruiter_application_fk_idx on public.recruiter_leads(application_id);
do $$
declare t text;
begin
  foreach t in array array['mail_connections','outreach_messages','mail_replies','recruiter_leads'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all on public.%I from anon,authenticated',t);
    execute format('grant select on public.%I to authenticated',t);
    execute format('grant all on public.%I to service_role',t);
    execute format('create policy owner_read on public.%I for select to authenticated using(user_id=(select auth.uid()))',t);
  end loop;
end $$;

create function public.mail_command(p_user_id uuid,p_action text,p_data jsonb)
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
    update public.outreach_messages set state='draft',revision=revision+1,approved_revision=null,approved_at=null,connection_id=null,run_id=null,updated_at=clock_timestamp()
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
    update public.outreach_messages set state='draft',revision=revision+1,approved_revision=null,approved_at=null,connection_id=null,run_id=null,updated_at=clock_timestamp() where id=m.id returning * into m;
    return to_jsonb(m);
  end if;
  if p_action='edit' then
    if m.state not in ('draft','approved','failed') then raise exception 'mail_immutable'; end if;
    update public.outreach_messages set to_email=p_data->>'to_email',subject=p_data->>'subject',body=p_data->>'body',attachment=nullif(p_data->'attachment','null'),
      revision=revision+1,state='draft',approved_revision=null,approved_at=null,connection_id=null,run_id=null,last_error=null,updated_at=clock_timestamp()
      where id=m.id returning * into m;
  elsif p_action='approve' then
    if m.state not in ('draft','approved') then raise exception 'mail_immutable'; end if;
    select * into c from public.mail_connections where user_id=p_user_id and status='active' for update;
    if not found then raise exception 'mail_connection_required'; end if;
    if m.to_email='' or m.subject='' or m.body='' then raise exception 'mail_incomplete'; end if;
    update public.outreach_messages set state='approved',approved_revision=revision,approved_at=clock_timestamp(),connection_id=c.id,updated_at=clock_timestamp()
      where id=m.id returning * into m;
  elsif p_action='queue' then
    if m.state<>'approved' or m.approved_revision is distinct from m.revision then raise exception 'mail_approval_required'; end if;
    if not exists(select 1 from public.mail_connections where id=m.connection_id and user_id=p_user_id and status='active') then raise exception 'mail_connection_required'; end if;
    job=public.enqueue_agent_run(p_user_id,'mail_send',jsonb_build_object('message_id',m.id),'outreach-send:'||m.id::text||':'||m.revision::text);
    update public.outreach_messages set state='queued',run_id=(job->>'id')::uuid,updated_at=clock_timestamp() where id=m.id returning * into m;
  else raise exception 'invalid_mail_action'; end if;
  return to_jsonb(m);
end $$;

create function public.begin_mail_send(p_run_id uuid,p_token uuid,p_message_id uuid)
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
  update public.outreach_messages set state='sending',attempt_id=gen_random_uuid(),attempt_started_at=clock_timestamp(),
    rfc_message_id='<jobpilot.'||id::text||'@'||split_part(c.email,'@',2)||'>',updated_at=clock_timestamp() where id=m.id returning * into m;
  return jsonb_build_object('dispatch',true,'message',to_jsonb(m),'connection',to_jsonb(c));
end $$;

create function public.mail_worker_result(p_run_id uuid,p_token uuid,p_message_id uuid,p_state text,p_data jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare r public.agent_runs; m public.outreach_messages; reply jsonb;
begin
  select * into r from public.agent_runs where id=p_run_id and lease_token=p_token and status='running' and lease_expires_at>clock_timestamp() and kind in ('mail_send','mail_sync') for update;
  if not found then raise exception 'lease_lost'; end if;
  select * into m from public.outreach_messages where id=p_message_id and user_id=r.user_id for update;
  if not found then raise exception 'mail_not_found'; end if;
  if (r.kind='mail_send' and m.run_id is distinct from r.id) or (r.kind='mail_sync' and m.connection_id::text is distinct from r.inputs->>'connection_id') then raise exception 'mail_not_found'; end if;
  if p_state='sent' then
    if m.state not in ('sending','send_unknown','sent') or coalesce(p_data->>'provider_message_id','')='' then raise exception 'invalid_mail_transition'; end if;
    update public.outreach_messages set state='sent',provider_message_id=p_data->>'provider_message_id',provider_thread_id=p_data->>'provider_thread_id',
      sent_at=coalesce(sent_at,clock_timestamp()),last_error=null,updated_at=clock_timestamp() where id=m.id returning * into m;
  elsif p_state in ('send_unknown','failed') then
    if m.state in ('sending','send_unknown') then
      update public.outreach_messages set state=p_state,last_error=left(p_data->>'error',500),updated_at=clock_timestamp() where id=m.id returning * into m;
    end if;
  elsif p_state<>'replies' then raise exception 'invalid_mail_transition'; end if;
  for reply in select value from jsonb_array_elements(coalesce(p_data->'replies','[]')) loop
    insert into public.mail_replies(user_id,message_id,provider_message_id,from_email,excerpt,received_at,classification)
      values(r.user_id,m.id,reply->>'provider_message_id',reply->>'from_email',left(reply->>'excerpt',4000),(reply->>'received_at')::timestamptz,reply->>'classification')
      on conflict(message_id,provider_message_id) do nothing;
    if reply->>'classification'='bounce' then update public.outreach_messages set delivery_status='bounce_observed' where id=m.id; end if;
  end loop;
  if p_state='replies' then update public.mail_connections set last_sync_at=clock_timestamp() where id=m.connection_id and user_id=r.user_id; end if;
  return to_jsonb(m);
end $$;
revoke all on function public.mail_command(uuid,text,jsonb),public.begin_mail_send(uuid,uuid,uuid),public.mail_worker_result(uuid,uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.mail_command(uuid,text,jsonb),public.begin_mail_send(uuid,uuid,uuid),public.mail_worker_result(uuid,uuid,uuid,text,jsonb) to service_role;
