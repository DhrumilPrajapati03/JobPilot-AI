# Deploying JobPilot on Render (free tier)

This puts the API and web app online so the nightly scan and morning digest run while
your laptop is off. About 30 minutes, once.

You need accounts on: **GitHub** (code), **Render** (hosting), **Supabase** (already set
up), **Resend** (digest email), and **cron-job.org** (wakes the server at night). All free.

---

## 1. Supabase

1. In the SQL editor, run every migration in `backend/supabase/migrations/` that you
   haven't yet, oldest first:
   `20261006_application_materials`, `20261010_answer_bank`, `20261010_cold_emails_rls`,
   `20261011_job_discovery`, `20261012_more_job_boards`, `20261013_referrals`,
   `20261014_autopilot`. They're all safe to re-run.
2. **Project Settings → API**: copy the **service_role** key. The server needs it to run
   the schedule and serve the extension. Keep it secret: it bypasses row-level security.
   It only ever goes into Render's environment, never into the web app.

## 2. Resend (morning digest)

1. Sign up at [resend.com](https://resend.com) **with the email address you want the
   digest sent to**. On the free plan, mail from `onboarding@resend.dev` can only go to
   that address, which is all a personal digest needs.
2. **API Keys → Create API key** (sending access). Copy it.

## 3. Push the code to GitHub

Render deploys from your GitHub repo (`DhrumilPrajapati03/JobPilot-AI`). Commit and push
the current work. Check that `backend/.env` isn't included (it's git-ignored).

Local `.env` files and the generated resume-search database are excluded from version
control. On Render, configure the frontend's Supabase URL and anon key through the
environment variables below; keep the service-role key and provider API keys on the API.

## 4. Render

1. **New → Blueprint**, pick the repo. Render reads `render.yaml` and creates
   `jobpilot-api` (Docker) and `jobpilot-web` (static site).
2. Fill in the values it asks for:

   | Service | Variable | Value |
   |---|---|---|
   | api | `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_JWT_SECRET` | same as `backend/.env` |
   | api | `SUPABASE_SERVICE_KEY` | from step 1 |
   | api | `GROQ_API_KEY` | same as `backend/.env` |
   | api | `RESEND_API_KEY` | from step 2 |
   | api | `FRONTEND_URL` | `https://jobpilot-web.onrender.com` (your web URL) |
   | web | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | same as `frontend/.env` |
   | web | `VITE_API_BASE_URL` | `https://jobpilot-api.onrender.com` (your API URL) |
   | web | `VITE_WS_BASE_URL` | `wss://jobpilot-api.onrender.com` |

   `CRON_SECRET` is generated for you; copy it from the API's **Environment** tab for step 6.
3. The exact URLs appear once the services exist. If they differ from the defaults, update
   `FRONTEND_URL` and the `VITE_*` values. Then redeploy the web app: `VITE_*` values are
   baked in at build time.
4. Check `https://<your-api>.onrender.com/health` returns `{"status":"healthy",...}`.

## 5. Supabase Auth URLs

**Authentication → URL Configuration**: set **Site URL** to your web URL and add it to
**Redirect URLs**, so sign-in returns to the deployed app rather than localhost.

## 6. Wake-up cron (cron-job.org)

Render's free web services sleep after 15 minutes without traffic, which stops the
in-process scheduler. A cron call wakes the server and runs the nightly schedule.

Create a job at [cron-job.org](https://cron-job.org):

- **URL:** `https://<your-api>.onrender.com/api/v1/autopilot/tick`
- **Method:** POST, with request header `X-Cron-Secret: <CRON_SECRET>`
- **Schedule:** every 10 minutes from about **3 hours before** your digest time to
  **1 hour after**. For a 7:00 digest in India, that's 04:00 to 08:00 IST.

Why only those hours: the free tier includes 750 instance hours a month. Keeping one
service awake all month uses almost exactly that, so a night window leaves plenty spare.
During the day the server wakes when you open the app; the first request takes about a
minute.

The scan runs two hours before your digest. Auto-drafts follow it, and the digest goes
out at your digest hour, waiting up to an hour for drafts still running.

## 7. In the app

1. Open the web app → **Settings**:
   - **Morning digest:** turn it on, pick the hour and your time zone, **Send me one now**
     to test it.
   - **Overnight schedule:** all three rows should be green.
2. **Profile → Preferences:** set target roles, and turn on **Auto-draft** if you want
   drafts ready each morning (default: up to 3 a night at 80%+ fit).
3. **Job feed:** follow companies and the remote boards.

## 8. Chrome extension

1. `chrome://extensions` → Developer mode → **Load unpacked** → the `extension` folder.
2. On the deployed web app, **Settings → Chrome extension → Connect extension**.
3. Each morning, open the **Apply queue** (or the links in the digest email) →
   **Open & fill** → check the amber fields → click the site's Submit → **I submitted it**
   in the JobPilot panel.

The extension talks to `localhost:8000` and `*.onrender.com`. For another host, add it
to `host_permissions` in `extension/manifest.json`.

---

## Good to know on the free tier

- **Cold starts:** a sleeping service takes about a minute to wake up.
- **Memory:** 512 MB. The local embedding model fits, but if Render reports
  out-of-memory restarts, set `EMBEDDINGS_PROVIDER=openai` (needs an OpenAI key).
- **Disk is temporary:** the resume search index (`data/chroma`) resets on each deploy.
  Tailoring still works, because the full base resume is always used. Re-save your base
  resume on the Profile page to rebuild the index.
- **PDFs:** the Docker image includes WeasyPrint's system libraries, so resume PDFs
  render on the server. The extension uploads them, which never worked on Windows.

## Test the image locally (optional)

With Docker Desktop running:

```sh
docker build -t jobpilot-api backend
docker run --env-file backend/.env -p 8000:8000 jobpilot-api
```
