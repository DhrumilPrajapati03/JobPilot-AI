# JobPilot release candidate ? 7 November 2026

**Code is prepared for review. Public launch is not approved or fully verified.**
No final commit/push/deployment or hosted release migration was performed.
Local environment files still point to JobPilotAI and remain unchanged.
Start with [the setup checklist](PRODUCTION_SETUP.md).

## Changes delivered

- Career Desk landing/login/shared app theme, real overview/workflow activity,
  responsive drawer and split opportunity browsing; all prior routes retained.
- R?sum? JSON parsing fix and source-evidence boundaries in writing.
- Private recommendation snapshots, opt-in visible impressions and explicit
  feedback/reasons. Observed display order is not a trusted relevance label.
- Optional local reranking and offline BGE/CrossEncoder comparison tools.
  Eligibility/default fit scores remain binding; no automatic training or promotion.
- Bounded cited company research, exact sources next to a reviewable cover draft,
  explicit replacement of saved text and failed-run recovery.
- Functional private email/DM/cover templates consumed by inline/durable writers;
  revision conflicts preserve unsaved text, and saves retain the initiating account.
- Active-session validation, periodic chat/progress stream checks and tool-boundary
  revalidation in production. Unexpected provider details no longer enter chat errors.
- Production guards, shared daily quotas, bounded request bodies, patch-level
  dependency lock, Router 7, CSP/security headers, worker blueprint and pinned CI.
- Non-root image definition, offline model preparation, local PDF fonts,
  recovery/restore scripts, rollout/rollback and operator documentation.

## Verification completed

| Check | Result / scope |
| --- | --- |
| Backend full regression | **338 passed** in clean `backend/.venv-release`; no developer dotenv loaded |
| Frontend checks | **27 passed**, including delayed-token and delayed-execution account-switch saves |
| App browser journeys | **9 passed**: public/auth, overview/nav/mobile/errors, route preservation, template conflict, feedback dwell, research retry/source-bound save, full onboarding/generation/evidence/analytics and account isolation |
| Extension | **7 unit checks + 15 Chromium browser tests passed**; no real employer submission |
| Frontend release build | TypeScript/Vite passed with synthetic HTTPS/WSS release configuration |
| Secret-key guard | Synthetic server key correctly rejected before frontend build |
| npm audits | Frontend and extension: **zero findings** |
| Backend dependency gate | Pass with **four reviewed Chroma server-path exceptions**, not vulnerability-free; expires 7 December. [Assessment](DEPENDENCY_SECURITY.md) |
| Dependency consistency | 165 exact baseline distributions; clean-env `pip check` passed |
| Fresh database | All **19 migrations and seven SQL suites passed** on disposable network-isolated PostgreSQL 17 |
| Research DB contracts | Wrong lease denied; repeated save preserves source evidence; other-account reads denied |
| Worker process recovery | Real Worker killed after synthetic DB persistence; after real lease expiry a replacement restored the checkpoint. Two attempts; exactly one application/version/email draft |
| Synthetic backup/restore | `pg_dump` archive restored into a separate local DB; fixture and release schema verified |
| Optional ML setup | Dependency dry-run resolved without installation/model downloads; synthetic baseline evaluation CLI works. Actual model inference/quality is unverified |
| Config/docs | Workflow/blueprint YAML contracts, relative documentation links and Git whitespace checks pass |
| Independent UI review | Calibrated reviewer; six new findings and two follow-ups fixed and source-rechecked. Runtime/browser checks performed separately |

Three backend warnings remain: Starlette/httpx compatibility deprecation, Chroma
legacy embedding-function deprecation and an intentionally unsupported-algorithm
test's short-key warning. Tests pass; these are not runtime/provider acceptance.

## Open gates and verification limits

**Linux image smoke is pending.** The initial image reached dependency installation
but failed on a package-download read timeout. Retry uses a pinned parallel installer
and package cache, but the registry download stayed extremely slow and was stopped.
Only task-owned build processes were stopped; Docker images/cache/other containers
were preserved. No complete release image, Linux PDF/embedding smoke or resource
measurement is claimed. Re-run on a reliable connection or CI:

