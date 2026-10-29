# Sprint 6: product validation, onboarding and operational visibility

Development implementation completed on 29 October 2026. This completes the six-sprint development backlog; real provider/employer acceptance and production rollout are still separate release gates. No deployment, real Gmail send, employer submission, paid service provisioning or production schema changes were performed.

## Implemented

- **Evidence-based analytics:** a new owner-scoped PostgreSQL aggregate separates generated/prepared applications, native submission attempts, browser confirmation observations and explicit user reports. It counts distinct applications rather than repeated events. Latest preparation measurements are used per application.
- **Gmail outcomes:** only `sent` messages with provider receipt and send timestamp count as Gmail-accepted. Correlated replies, user-reviewed positive/negative/interview replies, observed bounces and uncertain sends are separate measures. Manual email flags remain labeled manual. Gmail acceptance is not delivery or reading.
- **Preparation and recovery measurements:** observed field completion, review/invalid/truncated counts, generation-to-first-preparation median/p95, failed/pending runs, retries that later succeeded, and newly measured server-stage median/p95. Independent employer verification and cost remain null, not invented zeroes or success percentages.
- **Onboarding:** Profile now imports PDF/DOCX files and shows a checklist derived from saved résumé content, current fact confirmations, target roles and followed sources. File validation/retry errors are visible. Existing résumé replacement asks for confirmation. Gmail is optional. Changed source facts invalidate matching readiness.
- **Account isolation:** upload credentials must belong to the initiating account; a late session lookup cannot upload one account's selected file with another account's token. Account changes clear the selected upload and ignore old completion callbacks.
- **Operations:** public `/health` remains process liveness. `/ready` checks development schema/database availability and, in durable mode, an actually polling or actively leased worker. Private `/ops/metrics` exposes bounded process HTTP measurements, database queue/lease counts and alert conditions.
- **Privacy:** generated request UUIDs, route templates, status and elapsed time are recorded without raw URLs, queries, headers, request bodies or user identifiers. Optional Sentry events are rebuilt from a narrow allowlist; request data, exception messages, stack locals, breadcrumbs and traces are not sent by this integration. Sentry remains off without a DSN.
- **Efficiency:** summary analytics use narrow metadata projections, explicit owner filters, pagination beyond PostgREST's default row cap, and bounded batches for related records. Readiness probes are cached for five seconds. HTTP route labels are bounded. Browser/fixture artifacts live in ignored directories.
- **Validation tooling:** real React/Vite and FastAPI local browser workflows, synthetic authentication/provider/database fixtures, hosted PostgreSQL contract checks, unit regressions, and a release/monitoring runbook. API startup output also works under Windows console encodings.

## Metric definitions and limits

| Measure | Meaning |
| --- | --- |
| Prepared / attempted / browser-observed / user-reported applications | Distinct application IDs with each corresponding event; these are separate sets, not a guaranteed nested conversion funnel |
| Field completion | Filled + preserved fields divided by all inspected fields in the latest preparation per application; measures retained controls, not factual correctness |
| Reviewed human reply rate | Distinct accepted messages with at least one user-reviewed positive/negative/interview reply, divided by Gmail-accepted messages |
| Correlated replies | Messages with correlated incoming thread records, including automated categories; not the same as confirmed human interest |
| Preparation time | Application creation to first recorded browser preparation; includes queueing and user time, not just model processing |
| Stage timing | Server node operation + checkpoint save elapsed time on newly completed stages; replayed checkpoints do not invent new samples |
| HTTP timing | Per-process app response timing, including response handling; bounded bucket p95 is an upper bound, not an exact percentile |
| Independent employer verification / cost | Not instrumented; null |

Historical runs have no stage timing backfill. An interrupted final timing emission can leave a completed stage without a measurement. HTTP measurements reset with each API process and are not a cross-instance aggregate. The existing status funnel is user-managed; it does not become verified employer truth merely because evidence analytics now exists.

## Worker readiness

`execution_workers` is a service-role-only RLS table. A separate worker thread announces every 15 seconds. The database considers a worker healthy only if its heartbeat is within 45 seconds and either its last successful queue poll is recent or its recorded active run has a matching worker ID and unexpired running lease. A heartbeat alone does not declare a stalled, non-polling idle process ready.

Stale heartbeat records are removed after a day on later announcements. `active_run_id` is a diagnostic reference rather than a foreign key, so run retention is independent of old process records. A stopping worker can remain visible within the short heartbeat/cache grace period. An active lease indicates liveness, not a guarantee of forward progress or correct provider behavior.

Public readiness returns booleans and a status only. Detailed operations data require `X-Ops-Token` matching a backend-only `OBSERVABILITY_TOKEN`; query-string credentials and normal user JWTs do not authorize this endpoint. An unset token disables detailed operations access. Optional error ingestion is not configured by a chat plugin connection.

