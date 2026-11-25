-- Isolated test database only; all fixtures roll back.
begin;
insert into auth.users(id,email) values
 ('11111111-1111-4111-8111-111111111111','release-a@example.invalid'),
 ('22222222-2222-4222-8222-222222222222','release-b@example.invalid');
insert into public.job_postings(id,user_id,ats,external_id,company,title,url) values
 ('33333333-3333-4333-8333-333333333333','11111111-1111-4111-8111-111111111111','greenhouse','release-a','Example','Engineer','https://example.invalid/job');
insert into public.recommendation_runs(id,user_id,request_key,model_version,profile_digest,items) values
 ('44444444-4444-4444-8444-444444444444','11111111-1111-4111-8111-111111111111',gen_random_uuid(),'v2-test','digest',
  '[{"posting_id":"33333333-3333-4333-8333-333333333333","position":1,"score":90}]');
select public.record_recommendation_impression('11111111-1111-4111-8111-111111111111','44444444-4444-4444-8444-444444444444','33333333-3333-4333-8333-333333333333','55555555-5555-4555-8555-555555555555',1,600);
select public.record_recommendation_impression('11111111-1111-4111-8111-111111111111','44444444-4444-4444-8444-444444444444','33333333-3333-4333-8333-333333333333','55555555-5555-4555-8555-555555555555',1,600);
do $$ begin
 if (select count(*) from public.recommendation_impressions)<>1 then raise exception 'duplicate impression'; end if;
 if not public.reserve_release_usage('11111111-1111-4111-8111-111111111111','test','one',1) then raise exception 'first usage denied'; end if;
 if not public.reserve_release_usage('11111111-1111-4111-8111-111111111111','test','one',1) then raise exception 'retry charged'; end if;
 if public.reserve_release_usage('11111111-1111-4111-8111-111111111111','test','two',1) then raise exception 'quota exceeded'; end if;
 begin
  insert into public.recommendation_feedback(user_id,posting_id,signal) values('22222222-2222-4222-8222-222222222222','33333333-3333-4333-8333-333333333333','interested');
  raise exception 'cross-owner feedback accepted';
 exception when foreign_key_violation then null; end;
end $$;
insert into public.job_applications(id,user_id,company,role) values
 ('88888888-8888-4888-8888-888888888888','11111111-1111-4111-8111-111111111111','Research Fixture','Engineer');
do $$ declare r jsonb; bad boolean=false; begin
 r:=public.enqueue_agent_run('11111111-1111-4111-8111-111111111111','company_research','{"application_id":"88888888-8888-4888-8888-888888888888","urls":["https://example.invalid"]}','release-research');
 r:=public.claim_agent_run('research-sql-check',30);
 begin
  perform public.save_company_research((r->>'id')::uuid,gen_random_uuid(),'88888888-8888-4888-8888-888888888888','Fixture','[]','[]');
 exception when raise_exception then bad:=true; end;
 if not bad then raise exception 'unfenced research save accepted'; end if;
 perform public.save_company_research((r->>'id')::uuid,(r->>'lease_token')::uuid,'88888888-8888-4888-8888-888888888888','Fixture','[{"url":"https://example.invalid","excerpt":"Synthetic source"}]','[]');
 perform public.save_company_research((r->>'id')::uuid,(r->>'lease_token')::uuid,'88888888-8888-4888-8888-888888888888','Changed','[]','[]');
 if (select count(*) from public.company_research)<>1 or (select company from public.company_research)<>'Fixture' then raise exception 'research replay changed evidence'; end if;
end $$;
-- Column default user_id = auth.uid() follows app.user_id.
select set_config('app.user_id','11111111-1111-4111-8111-111111111111',true);
insert into public.writing_templates(kind,content) values('email','Use a concise style.');
do $$ begin
 if (select user_id from public.writing_templates)<>'11111111-1111-4111-8111-111111111111' then raise exception 'auth.uid() default not applied'; end if;
end $$;
rollback;