```powershell
docker build -t jobpilot-release:review backend
backend/.venv-release/Scripts/python.exe backend/scripts/check_image.py jobpilot-release:review
```

The smoke script requires non-root execution, read-only root filesystem, disabled
network, bounded resources, prepared embeddings, real PDF rendering, process health
and fail-closed readiness without credentials. CI includes this gate, but remote CI
has not run because final push is held for review. Branch protection is not configured.

New migration `20261107152821_release_recommendations_research.sql` is tested
locally and **unapplied to both hosted projects**. Old Sprint 1?6 migrations already
exist on JobPilotAI. Reconcile history, verify real backup recovery and run advisors
before approved rollout. No main-project data was exported or modified this turn.

Live Auth SMTP/redirects/two-account revocation, Composio/Gmail/Hunter/digest, chosen
host capacity/HTTPS streams, real permitted forms, external alerts, privacy/retention
and provider restore acceptance remain. The user explicitly selected **finish code
and list setup steps** for missing credentials. Mailbox/send defaults stay disabled.
Fixture tests do not prove provider behavior, deliverability or employer acceptance.

No independent labelled ranking dataset was supplied. Baseline v2 stays default;
v3 is an opt-in experiment. BGE/CrossEncoder quality, optional ML security/resource
acceptance and any promotion remain pending. No interview or ranking uplift is claimed.

The old local `.venv` was in use and could not be fully updated on Windows; the clean
release environment is separate. Stop the old backend and use the release environment
or reinstall the lock after stopping it. Native PDF libraries are checked by the
pending Linux image smoke, not by the Windows fixture tests.

## Reproduce local checks

8 November addition: Google/GitHub sign-in, PKCE callbacks, legacy email-link
compatibility, provider error/availability handling and browser-return recovery.
At that point, live providers were disabled pending [setup](SOCIAL_LOGIN_SETUP.md).
That code implementation changed no hosted configuration, schema or deployment.
New auth tests are recorded there.
Frontend verification is now 35 checks and 14 app browser workflows, plus the
TypeScript/Vite build. Other 7 November verification counts above remain historical.

Subsequent approved Auth setup: Composio–Supabase connection confirmed active;
JobPilotAI Auth is healthy. Added and re-read only the exact localhost/127.0.0.1
`/login` return URLs, preserving the existing root entry, site URL and other Auth
settings. At that point, Google/GitHub client IDs/secrets were absent and both
providers were disabled pending owner console setup. No database/data/deployment changes.

13 November owner-completed Auth setup: read-only checks confirm Google/GitHub
enabled with credentials present, email required and Google nonce checks enabled.
Auth is `ACTIVE_HEALTHY`; public Auth settings return HTTP 200 with both providers
available. Both authorize endpoints return HTTP 302 to their expected HTTPS provider
with JobPilotAI's exact callback. Local `/login` return URLs remain configured.
No hosted settings, schema, records, environment files, push or deployment changed
during verification. The owner subsequently confirmed local Google/GitHub login
works on 13 November. This is owner-reported real-browser acceptance, separate from
the assistant's configuration/redirect probes. Distinct-account isolation, identity
linking, audience coverage and production-domain acceptance remain open. Final push
and deployment remain held for the user's review.

From backend: `.venv-release/Scripts/python.exe tests/run_offline.py`.
From frontend: `npm test`, `npm run build`, `npm run test:e2e`.
Set `JOBPILOT_TEST_PYTHON` to the clean backend Python for browser fixtures.
From extension: `npm test`, `npm run test:browser`.
From root: `backend/.venv-release/Scripts/python.exe backend/scripts/check_database.py --worker-recovery`.
Docker is required only for the database/image checks. Tool caches are ignored.

[Deployment/rollback](DEPLOY.md) ? [remaining operator steps](PRODUCTION_SETUP.md) ?
[production gates](PRODUCTION_READINESS.md) ? [database history](DATABASE_ROLLOUT_STATUS.md).
