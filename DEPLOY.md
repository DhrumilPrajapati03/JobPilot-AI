# JobPilot production release

Updated 7 November 2026. **No final push or deployment has been performed.**
Review [release evidence](RELEASE_READINESS.md) and [setup steps](PRODUCTION_SETUP.md).

## Architecture and hosting

React static frontend ? FastAPI Docker API ? Supabase PostgreSQL/Auth/Storage.
API ? PostgreSQL queue ? continuously running Docker worker. The worker handles
generation, discovery scheduling, research, ranking experiments and mailbox jobs.
PostgreSQL leases/checkpoints fence stale workers; Redis is not required.

API and worker must use the **same reviewed revision, database and durable mode**.
Submission stays manual; email sends require approval of their current revision.
Chroma is an in-process, disposable cache rebuilt from the owner's canonical r?sum?.
Do not expose a Chroma HTTP service.

`render.yaml` now defines frontend, API and worker with auto-deployment disabled.
API health checks use `/ready`, including worker health. Backend plans are paid,
continuously running instances; review current capacity/cost before provisioning.
The old sleeping free-server/wake-up-cron strategy is superseded. Nothing was provisioned.

## Database rollout

Main DB: **JobPilotAI** (`vgpkzekcfnogvvykfzoo`). Sprints 1?6 are already applied.
Hosted/local timestamps differ: use [the rollout mapping](DATABASE_ROLLOUT_STATUS.md).
**Do not replay old migrations or blindly run `db push`.**

New additive release migration, **not applied to either hosted project**:

`backend/supabase/migrations/20261107152821_release_recommendations_research.sql`

It adds private feedback/impressions, research, templates, quotas and strict session
validation. It does not rewrite saved application materials. After approval:
verify provider backup/recovery, compare actual schema/history, rehearse in isolation,
apply the exact reviewed SQL through the Supabase migration tool, record the returned
version and run SQL suites plus security/performance advisors. Review Auth settings.
CLI v3 is local-first; inspect installed help before using older remote commands.

Local, synthetic verification from the repository root:

```powershell
backend/.venv-release/Scripts/python.exe backend/scripts/check_database.py --worker-recovery
```

This creates/removes one network-isolated PostgreSQL 17 container, applies all 19
migrations, runs RLS/RPC suites, kills/resumes a real Worker with synthetic stages,
and restores a synthetic archive into another DB. No hosted/private data is exported.
Hosted Auth/Storage and real backup acceptance remain separate gates.

## Environment

Keep credentials in secure provider settings, outside Git/chat/URLs.

| API **and worker** | Required setting |
| --- | --- |
| Database | Identical `SUPABASE_URL`, public `SUPABASE_KEY`, private `SUPABASE_SERVICE_KEY` |
| Generation | `LLM_PROVIDER=groq`, valid `GROQ_API_KEY`; deliberate model overrides |
| Runtime | `APP_ENV=production`, `DEBUG=false`, `EXECUTION_MODE=durable`, `USAGE_LIMITS_ENABLED=true` |
| Origins | `FRONTEND_URL`: exact HTTPS frontend origins, comma-separated |
| Shared secrets | Random `SECRET_KEY`, `CRON_SECRET`, `OBSERVABILITY_TOKEN`, each ?32 characters |
| Limits | Initially 25 application runs and 100 chat turns per user/day; review usage |
| Mail | Keep mailbox/send flags false until real acceptance passes |

The blueprint generates shared random secrets in its environment group.
Render does not support `sync:false` prompts inside groups, so database/provider/origin
prompts are repeated on API and worker: **enter identical values on both**.
Legacy HS256 tokens also need `SUPABASE_JWT_SECRET` on the API; ES256/RS256 use JWKS.
Production validates issuer, required claims and active session before private access.

| Frontend build | Value |
| --- | --- |
| `VITE_RELEASE_MODE` | `true` |
| `VITE_SUPABASE_URL` | Same JobPilotAI URL as both backend processes |
| `VITE_SUPABASE_ANON_KEY` | That project's public publishable/anon key |
| `VITE_API_BASE_URL` | `https://<api-host>` |
| `VITE_WS_BASE_URL` | `wss://<api-host>` |

Rebuild frontend after changes. Builds reject insecure release URLs and Supabase
server keys. CSP uses configured origins; static hosting sets security/cache headers.

## Build, release and rollback

```powershell
docker build -t jobpilot-release:review backend
backend/.venv-release/Scripts/python.exe backend/scripts/check_image.py jobpilot-release:review
```

The image locks dependencies, includes PDF libraries/fonts and checksum-verified MiniLM,
and runs as UID 10001. No local env/venv/data/tests enter it. Inference never downloads.

After release approval, start worker first, then API/frontend at the same revision.
A worker must announce a recent poll/active lease before readiness passes. Test HTTPS
Auth callbacks, CORS, SSE/WebSocket reconnects, two accounts and exact-origin extension.

Require `.github/workflows/release-checks.yml` in GitHub branch protection (external
setting). CI checks application/extension/browser flows, audits, SQL, worker recovery,
synthetic restore and image smoke. Record the approved commit and previous revision.

Rollback: disable sends/new work, pause scheduling and drain/inspect the queue; roll
API/worker back together, then frontend. Drain new research/recommendation kinds
before returning to older workers. Keep additive schema/data; never drop tables
as code rollback. Database restore requires a verified backup and deliberate approval.
**Final push and deployment wait for user review.**
