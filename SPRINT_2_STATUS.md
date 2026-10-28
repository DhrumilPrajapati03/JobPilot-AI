# Sprint 2: durable orchestration

Implemented on 27 October 2026. Development implementation and automated verification are complete; live activation and deployment acceptance remain deferred. See [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) for the carry-forward production work and recommended timing.

## Execution model

`EXECUTION_MODE=durable` routes manual application generation, assistant-created applications, posting drafts, job-board scans, and digest sends through PostgreSQL. The default remains `inline` for existing installations until their database and worker are ready. All API and worker instances serving one project must use the same execution mode.

The API validates the authenticated user and inserts a run; a separate `python -m app.workers.runner` process claims it. Closing a tab or restarting an API process does not discard queued work. Workers also enqueue due daily schedules every ten minutes when `DISCOVERY_AUTO_SCAN=true`; the API scheduler and cron endpoint can do the same. Database keys deduplicate the scheduled requests.

Supabase PostgreSQL supplies the queue rather than introducing another Redis/Celery deployment. Existing Redis/Celery dependencies and legacy Compose configuration are unchanged; durable mode does not use them. A worker handles one run at a time. Start additional workers to serve different accounts concurrently; only one run per account can hold an execution lease.

## Persistence and ownership

| Object | Purpose |
| --- | --- |
| `agent_runs` | Owner, kind, request identity, inputs, status, current stage, attempts, outputs, checkpoints, lease and scheduling times |
| `agent_run_events` | Ordered, persistent status events with a composite run/owner foreign key |
| `agent_run_locks` | Worker-only per-account coordination rows |

Run and event tables allow authenticated owners to select their own rows. Clients cannot insert, edit, claim, finish, or retry runs directly. The API passes the verified owner to privileged functions. All new functions use `SECURITY INVOKER`, an explicit empty search path, qualified table names, and service-role-only execution grants. Queued inputs have a strict field allowlist; access tokens and provider credentials are not enqueued. Checkpoints contain private profile/resume/material snapshots and require the same care as the original application records.

Workers claim with `FOR UPDATE SKIP LOCKED`, rotate a lease token, and renew through a separate heartbeat thread. A unique partial index and a per-account lock prevent two running jobs for one account. Checkpoint, event, application/material, referral, form-preparation, child-enqueue, and finish RPCs reject stale leases. Recovery reuses saved stage results, with at most three automatic attempts and bounded exponential delays. A crash on the final attempt becomes a terminal failure when the next worker examines the expired lease.

## Application graph

The LangGraph `StateGraph` has these nodes:

1. Parse the JD and recheck eligibility for discovered postings.
2. Load and snapshot the owner's profile and base resume.
3. Tailor the resume and calculate the keyword score.
4. Check PDF rendering, preserving a warning when browser export is needed.
5. Generate the cover letter.
6. Generate the email sequence.
7. Generate LinkedIn messages.
8. Aggregate outreach fallback warnings.
9. Save application, tailored resume, email drafts, posting linkage, and the save checkpoint in one transaction.
10. Check referrals without overwriting later user edits or outcomes.
11. Prepare employer-form answers.

Checkpoints are implemented by the application's Supabase repository, not a LangGraph-native checkpoint saver. Recovery reconstructs the graph and skips operations for completed nodes. The atomic save checkpoint means a lost database response does not create another application on recovery. PDF bytes are checked rather than persisted as graph state; existing on-demand exports remain available.

Provider calls can repeat if a process stops after the call but before its checkpoint. This can incur additional AI usage. Application/material persistence is idempotent independently of that window. Generated outreach remains drafts; this graph does not submit employer forms or send recruiter emails.

## Requests, retries, and progress

- `POST /applications/generate` and `POST /autopilot/digest/send` accept `Idempotency-Key`. Reusing a key with changed inputs returns 409. Keys are scoped to owner and job kind.
- Posting drafts use a stable posting key. Manual drafting of a previously failed posting retries the saved run; automatic scans do not reset exhausted runs indefinitely.
- Scheduled scans/digests use the owner's local date. Completed schedule dates advance monotonically. Out-of-date scheduled digests are skipped.
- `GET /runs/{id}` returns a sanitized owner-only status and result. It omits input snapshots and lease tokens.
- `GET /runs/{id}/events?after={cursor}` returns up to 200 owner-only audit events and a next cursor.
- `POST /runs/{id}/retry` explicitly requeues a failed application/scan while preserving checkpoints. It rejects other owners, non-failed jobs, and digest retries. Request a new digest deliberately instead.
- Authenticated WebSockets replay database events across API processes. Explicit retries start replay from their latest queued marker so a historical terminal error cannot hide the retry. HTTP events retain the full audit history.
- The application and chat UI show queued/worker/retry messages. Scan and digest mutations wait for committed completion rather than immediately reporting success. Polling stops accepting results when the account changes. A ten-minute UI wait limit leaves background work running.

