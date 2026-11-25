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

Day 0 of the plan is done: secret scan, JobPilot snapshot, data export and removal of parts JobDots will not use. Day 1 is in progress: the backend runs on local Postgres + pgvector (Alembic baseline) with owner bearer-token auth; Supabase is no longer used. The frontend still expects the old Supabase login until the Day 2 login page.

## Local stack

Needs Docker Desktop and Python 3.12 (`uv python install 3.12`).

```
cp .env.example .env                 # set POSTGRES_PASSWORD, OWNER_EMAIL, OWNER_API_TOKEN
docker compose up -d                 # db -> migrate (alembic upgrade head) -> api + worker
curl -H "Authorization: Bearer $OWNER_API_TOKEN" http://127.0.0.1:8000/api/v1/auth/me
```

Postgres 17 + pgvector listens on 127.0.0.1:55432 and the API on 127.0.0.1:8000; nothing is exposed beyond the laptop. JobDots has one user, the owner: the API accepts `Authorization: Bearer <OWNER_API_TOKEN>` (Google and GitHub login come next). Provider keys such as `GROQ_API_KEY` are read from `backend/.env` when it exists.

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
