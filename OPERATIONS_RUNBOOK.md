# JobPilot operations and release validation

Release runbook, updated 7 November 2026. Production deployment remains deferred. See [release evidence](RELEASE_READINESS.md), [setup](PRODUCTION_SETUP.md) and [deployment/rollback](DEPLOY.md).

## Runtime separation

The user chose to keep the local runtime on `JobPilotAI` and apply its remaining Sprint 2–6 feature migrations on 30 October 2026. See [migration mapping and verification](DATABASE_ROLLOUT_STATUS.md). Both environment files remain unchanged, and manual UI edits now affect the existing project data. Keep `test-project` for isolated fixtures and future migration trials. Match frontend publishable keys and backend URL/keys to the same project; service-role and monitoring credentials belong only on the backend.

For future live migrations, inventory the baseline/schema and reconcile differing CLI/MCP migration timestamps against the rollout record. Test a fresh bootstrap and incremental replay in an isolated environment, retain backups, and roll API/frontend/worker/extension versions out together. Do not blindly run `db push` against an unreconciled live history.

## Monitoring configuration

Backend-only settings:

```dotenv
EXECUTION_MODE=durable
OBSERVABILITY_TOKEN=
REQUEST_LOGS_ENABLED=false
SENTRY_DSN=
```

Set a long random operations token when configuring a private scraper. Enable request logs only when desired; their records contain a generated request UUID, method, route template, status and elapsed milliseconds. Run Uvicorn with `--no-access-log` to avoid its separate raw-URL access logs; the Docker command now includes that flag. Provider failures now log exception categories. Recheck logging and third-party SDK output on the selected host before launch.

Sentry is optional and remains disabled without a DSN. This integration sends only a sanitized exception category and fixed message, with default/automatic integrations, request data, breadcrumbs, session tracking and traces disabled. Configure ingestion, retention and alert recipients deliberately and test with a synthetic error. No external monitoring project, alerts or paid plan was created here.

| Endpoint | Use |
| --- | --- |
| `GET /health` | Process liveness only; can be healthy while DB/workers are unavailable |
| `GET /ready` | DB/schema readiness; durable mode also requires a recent polling or actively leased worker; returns 503 when unavailable |
| `GET /ops/metrics` + `X-Ops-Token` | Private queue/lease/worker health and this process's HTTP counters/latencies/alerts |

Example from PowerShell, using a locally configured token rather than a URL parameter:

```powershell
Invoke-RestMethod 'http://localhost:8000/ready'
Invoke-RestMethod 'http://localhost:8000/ops/metrics' -Headers @{'X-Ops-Token'=$env:JOBPILOT_OPS_TOKEN}
```

Readiness probes cache DB results for five seconds. Worker announcements run every 15 seconds, freshness expires after 45 seconds, and stale rows are removed after a day. A heartbeat without a recent poll or matching valid active lease is unhealthy. Readiness does not test Google/Hunter/LLM/PDF-provider behavior, correct results or capacity.

## Alert meanings

| Flag | Trigger / response |
| --- | --- |
| `database_unavailable` | Cannot verify the health RPC/schema. Check project configuration, migrations and DB connectivity; keep diagnostic payloads private |
| `no_healthy_worker` | Durable mode with no recent polling/leased worker. Check separate worker process, runtime mode and required migrations |
| `expired_leases` | At least one running row has an expired lease. Verify recovery claims, stale-worker fencing and resource saturation |
| `failed_runs` | At least one terminal failed run in the last 24 hours. Inspect owner-scoped run status and sanitized worker diagnostics |
| `queue_delay` | A ready queued/retry job is more than 300 seconds overdue. Check capacity, worker health and scheduling |

These are JSON flags, not configured notification deliveries. Set up an external poller/alert destination at deployment time. Aggregate HTTP counters per instance in your monitoring system; they reset on restart. `p95_bucket_upper_ms=null` for a populated route means its p95 fell above the largest 10,000 ms bucket, not a measured zero. Stage timing p95 is an actual SQL percentile over recorded successful stage measurements.

If `/ready` reports a worker but work is slow, inspect stage timing/queue growth and a specific run. A valid active lease establishes liveness, not guaranteed progress. A sleeping host cannot process jobs. Avoid enabling mail sending until the durable worker and provider acceptance are confirmed.

## Product metrics

The Analytics page keeps manual status/email statistics separate from observed evidence/Gmail receipts. An empty denominator is unknown; independent employer verification and monetary cost are not instrumented. Browser confirmations, user reports, accepted Gmail messages and recipient delivery must never be conflated.

Use latest-per-application field completion only as a control-fill measure. Use a representative, human-labeled dataset and supervised real forms to measure answer correctness. Existing synthetic matching benchmarks do not establish real-world job precision or interview uplift.

## Release acceptance sequence

1. Complete Auth leaked-password-protection / unused password sign-in review from [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).
2. Use isolated development accounts for destructive/fixture tests; manual UI validation may use JobPilotAI as requested. Verify two real accounts, token revocation/logout/cache isolation, Storage ownership, résumé uploads and source-fact review. Keep API/frontend/worker project credentials consistent.
3. Run unit, full-stack fixture browser and hosted SQL checks. Exercise fresh provisioning and migration replay. Router 7 and dependency patches are implemented; require the final audited lockfiles and routing regressions. Review the time-limited Chroma server-path exceptions.
4. Configure real Composio Gmail auth/verifier and Hunter credentials. With explicit user consent and chosen test recipients, verify OAuth ownership, approval, frozen PDF/sender, a send receipt, tracked reply, disconnect/reconnect and uncertain-send reconciliation. Never retry an uncertain send blindly.
5. Exercise permitted employer forms with a user reviewing/finally submitting. Verify custom controls, upload server rejection, multi-step navigation, frames and actual confirmation evidence. Do not send duplicate or synthetic applications to real employers for automation testing.
6. Run API and a separate worker with production-shaped resources. Deliberately interrupt a fixture generation before/after checkpoint/persistence; verify lease takeover and no duplicate application/materials. Verify cancellation, provider retry windows and graceful shutdown.
7. Configure exact origins, HTTPS callbacks and extension policy; test CORS, authenticated WebSockets and reconnects. Verify fonts/PDF/system dependencies, retention/quotas/backups and a restore exercise.
8. Configure external monitoring ingestion, test alert delivery with synthetic incidents, set latency/error/queue budgets based on measured capacity, then approve and perform deployment.

Sprints 1–6 status files document completed implementation and the practical limits of each verification. This runbook does not authorize sending external messages or deploying the app without the corresponding user instruction.

## Release additions ? 7 November

Production startup requires durable mode, shared usage limits, secure origins and random secrets. Strict API token verification also checks the signed session against Supabase. The new release migration remains unapplied to hosted projects; Sprint 1?6 schema already exists on JobPilotAI. `/ready` checks the release schema in production.

Local release checks include 19 fresh migrations, seven SQL suites, actual Worker process kill/lease-expiry/resume with one committed material set, and a separate synthetic restore. These use no hosted records and do not prove provider backup recovery or live Gmail acceptance.

Review retention in [PRODUCTION_SETUP.md](PRODUCTION_SETUP.md). The release adds a service-only telemetry pruning RPC with a 30-day minimum. No schedule is enabled automatically. Preserve Gmail/approval/audit evidence according to an approved policy; never delete it solely to clear an alert.