For digest delivery, the worker freezes sender, recipient, subject, HTML, and text before sending. Recovery uses the same Resend idempotency key. Retries stop after 23 hours from preparation, before Resend's documented 24-hour key expiration. Expired or ambiguous runs require a new deliberate send request; they are not automatically reset. The provider guarantee is described in [Resend's idempotency documentation](https://resend.com/docs/dashboard/emails/idempotency-keys).

Discovery scans can repeat after interruption; they are not a transaction encompassing every board. Posting identity constraints and insert-only upserts prevent duplicate rows and preserve an existing posting's user state. A lease recheck follows board fetching; child application jobs are lease-fenced. Source counts and scan metadata are refreshed on a replay and are not a snapshot-consistent audit of a partially completed scan.

## Local activation

1. Provision the baseline schema and all existing feature/Sprint 1 migrations on a development Supabase project.
2. Apply `backend/supabase/migrations/20261027055731_durable_execution.sql`, then `20261027062316_durable_execution_indexes.sql`.
3. Configure the same Supabase URL, anon key, service-role key and AI provider configuration for API and worker. Keep the service-role key on the server. In `backend/.env`, use valid booleans and remove unrelated configuration entries.
4. Set `EXECUTION_MODE=durable` for both processes. Defaults: `RUN_LEASE_SECONDS=120`, `RUN_POLL_SECONDS=2`.
5. From `backend`, run `python -m uvicorn app.main:app --reload` in one terminal and `python -m app.workers.runner` in another. `--once` processes one available job without running the scheduler and then exits.
6. Alternatively, run `docker compose -f docker-compose.durable.yml up --build` from `backend`. This starts the API and worker using the hosted development database.

Do not mix inline and durable instances against one running application. Stop intake and let workers drain before rolling back modes; switching to inline does not process existing durable runs. A stopped worker leaves work queued; an expired claimed lease is recoverable when a worker next polls. A stop signal allows the current run to finish; a host kill leaves it for lease recovery.

## Supabase verification record

Changes were applied only to `test-project` (`klhpguohtcrsidqjwbqh`). The live `JobPilotAI` project and local runtime mode were not changed.

| Local SQL | Test-project migration history |
| --- | --- |
| `20261027055731_durable_execution.sql` | `20261027060530_sprint_2_durable_execution` |
| `20261027062316_durable_execution_indexes.sql` | `20261027062405_sprint_2_durable_execution_indexes` |

MCP assigns remote timestamps. Baseline tables were previously provisioned manually. Reconcile local/remote migration history against the actual schema before adopting CLI `db push`; do not blindly replay creation statements or mark missing schema as applied.

The rollback-only `backend/supabase/tests/durable_execution.sql` smoke test passed against hosted PostgreSQL. It covers request deduplication, payload conflict, same-account execution locking, heartbeat renewal, expired-lease recovery, stale-token rejection, checkpoint preservation, cross-account child rejection, atomic partial-save rollback, duplicate-save prevention, posting linkage, preserved referral edits, explicit retry ownership, exhaustion, client grants, and two-account run/event RLS. Test users and business rows roll back.

Security Advisor reported no new Sprint 2 warnings after the follow-up index/policy migration. The pre-existing `set_updated_at` search-path warning remains deferred; [Supabase remediation](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable). Existing baseline policy and unrelated-index performance recommendations remain outside this sprint.

Python tests exercise a replacement worker recovering after a material commit whose response was lost, graph stage reuse, bounded digest retry identity, expired delivery refusal, lease loss, cancellation, private status reads, and terminal event replay. Provider boundaries are stubbed; these tests do not send email or consume live LLM credits. Browser acceptance, an actual host process-kill test, live Resend verification, Docker execution, capacity/retention checks and deployment acceptance remain on the production checklist.

Regression verification: 204 backend tests, 9 frontend tests, and the frontend production build passed. Run `python tests/run_offline.py` from `backend` to isolate the regression suite from developer `.env` entries; use `npm test` and `npm run build` from `frontend`. LangGraph is pinned to the tested 1.2.6 API.
