# JobDots codebase triage

What happens to each part of the JobPilot code on the `jobdots` branch. The plan ([jobdots_final_plan.md](jobdots_final_plan.md), section 16) is the summary; this file is the detail and the record of what was removed and when. The evidence behind each call is in [CODEBASE_AUDIT_INPUT.md](CODEBASE_AUDIT_INPUT.md).

Nothing is lost: the full JobPilot code is on branch `legacy/jobpilot-v1` (tag `jobpilot-v1-baseline`, commit `801f703`), and the hosted data is exported to `D:\jobdots-archive\jobpilot-export-2026-11-24\`.

**Rule:** a part is removed on the day its replacement lands, so the suite stays green and the app keeps running in between. Only parts with no replacement and no dependants were removed on Day 0.

## Removed on Day 0 (25 Nov 2026)

| Removed | Why |
|---|---|
| Recommendation and ranking experiment: `app/recommendation/*`, `api/v1/recommendations.py`, run kind `recommendation`, `scripts/evaluate_recommendations.py`, `requirements-ml.txt`, `RERANKER_PATH`, frontend `RankingExperiment.tsx`, `RecommendationFeedback.tsx`, and their 8 test cases | Experiment for the SaaS; not in the JobDots plan. Its tables were in the never-applied migration. |
| Landing page: `pages/Landing.tsx`, `Landing.css`, `components/landing/LandingDemos.tsx`; `/` now redirects to the workspace | Single-user app; landing page is out of scope (plan section 13). |
| Frontend E2E specs `career-desk.spec.cjs`, `social-auth.spec.cjs` | They test the landing page and Supabase magic-link login, both going away; the suite was already recorded as stalled. `product-workflow.spec.cjs` is kept for reference. |
| Stray scripts: `backend/test_supabase.py`, `backend/test_vector_store.py`, `scripts/check_storage_access.py` | Manual scripts against live Supabase and Chroma, not part of the test suite. |
| Old SaaS docs at the repo root (sprint status files, roadmap, deploy, runbook, readiness, design, social-login setup) | Superseded by the plan. `DEPENDENCY_SECURITY.md` moved to `docs/`. |

## Removed later, with their replacement

| Part | Files | Replaced by | Day |
|---|---|---|---|
| Chroma vector store | `services/vector_store.py`, `chromadb` dependency, `MINILM_CACHE_PATH`, `CHROMA_PATH`, `scripts/prepare_models.py`, Dockerfile MiniLM step | pgvector answer bank, Ollama embeddings | 1 (Chroma advisory exception expires 7 Dec) |
| LangChain, Celery/Redis, LangSmith | `services/llm.py` (LangChain ModelChain), `celery`, `redis`, `langsmith` in requirements, `REDIS_URL`, old `docker-compose.yml` | OpenAI-compatible provider adapter (Groq, Ollama) keeping the ModelChain cooldown idea | 1 |
| Supabase data access | `services/supabase.py`, 197 `.table()` and 18 `.rpc()` calls, `supabase-py` | psycopg 3 / SQLAlchemy 2 on local Postgres | 1–2 |
| Supabase migrations, RLS, grants, `auth.users` foreign keys | `backend/supabase/**`, `scripts/database_bundle.py`, `scripts/check_database.py` | Alembic baseline with the queue and mail SQL functions ported, auth/RLS/grants stripped, `owner` default | 1 |
| Supabase JWT auth | `services/auth.py`, `api/v1/auth.py`, `SUPABASE_JWT_SECRET` | Owner bearer token (Day 1), then Google + GitHub login with allowlist (Day 2) | 1–2 |
| Supabase Storage (`resumes` bucket) | `services/uploads.py` storage calls, `api/v1/resume.py` upload path | Files on local disk (Phase A) | 2 |
| Frontend Supabase auth, magic link/OTP, account-switch guards | `lib/supabase.ts`, `stores/auth-store.ts`, `LoginForm.tsx`, `lib/account-context.ts`, `lib/auth-errors.ts`, `lib/auth-redirect.ts`, `tests/social-auth.test.mjs`, `tests/account-isolation.test.mjs`, `expectedUserId` in hooks | New login page (Google, GitHub), session cookie | 2 |
| One-running-job-per-user lock | `agent_run_locks` and the lock in `claim_agent_run` | Per-case and per-kind concurrency | 2 |
| Composio Gmail broker | `services/gmail_broker.py`, Composio parts of `services/mailbox.py`, `components/email/GmailConnection.tsx` | Direct Gmail executor in Courier (token broker) | 5 |
| Resend morning digest | `services/digest.py`, `RESEND_API_KEY` | Telegram daily digest | 5 / 16 |
| Production hardening tied to Supabase sessions | `services/production.py` checks, live session re-verify in `run_stream.py` and `websocket.py` | Startup validation for the new config; session checks for the new login | 2 |
| Usage limits (`services/usage.py`) and its tables | needs the unapplied migration | Plan budgets (`budget_ledger`, per-case caps) | 2 |
| Old UI ("career desk") pages and styles | `pages/*`, `styles/career-desk.css`, `components/layout/*`, `components/ui/brand.tsx`, `workflow-map.tsx`, `Overview.tsx` | Agentic UI (plan section 6; skills `frontend-design` and `jobdots-agentic-ui`) | 3–9, screen by screen |

## Kept (ported, not rewritten)

| Part | Files | Becomes |
|---|---|---|
| Durable queue | SQL functions `enqueue/claim/renew/checkpoint/append_event/finish/retry_agent_run`, `save_run_*`; `services/runs.py` (`RunStore`); `workflows/context.py` (`ExecutionContext`); `workers/runner.py` | Same design on psycopg; durability layer for every expert |
| Email approval state machine | `outreach_messages` states (draft → approved revision-pinned → queued → sending → sent / send_unknown / failed), `mail_send` worker logic | Generalised `action` state machine |
| Scout | `services/discovery.py`, `job_boards.py`, `job_filters.py`, `job_identity.py`, `job_matching.py`, `matching_semantics.py`, `eligibility.py`, autopilot nightly scan | Scout expert and its daily routine |
| Safe fetching and JD parsing | `services/safe_fetch.py`, `agents/jd_parser.py` | Tool registry (fetch) and Scout/Researcher input |
| Resume validator | `resume_engine/validator.py` | Seed of the Reviewer's fact checks |
| Resume engine | `resume_engine/*` (LaTeX template, Tectonic path, HTML fallback) | Tailor (master `.tex`, Tectonic in the image) |
| Identity and facts | `services/identity.py`, `identity_confirmations` | Fact vault seed |
| Answer bank | `qa_answers`, `services/form_answers.py`, `sensitive` flag | pgvector `answer_bank` |
| Company research | `services/company_research.py`, `agents/research.py` (cited fetcher) | Researcher (adds search and synthesis) |
| Recruiters and network | `services/recruiters.py` (Hunter), `referrals.py`, network CSV import | Recon and the contact CRM |
| Extension | `extension/**` (ATS form engine, policy, tests) | Applicant; Vite + TypeScript shell around the existing JS |
| Writers | `agents/cover_letter.py`, `email_writer.py`, `dm_writer.py`, `services/writing_evidence.py` | Email Outreach, DM Outreach prompts and grounding |
| Assistant | `agents/assistant.py` (tool loop with `propose_*` tools) | Supervisor |
| Matching evals | `backend/evaluations/matching_cases.json` (37 cases), `scripts/evaluate_matching.py` | Eval harness seed (Day 2) |
| Export script | `scripts/export_supabase.py` | One-off; final export before the Supabase project is deleted |
| Dependency gate | `scripts/check_audit.py`, `docs/DEPENDENCY_SECURITY.md` | CI gate (exceptions drop as Chroma is removed) |
