# JobDots runbook

How to run JobDots day to day, and what to do when something goes wrong. Commands run from the repository root unless they say otherwise.

## Start and stop

| What | Command |
|---|---|
| Start everything (database, migrations, API, worker, Telegram) | `docker compose up -d` |
| Web app | `cd frontend && npm run dev`, then open http://localhost:5173 |
| Stop | `docker compose stop` |
| After pulling new code | `docker compose up -d --build` (migrations run on their own) |
| Logs | `docker compose logs -f api worker telegram` |

Check that everything works: open **Dashboard → Health**, or call `GET /api/v1/health/deep` while signed in. Each check says *OK*, *Check* or *Down* and what to do.

## Stop everything that sends: the kill switch

Set `kill_switch: true` in `config/policy.yaml`. Courier then refuses every email, LinkedIn queue item and calendar event, and the Dashboard shows "Kill switch on". Approvals already given wait; nothing is lost. Set it back to `false` to resume. The file is re-read on change, so no restart is needed.

## Connections

| Symptom | Fix |
|---|---|
| Health → Google: expired, or missing send, read or calendar | `cd backend && python scripts/connect_google.py connect`. Google's Testing mode ends the connection every 7 days, and Telegram warns you a day before. The Google Calendar API must be enabled in the same Google Cloud project. |
| Extension says the token was revoked | Web app → Settings → Connect extension. |
| No Telegram approvals or alerts | `cd backend && python scripts/connect_telegram.py`, then `docker compose up -d telegram`. |
| Recon or Comp Analyst: "search isn't configured" or "rate limit" | Check `BRAVE_API_KEY` in the root `.env`. Daily search caps are in `policy.yaml` (`recon_searches_per_day`, `comp_searches_per_day`). |
| Experts fail with "models are at their usage limit" | Groq's free tier has a daily token budget per model. The chain falls back to smaller models; wait for the reset or raise the plan. |

## Backups and restore

* Nightly at `BACKUP_HOUR` (02:00 local by default): an encrypted database dump goes to Google Drive when it's connected, otherwise to local disk. Health → Backups shows the last one.
* Back up now: `cd backend && python scripts/backup.py run`. List them: `python scripts/backup.py status`.
* Restore into a scratch database first, and check it there: `python scripts/backup.py restore FILE --into postgresql://…/scratch`.
* **Keep `BACKUP_ENCRYPTION_KEY`** (root `.env`) somewhere safe outside the laptop. Without it no backup can be restored.

## When an expert fails

1. **Dashboard → Live Ops → Failed in the last day** shows the expert, the case and the error in one line, with secrets removed. Telegram alerts you when an expert fails twice within an hour.
2. Fix the cause (a connection, a key, a quota), then use **Ask an expert again** on the case.
3. Runs that keep failing: `docker compose logs worker` shows the full error.
4. **End-to-end report**: `docker compose exec api python -m app.experts.e2e_report` writes `data/files/reports/e2e-*.md`. It lists every case, what each expert made, failures, model usage, and routing advice. Add `--run CASE_ID …` to have Supervisor carry those cases first.

## A send's result is unknown

"Send result unknown" means the worker stopped during a Gmail send. Look in Gmail's Sent folder before doing anything; JobDots never retries these on its own. If it went out, there's nothing more to do. If it didn't, ask Email Outreach for a new draft.

## Checks before changing code

`cd backend && python tests/run_offline.py tests --ignore=tests/integration -q` (unit tests), `python scripts/check_database.py` (migrations and integration tests on a throwaway Postgres), `python -m evals` (quality bars, including the red team), `cd frontend && npm run build`, `cd extension && npm test && npx playwright test`.

## Moving to Render (Phase B)

`render.yaml` describes the API, worker and Telegram services on Render with a managed Postgres that has pgvector. Before using it:
1. Create the database (Neon, or Render Postgres with `create extension vector`).
2. Fill in the secrets marked `sync: false` in the Render dashboard; they are never in the file.
3. Restore your latest backup into it.
4. Switch Google OAuth redirect URIs to the Render URL.

The laptop stack stays the source of truth until you switch.
