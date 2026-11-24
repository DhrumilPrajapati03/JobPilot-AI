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

Day 0 of the plan is done: secret scan, JobPilot snapshot, data export and removal of parts JobDots will not use. Until Day 1 and Day 2 land, the backend and frontend are still the JobPilot app (Supabase auth and database).

## The old JobPilot app

The complete JobPilot code is on branch `legacy/jobpilot-v1` (tag `jobpilot-v1-baseline`). To run it beside JobDots, check it out in a second folder:

```
git worktree add ../jobpilot-v1 legacy/jobpilot-v1
```

Copy `backend/.env` and `frontend/.env` into that folder, since git does not copy ignored files.

## Checks

```
cd backend   && python tests/run_offline.py      # backend, no .env loaded
cd frontend  && npm test && npx tsc --noEmit
cd extension && npm test
```

CI runs the same checks on pushes to `main` and `jobdots` (`.github/workflows/release-checks.yml`).

## Frontend work

Load the project skills `frontend-design` and `jobdots-agentic-ui` (in `.claude/skills/`) before designing or building any screen.
