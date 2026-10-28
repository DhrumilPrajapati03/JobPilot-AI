-- Cover the composite session-owner FK as well as owner-scoped timeline reads.
create index application_events_session_owner on public.application_events(session_id,user_id,id);
