# JobPilot AI

An AI assistant for finding relevant jobs, preparing tailored application materials, and tracking your job search. JobPilot includes a web app, a FastAPI backend, and a Chrome extension that fills application forms for you to review and submit.

Sprint 2 adds opt-in durable Supabase runs and a separate worker. See [setup, architecture and verification](SPRINT_2_STATUS.md), and keep the deferred [production readiness work](PRODUCTION_READINESS.md) as a release gate.

Sprint 3 adds source-linked resume confirmations, structured eligibility, explainable semantic ranking, and conservative job deduplication. See [workflow, setup and evaluation results](SPRINT_3_STATUS.md).

## Features

- **Identity vault:** Store your profile, base resume, skills, work preferences, and reusable screening answers. Upload a resume or edit its structured content.
- **Job discovery:** Follow company boards on Greenhouse, Lever, Ashby, and SmartRecruiters, or search Himalayas and Remotive. Match jobs against your target roles and resume.
- **India eligibility filtering:** Show jobs with stated hiring eligibility in India, including explicitly worldwide remote roles. Hide jobs restricted to other countries or with unclear eligibility. A remote or APAC label alone does not qualify.
- **Application preparation:** Parse a job URL or pasted description, tailor your resume, calculate a keyword match score, and draft a cover letter, cold email sequence, and LinkedIn messages.
- **Resume review:** Edit tailored content, compare changes, inspect missing keywords, and export a PDF.
- **AI workspace:** Chat with an assistant that can retrieve your job-search data, propose changes, and start preparation flows. View generation progress as it happens.
- **Application tracking:** Manage statuses, notes, outreach drafts, and follow-up reminders. Review application analytics and recurring skill gaps.
- **Network and referrals:** Import LinkedIn connections, find contacts at target companies, and draft referral requests.
- **Supervised autopilot:** Scan boards, automatically prepare qualifying matches within a daily cap, and send a morning digest when configured.
- **Chrome autofill:** Fill contact details, tailored resumes, cover letters, and screening answers on application pages. Flag AI drafts and unanswered questions for review.

**You remain in control of submission.** The Chrome extension never clicks Submit. After submitting on the employer's site, mark the application as applied in JobPilot.

## How it works

1. Sign in through Supabase and complete your profile and base resume.
2. Follow job boards and set your preferred roles and work preferences.
3. Browse matching jobs or paste a job description directly.
4. The backend parses the description, tailors your resume, renders a PDF, generates outreach drafts, and saves the application.
5. Review the materials, open the employer's application form, and use JobPilot Autofill.
6. Submit the form yourself and track the outcome and follow-ups.

The React app calls the FastAPI API using a Supabase access token. Supabase stores profiles and application records; ChromaDB supports resume search. AI providers handle parsing and writing. Chat responses stream over HTTP, while application preparation reports progress over WebSockets.

## Technology

| Component | Stack |
| --- | --- |
| Web app | React 19, TypeScript, Vite, Tailwind CSS |
| Client state and data | Zustand, TanStack Query, React Router |
| API | Python, FastAPI, Pydantic |
| Authentication and database | Supabase Auth and PostgreSQL |
| AI | LangChain integrations for Groq, OpenAI, and Anthropic |
| Resume search | ChromaDB with local, Hugging Face, or OpenAI embeddings |
| PDF generation | Jinja2 templates, Tectonic/LaTeX, WeasyPrint fallback |
| Digest delivery | Resend |
| Hosting configuration | Docker and Render Blueprint |

## Project structure

```text
JobPilot AI/
├── backend/
│   ├── app/
│   │   ├── agents/             # Assistant and application-writing agents
│   │   ├── api/v1/             # API endpoints
│   │   ├── models/             # Request and data schemas
│   │   ├── resume_engine/      # Resume validation, templates, PDF rendering
│   │   └── services/           # Discovery, matching, autofill, scheduling
│   ├── supabase/migrations/    # Incremental database changes
│   ├── tests/                 # Backend regression tests
│   ├── .env.example
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/src/               # Web pages, components, hooks, and stores
├── extension/                  # Unpacked Chrome extension
├── DEPLOY.md                   # Render deployment walkthrough
└── render.yaml                 # API and static frontend services
```

## Local setup

Use Python 3.12, Node.js 20 or newer, a Supabase project, and an API key for at least one supported AI provider. The commands below use Windows PowerShell and start from the repository root.

### 1. Configure Supabase

For a fresh Supabase project, apply the SQL files in [backend/supabase/migrations](backend/supabase/migrations) in filename order, starting with `20261001_base_schema.sql`. The baseline creates the core tables, ownership policies, and private resume bucket before the incremental migrations. You can generate a single transactional SQL bundle with `python scripts/database_bundle.py --output supabase/bootstrap.generated.sql` from `backend`. See [Sprint 1 setup and acceptance checks](SPRINT_1_STATUS.md) before applying to an existing database; the baseline does not reconcile arbitrary schema drift or old permissive policies.

