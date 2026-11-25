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

Day 0 of the plan is done: secret scan, JobPilot snapshot, data export and removal of parts JobDots will not use. Day 1 is in progress: the local Postgres + pgvector stack and the Alembic baseline are in place. Until the backend is switched over, it is still the JobPilot app (Supabase auth and database).

## Local stack

Needs Docker Desktop and Python 3.12 (`uv python install 3.12`).

```
cp .env.example .env                 # then set POSTGRES_PASSWORD
docker compose up -d db              # Postgres 17 + pgvector on 127.0.0.1:55432
docker compose run --rm migrate      # alembic upgrade head
```

The schema lives in `backend/migrations/` (Alembic). Revision `0001` is the JobPilot schema without Supabase auth, row-level security or grants; see the header of `backend/migrations/0001_baseline.sql`. New schema changes are new Alembic revisions:

```
cd backend && alembic revision -m "describe the change"
```

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
cd frontend  && npm test && npx tsc --noEmit
cd extension && npm test
```

CI runs the same checks on pushes to `main` and `jobdots` (`.github/workflows/release-checks.yml`).

## Frontend work

Load the project skills `frontend-design` and `jobdots-agentic-ui` (in `.claude/skills/`) before designing or building any screen.