## Verified

| Check | Result |
| --- | --- |
| Backend suite | **296 tests passed** |
| Frontend suite | **25 tests passed** |
| TypeScript + frontend production build | Passed, Vite 6.4.5 |
| Full-stack Chromium workflows | **2 passed**, using actual application UI/API with explicitly synthetic boundaries |
| Hosted development SQL smoke | Passed; owner isolation, latest preparation, receipt/reply denominators, timing samples, worker freshness/lease checks and restricted grants |
| Development security advisor | No findings |
| New missing-FK-index findings | None |
| Fixture cleanup | Zero hosted workers, applications, events and outreach messages remain |

The browser workflows exercise import → fact review → preferences → actual inline generation/progress stream → application detail → explicit submission report → analytics. They simulate a lost response after the report commit, verify request-key reuse on retry, reject a stranger's application detail request, isolate a second account, recover from an invalid PDF and retry unavailable analytics without falsely completing onboarding.

`backend/tests/fixtures/browser_server.py` is guarded by `JOBPILOT_E2E=1`, binds to loopback, does not load the developer `.env`, clears provider configuration, and is never imported by the production app. Authentication, résumé structuring/rendering, LLM calls, database storage and external boundaries are synthetic. These tests validate real UI/API orchestration; they do not replace actual Supabase browser authentication, real PDF host acceptance, actual worker process-kill recovery or provider/employer acceptance. Hosted SQL tests independently exercise real PostgreSQL/RLS/RPC contracts.

Existing Sprint 5 coverage remains: 7 extension broker/security tests and 15 browser cases were already verified there. The extension source did not change in Sprint 6. Existing FastAPI/Chroma deprecation and mixed static/dynamic Supabase import warnings remain non-blocking.

## Dependency verification

Installing the pinned browser-test dependency exposed eight existing npm findings. Compatible, non-forced fixes updated 13 packages, including Vite 6.4.3 → 6.4.5, PostCSS and other affected transitive packages. The final frontend tests/build and browser workflows pass with the new lockfile.

Two moderate npm findings remain for `react-router` / `react-router-dom` 6.30.6. The reported fixes require a major Router 7 upgrade; no forced upgrade was applied. Track [the backslash/open-redirect advisory](https://github.com/advisories/GHSA-wrjc-x8rr-h8h6) and [SSR error-hydration advisory](https://github.com/advisories/GHSA-337j-9hxr-rhxg). This application uses a client SPA rather than server-side hydration, but the affected dependency still needs a deliberate migration/assessment and routing regressions before public release. Do not describe the dependency audit as clean.

## Database rollout

| Local migration | Development project history | Production |
| --- | --- | --- |
| `20261029155926_product_validation_metrics.sql` | `20261029161811_sprint_6_product_validation_metrics` | Deferred |

Applied only to `test-project` (`klhpguohtcrsidqjwbqh`). The migration adds a service-only worker table, service-only heartbeat/health RPCs and authenticated owner-scoped `get_product_metrics()`, all `SECURITY INVOKER` with explicit search paths. Trial DDL and fixtures were first checked transactionally, then the migration and rollback smoke were verified against the development database.

The local runtime still needs matching development Supabase credentials before manually using Sprint 2–6 features. It previously points to the live project, which intentionally lacks those feature migrations. No `.env` credentials or runtime flags were changed. Reconcile MCP/local migration timestamps and the actual schema before any future `db push` or live rollout.

## Reproduce checks

Backend: `.venv/Scripts/python.exe tests/run_offline.py` from `backend`.

Frontend: `npm ci`, `npm test`, `npm run build` from `frontend`. For the browser workflows:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Resolve-Path ..) '.tool-cache/playwright'
npx playwright install chromium
npm run test:e2e
```

The browser config uses local ports 5174/8001, refuses existing servers, and stores fixture data under `.tool-cache/browser-api`. It uses `backend/.venv` by default; set `JOBPILOT_TEST_PYTHON` to an absolute Python executable if using another environment. Windows process restrictions may require running the test shell with enough permission to manage its own child servers. No real provider keys are required. Test profiles/reports/binaries and the fixture data are ignored.

SQL: run `backend/supabase/tests/product_validation.sql` only against the development database; it rolls back its fixtures. Operations setup, alert thresholds, acceptance steps and remaining release gates are in [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md) and [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

## Release status

The next stage is production readiness and real integration acceptance, not another invented development sprint. Required gates still include live Auth settings review, development runtime credential separation, real per-user Gmail/Hunter setup and approved test send/reply, supervised employer forms, a production-shaped worker recovery exercise, fresh-install/migration replay, Router dependency remediation, backups/retention/quotas, external monitoring/alerts and deployment origins/resources.

All six sprints have code and development verification. This is not a claim that every original production acceptance criterion has been met. No independent employer submission or recipient-delivery guarantees were added.
