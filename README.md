# JobDots

A personal job-hunting assistant for one person. A team of expert agents finds jobs, researches companies, tailors the resume, fills application forms, finds the right people and drafts outreach. Nothing leaves the system (email, DM, form submit, referral request) until the owner approves it.

JobDots is being rebuilt from the JobPilot AI codebase on this branch (`jobdots`).

| Document | What it covers |
|---|---|
| [docs/jobdots_final_plan.md](docs/jobdots_final_plan.md) | The plan: agents, architecture, data model, UI, build days, hosting, risks |
| [docs/jobdots_codebase_triage.md](docs/jobdots_codebase_triage.md) | What is kept, reshaped or removed from JobPilot, and on which day |
| [docs/CODEBASE_AUDIT_INPUT.md](docs/CODEBASE_AUDIT_INPUT.md) | Audit of the JobPilot code (routes, tables, queue, tests) |
| [docs/spikes/](docs/spikes/) | Spike results (Google Calendar via Composio vs direct API) |

## Status

Days 0 and 1 of the plan are done (export, local Postgres + pgvector, Groq/Ollama, owner auth; Supabase and LangChain are gone). Day 2 added the case spine (cases, actions with approvals, the `policy.yaml` engine, budgets, per-case queue concurrency), Google/GitHub login, the JobPilot import, nightly backups and the eval harness. Day 3 adds the agent runtime: Supervisor, Scout and Researcher.

## Local stack

Needs Docker Desktop and Python 3.12 (`uv python install 3.12`).

```
cp .env.example .env                 # set POSTGRES_PASSWORD, OWNER_EMAIL, OWNER_API_TOKEN
docker compose up -d                 # db -> migrate (alembic upgrade head) -> api + worker
curl -H "Authorization: Bearer $OWNER_API_TOKEN" http://127.0.0.1:8000/api/v1/auth/me
```

Postgres 17 + pgvector listens on 127.0.0.1:55432 and the API on 127.0.0.1:8000; nothing is exposed beyond the laptop. Provider keys such as `GROQ_API_KEY` are read from `backend/.env` when it exists. `config/policy.yaml` (action modes, caps, budgets) is mounted read-only and re-read when it changes.

### Signing in

JobDots has one user, the owner. Run the frontend (`cd frontend && npm run dev`) and open http://localhost:5173:

1. First time: choose **Use owner token instead** and paste `OWNER_API_TOKEN`. The API trades it for an HttpOnly session cookie; the browser never stores the token.
2. In **Settings → Sign-in**, link your Google and GitHub accounts. Only those exact accounts (by provider id, not email) can sign in afterwards.

Login needs a Google OAuth client (Web application, redirect URI `http://localhost:8000/auth/google/callback`) and a GitHub OAuth app (callback `http://localhost:8000/auth/github/callback`), with their ids and secrets in `backend/.env` (see `backend/.env.example`). The bearer token keeps working for scripts and recovery until `BEARER_AUTH_ENABLED=false`.

The schema lives in `backend/migrations/` (Alembic). Revision `0001` is the JobPilot schema without Supabase auth, row-level security or grants; see the header of `backend/migrations/0001_baseline.sql`. New schema changes are new Alembic revisions:

```
cd backend && alembic revision -m "describe the change"
```

### Experts

Experts are data: `backend/app/experts/builtin.yaml` holds the roster (synced into `agent_spec` on start). Each spec lists the tools it may use (the registry in `app/experts/tools.py` enforces the allowlist), the action kinds it may propose (only those in `policy.yaml`) and its budgets. Experts that are not built yet stay `draft`, and Supervisor says what it is waiting for.

* **Scout** runs daily (routine `scout_daily_scan`), scans your boards and opens a case for each strong, eligible new match.
* **Supervisor** routes each case: Researcher, then Tailor, then Email Outreach. No model calls.
* **Researcher** writes a cited `company_brief`: every claim names its sources, uncited claims are dropped, and confidence is capped by the number of sources.
* Routines catch up after the laptop was off ("JobDots woke up and ran N missed routines"). Every step is traced in `run_step`.

```
curl -H "Authorization: Bearer $OWNER_API_TOKEN" http://127.0.0.1:8000/api/v1/experts         # roster with live state
curl -X POST -H "Authorization: Bearer $OWNER_API_TOKEN" http://127.0.0.1:8000/api/v1/experts/scout/run
```

### Backups

The worker backs up the database every night after 02:00 (your `policy.yaml` time zone), and right away if the last good backup is more than a day old (the laptop was off). Each backup is encrypted before it leaves `pg_dump`'s temp file.

```
cd backend
python scripts/backup.py new-key         # once: writes BACKUP_ENCRYPTION_KEY to .env; copy it to your password manager
python scripts/backup.py connect-drive   # optional: upload to Google Drive (drive.file); reconnect weekly in Testing mode
docker compose up -d
docker compose exec worker python scripts/backup.py status
```

Without Drive, the encrypted files stay in `./data/backups`. With Drive, a local copy is deleted only after Drive's checksum and size match. Restore test (into a scratch database, never the live one): `docker compose exec worker python scripts/backup.py restore /app/data/backups/<file> --into <scratch database URL>`.

### Importing JobPilot data

```
cd backend
python scripts/import_jobpilot.py --export D:/jobdots-archive/jobpilot-export-2026-11-24           # dry run
python scripts/import_jobpilot.py --export D:/jobdots-archive/jobpilot-export-2026-11-24 --apply
python scripts/import_jobpilot.py --export D:/jobdots-archive/jobpilot-export-2026-11-24 --verify
```

The import is idempotent and keeps every source row in `legacy_import`. Imported drafts are read-only records; nothing old can be sent.

## The old JobPilot app

The complete JobPilot code is on branch `legacy/jobpilot-v1` (tag `jobpilot-v1-baseline`). To run it beside JobDots, check it out in a second folder:

```
git worktree add ../jobpilot-v1 legacy/jobpilot-v1
```

Copy `backend/.env` and `frontend/.env` into that folder, since git does not copy ignored files.

## Checks

```
cd backend   && python tests/run_offline.py      # backend, no .env loaded
cd backend   && python scripts/check_database.py --worker-recovery   # migrations + SQL tests on a throwaway Postgres (Docker)
cd backend   && python -m evals                   # agent evals (Scout matching, Courier policy); --semantic, --record
cd frontend  && npm test && npx tsc --noEmit
cd extension && npm test
```

CI runs the same checks on pushes to `main` and `jobdots` (`.github/workflows/release-checks.yml`).

## Frontend work

Load the project skills `frontend-design` and `jobdots-agentic-ui` (in `.claude/skills/`) before designing or building any screen.