Apply the migration files in filename order through the Supabase SQL editor. Configure Supabase Auth's Site URL and allowed redirect URLs for `http://localhost:5173`.

### 2. Configure and install the backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If `backend/.env` already exists, edit that file instead of copying over it. Replace the placeholder values with your own configuration:

| Variable | Purpose |
| --- | --- |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon key |
| `GROQ_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY` | Configure at least one AI provider |
| `LLM_PROVIDER` | `auto`, `groq`, `openai`, or `anthropic` |
| `FRONTEND_URL` | Allowed frontend origin; locally `http://localhost:5173` |
| `DEBUG` | Boolean value: `true` or `false` |

Optional configuration:

| Variable | Purpose |
| --- | --- |
| `SUPABASE_JWT_SECRET` | Required for projects using legacy HS256 tokens; asymmetric tokens use Supabase JWKS |
| `SUPABASE_SERVICE_KEY` | Enables server scheduling and extension APIs; keep this key on the backend only |
| `DISCOVERY_AUTO_SCAN` | Enables the in-process scan/digest scheduler when the service key is configured |
| `RESEND_API_KEY`, `DIGEST_FROM` | Morning digest delivery |
| `CRON_SECRET` | Authenticates calls to `/api/v1/autopilot/tick` from an external scheduler |
| `EMBEDDINGS_PROVIDER` | `local` (default), `huggingface`, or `openai` |
| `HUGGINGFACE_API_KEY` | Required when using Hugging Face embeddings |
| `AGENT_PROVIDER`, `AGENT_MODEL` | Optional chat assistant provider and model overrides |

Provider model overrides and other settings are defined in [backend/app/config.py](backend/app/config.py). Local embeddings may download their model on first use; re-save your base resume after changing embedding providers.

### 3. Configure and install the frontend

From the repository root:

```powershell
cd frontend
npm.cmd ci
```

Create or edit `frontend/.env`:

```dotenv
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-supabase-anon-key
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
```

Use only the Supabase anon key in the frontend. Vite embeds `VITE_*` variables in the browser bundle; provider API keys and the service-role key belong in the backend environment.

## Start the app

Run these commands in two separate PowerShell terminals, starting from the repository root.

**Backend:**

```powershell
cd backend
$env:DEBUG="false"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

**Frontend:**

```powershell
cd frontend
npm.cmd run dev
```

- Web app: http://localhost:5173
- Interactive API documentation: http://localhost:8000/docs
- API health check: http://localhost:8000/health

The `DEBUG` override avoids startup errors if your shell defines a non-boolean value such as `release`. Using `npm.cmd` avoids PowerShell execution-policy errors from `npm.ps1`.

## Install JobPilot Autofill

1. Open `chrome://extensions` and enable **Developer mode**.
2. Choose **Load unpacked** and select the repository's `extension` folder.
3. In JobPilot, open **Settings → Chrome extension → Connect extension**.
4. Open an application form and click **Fill this page**, or use the floating fill button on supported sites.
5. Review highlighted fields and AI suggestions, submit manually, then select **I submitted it**.

The extension requires the backend service-role key to be configured. It uses a personal token that you can revoke in Settings. It fills forms on the current page; it does not navigate from a job description to the application form for you. See [extension/README.md](extension/README.md) for connection and hosting details.

## Checks

Backend tests, from `backend`:

```powershell
$env:DEBUG="false"
.\.venv\Scripts\python.exe -m pytest tests -q
```

Frontend production build, from `frontend`:

```powershell
npm.cmd run build
```

The latest local verification passed **192 backend tests**, four frontend account-isolation tests (`npm.cmd test`), four extension security tests (`node --test extension/tests/security.test.cjs` from the repository root), and the frontend production build. Tests use mocked services and do not establish that live AI, email, hosting, or database provisioning is configured correctly. See [Sprint 1 status](SPRINT_1_STATUS.md) for deployment changes and outstanding acceptance checks.

## Current limitations

- Template library management is placeholder UI.
- Recruiter enrichment and cold email sending/history endpoints are not implemented. Outreach drafts are available; morning digest delivery is a separate Resend integration.
- India eligibility is inferred conservatively from published locations and descriptions. Missing or inaccurate employer data can hide suitable roles or require additional review. The feed rule also applies to existing listings and automatic drafts; manually pasted jobs are a separate preparation flow.
- Server PDF export needs WeasyPrint's native libraries. Tectonic is optional; rendering falls back to HTML/WeasyPrint. If neither renderer is available, use the resume preview's browser export. The backend Docker image installs the native PDF dependencies.
- Scheduled scans need a running backend. Hosts that sleep need an external cron calling the protected tick endpoint.
- A fresh-project database baseline and SQL smoke test are included. Live provisioning and hosted RLS/storage acceptance checks still need to be run; see [Sprint 1 status](SPRINT_1_STATUS.md).

## Deployment

See [DEPLOY.md](DEPLOY.md) for the Render setup using [render.yaml](render.yaml), Supabase migrations, digest configuration, and external cron. Deployment configuration is included; successful production deployment has not been verified by the local build and test checks.
