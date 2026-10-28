-- Cover the event ownership FK as well as per-user audit reads.
create index agent_run_events_parent_owner_idx on public.agent_run_events(run_id,user_id);
-- This coordination table is intentionally worker-only; client grants stay revoked.
create policy run_lock_worker_access on public.agent_run_locks for all to service_role using (true) with check (true);
