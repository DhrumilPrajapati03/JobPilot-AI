# JobPilot → JobDots: Codebase Audit (input for re-architecture)

Audit date: 24 Nov 2026. Repo HEAD: `eb8c6d0` (Sprint 6) on `main`, plus an uncommitted release candidate.
Target plan: [jobdots_final_plan.md](jobdots_final_plan.md) (v1.3).
Method: read-only. No code changes. No `.env` files were opened; no secret values appear here.
Tests were run locally with `.env` loading disabled (`tests/run_offline.py`) and Chroma pointed at a temp dir.

**Headline findings**

1. The **durable Postgres queue is real and good** (leases, fencing tokens, per-stage checkpoints, idempotency keys, retry backoff, recovery). It is implemented as **SQL functions called over Supabase PostgREST `.rpc()`**. The SQL ports to plain Postgres almost unchanged; the Python callers (`RunStore`) need a psycopg adapter.
2. The "8-stage pipeline" exists twice: an **inline** version (`agents/orchestrator.py`, WebSocket events) and a **durable LangGraph** version (`workflows/application.py`, 11 linear nodes). LangGraph is used only as a linear runner. It does not use a LangGraph checkpointer; checkpoints live in `agent_runs.checkpoints`.
3. **Every table is multi-user**: `user_id uuid references auth.users`, `default auth.uid()`, RLS policies, and grants to the Supabase `authenticated`/`service_role` roles. There are 197 `.table()` calls and 18 `.rpc()` calls through `supabase-py`. **No SQLAlchemy and no Alembic.**
4. **Gmail goes through Composio** (`services/gmail_broker.py`), not the direct Gmail API. The plan requires direct Gmail. The approval state machine for email (`draft → approved(revision pinned) → queued → sending → sent | send_unknown | failed`) is solid and maps well to the plan's `action` table.
5. **Chroma** (`chromadb==1.5.9`) holds resume-section embeddings and has 4 accepted advisories with a hard **7 Dec 2026** expiry in `scripts/check_audit.py`. **No pgvector anywhere.** The answer bank (`qa_answers`) uses Jaccard word overlap, not embeddings.
6. The **extension** is plain JS MV3 (not TS/Vite). It has no side panel and no LinkedIn features. It covers ATS form fill only, never auto-submits, and authenticates with its own hashed token.
7. **Tests:** backend 338/338 pass, frontend node 35/35, `tsc` clean, extension node 7/7. Frontend Playwright E2E was last recorded as **BLOCKED/stalled**. SQL tests need a live DB and were not run.
8. Pending changes: **159 paths (78 modified, 81 untracked)**, not 169. The difference is likely the gitignored `spike/composio_calendar/` and other ignored tool folders. **Root `data/chroma/chroma.sqlite3` is untracked and NOT gitignored** (only `backend/data/` is ignored), so a `git add -A` would commit an embedding DB.

---

## 1. Tree (2 levels) with lines of code

LOC = lines of `.py .ts .tsx .js .cjs .mjs .sql .css .j2 .html .md .json .yml` excluding `node_modules`, `dist`, `__pycache__`, `test-results`, lockfiles.

### backend/ (Python 3.11 locally, 3.12 in Docker)
| Path | Files | LOC | Notes |
|---|---|---|---|
| `app/agents/` | 10 | 1,608 | `assistant.py` 776 (chat agent + tools), `orchestrator.py` 311 (inline pipeline), `resume_tailor.py` 135, `jd_parser.py` 105, `email_writer.py` 100, `dm_writer.py` 70, `cover_letter.py` 53, `tracker.py` 28 (stub), `research.py` 25 |
| `app/api/v1/` | 20 | 2,866 | routers (see §2); largest: `applications.py` 441, `discovery.py` 302, `network.py` 271, `resume.py` 245, `extension.py` 224, `email.py` 206, `analytics.py` 206 |
| `app/config.py` | 1 | 103 | pydantic-settings |
| `app/main.py` | 1 | 124 | app, CORS, `/health`, WebSocket `/ws/agent-stream/{run_id}` |
| `app/models/` | 7 | 399 | Pydantic: `resume.py` 112, `application.py` 75, `user.py` 69 (incl. `WorkPreferences`), `template.py`, `email.py`, `contact.py` |
| `app/recommendation/` | 4 | 154 | **untracked**: reranker (`ranking.py` 84), feedback/snapshots (`service.py` 50), metrics (`evaluation.py` 19) |
| `app/resume_engine/` | 7 | 595 | `renderer.py` 131 (Tectonic→LaTeX, else WeasyPrint), `validator.py` 149, `builder.py` 53, `schemas.py` 52, templates `latex/standard.tex.j2` 85 + `html/standard.html.j2` 121 |
| `app/services/` | 37 | 5,061 | discovery 522, job_boards 416, form_answers 395, llm 370, referrals 322, autopilot 321, job_matching 237, mailbox 220, digest 206, application_execution 192, auth 186, vector_store 165, materials 146, runs 116, observability 107, gmail_broker 106, safe_fetch 89, … |
| `app/workers/` | 2 | 182 | `runner.py` 181 (durable worker) |
| `app/workflows/` | 3 | 217 | `application.py` 168 (LangGraph), `context.py` 48 (stage/checkpoint helper) |
| `supabase/migrations/` | 19 | 1,385 | see §3 |
| `supabase/tests/` | 7 | 540 | SQL contract tests (need a DB) |
| `supabase/bootstrap.generated.sql` | 1 | 481 | generated fresh-DB bootstrap (Oct 23; predates Sprint 2+) |
| `tests/` | 21 | 3,519 | pytest (see §9) |
| `scripts/` | 9 | 486 | `check_audit.py`, `check_database.py`, `check_worker_recovery.py`, `check_image.py`, `check_storage_access.py`, `prepare_models.py`, `evaluate_*`, `database_bundle.py` |
| `evaluations/` | 3 | 885 | matching cases + lexical/semantic reports (JSON) |
| `templates/resume/` | 1 | 0 | empty placeholder |
| `data/chroma/` | 5 | binary | local Chroma store (gitignored) |
| `test_supabase.py`, `test_vector_store.py` | 2 | 117 | ad-hoc scripts at backend root that hit live services; not part of the suite |
| `Dockerfile` 46, `docker-compose.yml` 37 (api + **redis**, legacy), `docker-compose.durable.yml` 19 (api + worker, hosted Supabase), `requirements.txt` 27, `requirements.lock` 166, `requirements-ml.txt` 5 | | | `backend/20` is a stray 1-line diagnostic file (gitignored) |

### frontend/ (React 19 + Vite 6 + Tailwind v4 alpha + TS)
| Path | Files | LOC | Notes |
|---|---|---|---|
| `src/pages/` | 16 | 4,472 | ApplicationDetail 608, JobFeed 581, Landing 141 + Landing.css 585, Profile 476, Applications 438, NewApplication 341, Settings 323, Network 262, Chat 249, ApplyQueue 186, Analytics 166, Overview 40, Login 38, Templates 21, `lazy.ts` |
| `src/components/` | 40 | 4,580 | `agent/` (ToolCards 600, Conversation 212, Briefing 179, Markdown 137, Workspace 129, RunActivity 14), `applications/` (OutreachPanels 295, ResumePreview 246, ResumeDiff 215, ReferralPanel 196, ResumeTab 174, …), `profile/` (AnswerBankPanel 266, PreferencesPanel 216, FactsPanel 60, OnboardingPanel 57), `email/` (MailOutreach 108, GmailConnection 42), `jobs/`, `layout/` (Sidebar 181, AppShell 123), `auth/LoginForm` 174, `ui/` (shadcn-style primitives) |
| `src/hooks/` | 11 | 1,420 | TanStack Query hooks per domain |
| `src/agent/` | 2 | 380 | chat SSE client + zustand store |
| `src/lib/` | 11 | 427 | `api.ts` 133 (fetch wrapper, Supabase session token), `supabase.ts`, `constants.ts`, `run-poll.ts`, `account-context.ts`, `auth-*` |
| `src/stores/` | 2 | 281 | `auth-store.ts` 204 (Supabase auth: magic link + Google/GitHub OAuth), `ui-store.ts` |
| `src/types/` | 1 | 242 | hand-written API types (no OpenAPI codegen) |
| `src/styles/`, `index.css` | 2 | 725 | |
| `tests/` | 7 | 477 | node:test unit tests |
| `e2e/` | 3 | 398 | Playwright specs |

### extension/ (Chrome MV3, plain JS)
| Path | LOC | Notes |
|---|---|---|
| `manifest.json` | 36 | see §7 |
| `background.js` | 162 | service worker: token storage, API proxy, PDF fetch, session/event relay |
| `content/form-engine.js` | 215 | field collection, value setting, combobox, file attach, audit |
| `content/fill.js` | 266 | in-page panel (shadow DOM), fill/save answers/report submitted |
| `content/connect.js` | 22 | token hand-off from the web app |
| `policy.js` | 20 | exact allowed app/API origins |
| `popup.html/js/css` | 104 | manual connect + "Fill this page" |
| `tests/` | 381 | `security.test.cjs` + Playwright browser fixtures |
| `scripts/check-live-forms.cjs` | 34 | |

### data/
| Path | Notes |
|---|---|
| `data/chroma/chroma.sqlite3` | **Untracked, not ignored.** A Chroma DB at repo root (probably created when the app ran from the repo root with the default `CHROMA_PATH=data/chroma`). Delete it or add it to `.gitignore` before committing. |

### docs/
| Path | Files | LOC | Notes |
|---|---|---|---|
| `docs/benchmarks/` | 30 | 9,989 | all **untracked**: `ARCHITECTURE_AUDIT.md`, `BENCHMARK_RESULTS.md`, `EVALUATION_PLAN.md`, harness scripts, `raw/` logs and JSON (9,471 LOC) from the 12 Nov audit |

Root also has 20+ status/plan markdown files (`SPRINT_1..6_STATUS.md`, `CURRENT_PRODUCT_AND_ROADMAP.md`, `DEPLOY.md`, `RELEASE_READINESS.md`, etc.), `render.yaml`, `.github/` (dependabot + `release-checks.yml`, both untracked) and `spike/composio_calendar/` (gitignored).

---

## 2. FastAPI routes (107 HTTP + 1 WS) and frontend callers

Auth column: **U** = Supabase JWT (`get_current_user`); **X** = extension token header `X-JobPilot-Token`; **C** = cron secret; **O** = ops token; **—** = public.
DB column: **JWT** = user-scoped Supabase client (RLS enforces ownership); **ADM** = service-role client + manual `user_id` filter.

### App-level (`app/main.py`, `api/v1/operations.py`)
| Method | Path | Auth | Purpose | Caller |
|---|---|---|---|---|
| GET | `/health` | — | liveness | Render / ops |
| GET | `/ready` | — | readiness (DB, worker heartbeat, release schema) | Render / ops |
| GET | `/ops/metrics` | O | request/worker metrics | ops only |
| WS | `/ws/agent-stream/{run_id}` | U (token in 1st frame) | live pipeline events (inline: in-memory manager; durable: polls `agent_run_events`) | `hooks/use-agent-stream.ts` → NewApplication, ToolCards (Chat, JobFeed) |

### `/api/v1/auth`
| POST | `/auth/login` | — | Supabase magic-link OTP | **unused** (frontend calls Supabase directly) |
|---|---|---|---|---|
| GET | `/auth/me` | U | current user info | **unused** |
| POST | `/auth/logout` | U | no-op acknowledgement | **unused** |

### `/api/v1/profile` (JWT)
| GET | `/profile/onboarding` | U | onboarding checklist status | Profile (OnboardingPanel) |
|---|---|---|---|---|
| GET | `/profile/facts` | U | identity vault: facts from base resume + confirmations | Profile (FactsPanel) |
| POST | `/profile/facts/confirm` | U | confirm facts (writes `identity_confirmations`) | Profile (FactsPanel) |
| DELETE | `/profile/facts/{fact_id}` | U | revoke a confirmation | Profile (FactsPanel) |
| GET | `/profile/` | U | profile + work preferences | Profile, Settings, ResumeTab |
| POST | `/profile/update` | U | update profile/preferences | Profile, Settings, PreferencesPanel |

### `/api/v1/resume` (JWT; Storage on upload)
| GET | `/resume/base` | U | base resume JSON | Chat, NewApplication, Overview, Profile, ResumeTab |
|---|---|---|---|---|
| POST | `/resume/base` | U | save base resume (+ re-embed in Chroma) | Profile |
| POST | `/resume/upload` | U | PDF/DOCX import → parse → save (+ Storage `resumes` bucket) | Profile (OnboardingPanel) |
| GET | `/resume/tailored/{application_id}` | U | latest tailored resume | (via application detail) |
| PUT | `/resume/tailored/{application_id}` | U | save edited tailored resume | ResumeTab, Chat ToolCards (resume-edit proposal) |
| GET | `/resume/tailored/{application_id}/pdf` | U | render PDF (Tectonic or WeasyPrint) | ApplicationDetail (download) |

### `/api/v1/applications` (JWT, some ADM)
| POST | `/applications/parse-jd` | U | JD parse only | **unused** |
|---|---|---|---|---|
| POST | `/applications/generate` | U | start pipeline (inline task or durable run) | NewApplication |
| GET | `/applications/` | U | list/filter | Applications, Chat |
| GET | `/applications/{id}` | U | detail with resume, emails, materials | ApplicationDetail |
| PATCH | `/applications/{id}` | U | edit fields (notes, cover letter, DM) | ApplicationDetail, OutreachPanels, ResearchPanel, ToolCards |
| PUT | `/applications/{id}/status` | U | status change | ApplicationDetail, Applications, ToolCards |
| PUT | `/applications/{id}/emails/{email_id}` | U | edit cold-email draft | OutreachPanels, ToolCards |
| DELETE | `/applications/{id}` | U | delete | ApplicationDetail |
| POST | `/applications/{id}/report-submission` | U | user reports they submitted | ApplyQueue |
| GET | `/applications/{id}/execution` | U | submission evidence timeline | ApplicationDetail (ExecutionEvidence) |

### `/api/v1/answers` (JWT)
| GET | `/answers/` | U | list answer bank | Profile (AnswerBankPanel) |
|---|---|---|---|---|
| PUT | `/answers/` | U | upsert by question text | Profile (AnswerBankPanel) |
| DELETE | `/answers/{id}` | U | delete | Profile (AnswerBankPanel) |

### `/api/v1/discovery` (JWT)
| GET | `/discovery/sources` | U | followed ATS boards | JobFeed |
|---|---|---|---|---|
| POST | `/discovery/sources` | U | follow board + scan | JobFeed |
| POST | `/discovery/sources/bulk` | U | follow several | JobFeed |
| PATCH | `/discovery/sources/{id}` | U | enable/disable | JobFeed |
| DELETE | `/discovery/sources/{id}` | U | unfollow | JobFeed |
| POST | `/discovery/scan` | U | scan now (inline or durable `scan` run) | JobFeed, AppShell (`useAutoScan`) |
| GET | `/discovery/postings?status=` | U | feed (new/skipped/dismissed/drafted) | JobFeed |
| GET | `/discovery/postings/{id}` | U | posting detail | (assistant tool) |
| PATCH | `/discovery/postings/{id}` | U | dismiss/restore | JobFeed |
| POST | `/discovery/postings/{id}/draft` | U | start pipeline for posting | JobFeed |
| GET | `/discovery/briefing` | U | morning briefing | Chat, JobFeed, Overview, Briefing |

### `/api/v1/recommendations` (ADM, **untracked**)
| GET | `/recommendations/status` | U | reranker availability | JobFeed (RankingExperiment) |
|---|---|---|---|---|
| GET | `/recommendations/feedback` | U | user's interested/not-relevant marks | JobFeed (RecommendationFeedback) |
| PUT | `/recommendations/feedback/{posting_id}` | U | set feedback | JobFeed |
| POST | `/recommendations/runs` | U | snapshot a ranked list | JobFeed |
| POST | `/recommendations/impressions` | U | record visible impression | JobFeed |
| POST | `/recommendations/experiment` | U | queue reranker run | JobFeed (RankingExperiment) |

### `/api/v1/research` (ADM, **untracked**)
| GET | `/research/{application_id}` | U | cited company research | ApplicationDetail (ResearchPanel) |
|---|---|---|---|---|
| POST | `/research/{application_id}` | U | queue `company_research` run (≤3 user URLs) | ResearchPanel |
| POST | `/research/{application_id}/cover-letter` | U | cover letter grounded in research | ResearchPanel |

### `/api/v1/templates` (JWT, **untracked**)
| GET | `/templates` | U | writing templates (email/dm/cover) | Templates |
|---|---|---|---|---|
| PUT | `/templates/{kind}` | U | save template | Templates |

### `/api/v1/email` (ADM; Composio Gmail)
| GET | `/email/connection` | U | Gmail connection status | Settings (GmailConnection), MailOutreach |
|---|---|---|---|---|
| POST | `/email/connection` | U | start Composio OAuth link | GmailConnection |
| POST | `/email/connection/complete` | U | verify the connected account | GmailConnection |
| DELETE | `/email/connection` | U | disconnect/revoke | GmailConnection |
| POST | `/email/messages` | U | create outreach draft (idempotency key) | ApplicationDetail (MailOutreach) |
| GET | `/email/history` | U | messages for application | MailOutreach |
| PATCH | `/email/messages/{id}` | U | edit draft (bumps revision, clears approval) | MailOutreach |
| POST | `/email/messages/{id}/approve` | U | approve a specific revision | MailOutreach |
| POST | `/email/messages/{id}/send` | U | queue `mail_send` run (needs durable + flags) | MailOutreach |
| POST | `/email/messages/{id}/cancel` | U | cancel | MailOutreach |
| POST | `/email/send` | U | **deprecated**, always 409 | none |
| POST | `/email/sync` | U | queue `mail_sync` (reply fetch) | GmailConnection, MailOutreach |
| GET | `/email/messages/{id}/attachment` | U | frozen attachment download | MailOutreach |
| GET | `/email/messages/{id}/replies` | U | replies with rule classification | MailOutreach |
| PATCH | `/email/replies/{id}` | U | mark reviewed / reclassify | MailOutreach |

### `/api/v1/contacts` (ADM; Hunter)
| POST | `/contacts/research` | U | Hunter domain search → verified `recruiter_leads` | MailOutreach |
|---|---|---|---|---|
| GET | `/contacts/find` | U | GET alias of research | **unused** |
| GET | `/contacts/?application_id=` | U | list recruiter leads | MailOutreach (`useRecruiterLeads`) |

### `/api/v1/network` (JWT)
| POST | `/network/import` | U | import LinkedIn `Connections.csv`/zip | Network |
|---|---|---|---|---|
| GET | `/network/contacts` | U | search contacts | Network |
| POST | `/network/contacts` | U | add manual contact | Network |
| PATCH | `/network/contacts/{id}` | U | edit | (none in UI) |
| DELETE | `/network/contacts/{id}` | U | delete | Network |
| GET | `/network/companies` | U | companies you know people at | Network |
| GET | `/network/referrals/{application_id}` | U | ranked contacts + requests | ApplicationDetail (ReferralPanel) |
| POST | `/network/referrals` | U | draft referral message (never sent) | ReferralPanel, ToolCards |
| PATCH | `/network/referrals/{id}` | U | status (sent/referred/declined/no_reply) | ReferralPanel |
| DELETE | `/network/referrals/{id}` | U | delete | (none in UI) |

### `/api/v1/autopilot` (JWT/ADM)
| GET | `/autopilot/status` | U | schedule + last runs | Settings |
|---|---|---|---|---|
| GET | `/autopilot/queue` | U | drafted apps + prepared answers | ApplyQueue |
| POST | `/autopilot/prepare/{id}` | U | re-prepare form answers | ApplyQueue |
| GET | `/autopilot/digest/preview` | U | digest preview | Settings |
| POST | `/autopilot/digest/send` | U | send digest now (Resend) | Settings |
| POST | `/autopilot/tick` | C | cron: daily scans/digests for **all users** | external cron |
| POST/GET/DELETE | `/autopilot/extension-tokens[/{id}]` | U | create/list/revoke extension tokens | Settings |

### `/api/v1/extension` (X; ADM)
| GET | `/extension/me` | X | who am I | extension popup |
|---|---|---|---|---|
| GET | `/extension/queue` | X | apply queue | extension |
| POST | `/extension/match` | X | match page URL → application | extension |
| POST | `/extension/fill` | X | answers for detected fields | extension fill.js |
| GET | `/extension/resume/{id}` | X | tailored PDF | extension background.js |
| POST | `/extension/sessions` | X | start execution session (frozen PDF) | extension |
| POST | `/extension/events` | X | append evidence event (idempotent) | extension |
| POST | `/extension/document` | X | session's frozen document | extension |
| POST | `/extension/applied` | X | user reports submitted → Applied + follow-up | extension |
| POST | `/extension/answers` | X | save typed answers to bank (default sensitive) | extension |

### `/api/v1/agent`, `/runs`, `/analytics`
| POST | `/agent/chat` | U | assistant chat, SSE stream, tool calls (proposals) | Chat (`src/agent/client.ts`) |
|---|---|---|---|---|
| GET | `/runs` | U | recent durable runs | Overview (RunActivity) |
| GET | `/runs/{id}` | U | run status/result | `lib/run-poll.ts` (many hooks) |
| GET | `/runs/{id}/events?after=` | U | replay events | WS fallback / polling |
| POST | `/runs/{id}/retry` | U | retry failed run | RunActivity, run-poll |
| GET | `/analytics/summary` | U | funnel stats | Analytics, Chat, Overview |
| GET | `/analytics/skill-gaps` | U | skills missing vs targets | Analytics |
| GET | `/analytics/outcomes` | U | product metrics RPC | Analytics (ProductMetrics) |

Frontend pages with **no** backend route of their own: Landing, Login (Supabase direct).

---

## 3. Database tables and migrations

All in `backend/supabase/migrations/` (Supabase SQL, no Alembic). **No pgvector extension and no vector columns.** Every table has RLS on, `user_id → auth.users(id)`.

### Migrations (applied status per `DATABASE_ROLLOUT_STATUS.md`, 30 Oct)
| File | What it does | Status on hosted `JobPilotAI` |
|---|---|---|
| `20261001_base_schema.sql` | user_profiles, resumes, job_applications, tailored_resumes, cold_emails; owner RLS; Storage bucket `resumes` + owner policy | applied (originally provisioned manually) |
| `20261006_application_materials.sql` | adds cover_letter, linkedin_dm, follow_up_at, applied_at, updated_at; `set_updated_at` trigger | applied |
| `20261010_answer_bank.sql` | `qa_answers` | applied |
| `20261010_cold_emails_rls.sql` | parent-ownership RLS on cold_emails | applied |
| `20261011_job_discovery.sql` | job_sources, job_postings | applied |
| `20261012_more_job_boards.sql` | widens `job_sources.ats` check | applied |
| `20261013_referrals.sql` | network_contacts, referral_requests | applied |
| `20261014_autopilot.sql` | `job_applications.prepared_form`, extension_tokens, autopilot_state | applied |
| `20261023_security_guards.sql` | restrictive owner guards on all tables; private resumes bucket | applied |
| `20261027055731_durable_execution.sql` | agent_runs, agent_run_events, agent_run_locks + 10 queue RPCs (§4) | applied 30 Oct as `20261030065929_…` |
| `20261027062316_durable_execution_indexes.sql` | index + service-role lock policy | applied |
| `20261027140016_matching_v2_identity_vault.sql` | identity_confirmations; job_postings.matching_details, dedupe_key | applied |
| `20261028043146_mailbox_security_preflight.sql` | function hardening, storage policy | applied (already present) |
| `20261028043147_gmail_outreach_workflow.sql` | mail_connections, outreach_messages, mail_replies, recruiter_leads; `mail_command`, `begin_mail_send`, `mail_worker_result` | applied |
| `20261028045823_mailbox_sender_guards.sql` | `outreach_messages.from_email`; tightened mail RPCs | applied |
| `20261028113722_application_execution_evidence.sql` | application_documents, application_execution_sessions, application_events + 2 RPCs | applied |
| `20261028115607_application_execution_indexes.sql` | index | applied |
| `20261029155926_product_validation_metrics.sql` | execution_workers + heartbeat/health/product-metrics RPCs | applied |
| **`20261107152821_release_recommendations_research.sql`** | **untracked, NOT applied to either hosted project.** Adds `agent_runs.kind` values `company_research`, `recommendation`; recommendation_runs/impressions/feedback; company_research; writing_templates; usage_windows/receipts; RPCs `reserve_release_usage`, `record_recommendation_impression`, `save_company_research`, `prune_release_telemetry`, `release_schema_ready`, `jobpilot_session_active` (reads `auth.sessions`) | **pending.** Code in the working tree (`/research`, `/recommendations`, `/templates`, `usage.reserve`, prod session check, `/ready`) depends on it. In prod mode `/ready` fails without it. |

Migration timestamps on the hosted DB differ from local filenames (MCP-assigned). Docs warn: do not `db push` blindly.

### Tables (row-level purpose)
| Table | One row = | JobDots mapping |
|---|---|---|
| `user_profiles` | the user's profile + `work_preferences` JSONB (skip rules, digest, auto-draft, location) | single settings row / config |
| `resumes` | a structured resume (`version='base'`): experience/skills/projects/education JSONB | source for fact vault; plan wants master `.tex` instead |
| `identity_confirmations` | user confirmed one fact (sha256 fact id) of a given resume digest | ≈ `fact.confirmed_at`; keep the concept |
| `job_applications` | one application: company, role, JD text/URL, `jd_analysis`, status, cover letter, LinkedIn DM, `prepared_form`, follow-up/applied dates | ≈ `job_case` |
| `tailored_resumes` | a versioned tailored resume JSON + keyword score for an application | ≈ `artifact(resume_version)` |
| `cold_emails` | one email in the 3-step sequence drafted by the pipeline (no recipient) | ≈ `artifact(draft)` |
| `qa_answers` | answer-bank entry: question, answer, category, `sensitive` flag | ≈ `answer_bank` (no embedding, no version, no provenance) |
| `job_sources` | a followed ATS board (greenhouse/lever/ashby/smartrecruiters/…) | Scout source |
| `job_postings` | a discovered posting with fit score, matched/missing skills, skip flags, status, `matching_details`, `dedupe_key` | Scout output / `job_case` stage Found |
| `network_contacts` | an imported LinkedIn connection or manual contact (dedupe by URL/email/name+company) | ≈ `contact` (no role_class/stage) |
| `referral_requests` | a drafted referral ask to one contact for one application, with status | ≈ outreach `action` for employees |
| `extension_tokens` | hashed personal token for the Chrome extension | keep (or replace with single bearer) |
| `autopilot_state` | per-user last scan/digest dates and errors | ≈ `routine` last-run state |
| `agent_runs` | one durable job: kind, inputs, checkpoints, result, status, lease, attempts, idempotency key | ≈ `run` (+ queue) |
| `agent_run_events` | one append-only progress event for a run (replay/stream) | ≈ `run_step` / activity stream |
| `agent_run_locks` | per-user mutex row (one running job per user) | drop or keep per-case |
| `mail_connections` | the user's Composio-linked Gmail account | ≈ `connection` (status only) |
| `outreach_messages` | one email action: recipient, subject, body, revision, approved_revision, state machine, provider ids | ≈ `action` + `approval` (the best existing match) |
| `mail_replies` | an observed reply with rule-based classification | Inbox agent output |
| `recruiter_leads` | a Hunter-verified HR email for an application | ≈ `contact` from Recon |
| `application_documents` | the frozen tailored PDF (base64 + sha256) used in a fill session | artifact file ref |
| `application_execution_sessions` | one extension fill session on a page (24 h expiry) | Applicant run |
| `application_events` | evidence: form_prepared / submission_attempted / confirmation_observed / user_reported_submitted (idempotent key) | `case_event` |
| `execution_workers` | worker heartbeat (Live Ops) | keep |
| `recommendation_runs` / `_impressions` / `_feedback` *(pending)* | ranked-list snapshot / impression / user relevance signal | Scout eval data; optional |
| `company_research` *(pending)* | ≤3 cited source excerpts for an application | ≈ `artifact(company_brief)` |
| `writing_templates` *(pending)* | user template per kind (email/dm/cover) | Outreach agent instructions |
| `usage_windows` / `usage_receipts` *(pending)* | rate-limit counter / idempotent reservation | ≈ `budget_ledger` |

Missing vs the plan: `case_event` (generic), `artifact` (generic), `fact` (as a table), `contact_touch`, `outreach_event`, `action`/`approval` (generic), `agent_spec`, `memory`, `routine`, `eval_result`, `backup_log`, `budget_ledger`, any vector column.

---

## 4. Durable queue / worker

**Where:** SQL in `supabase/migrations/20261027055731_durable_execution.sql` (+ later kind extensions). Python repository in [app/services/runs.py](../backend/app/services/runs.py) (`RunStore`). Stage helper in [app/workflows/context.py](../backend/app/workflows/context.py) (`ExecutionContext`). Worker in [app/workers/runner.py](../backend/app/workers/runner.py), started with `python -m app.workers.runner`. Mode switch: `EXECUTION_MODE=inline|durable` (default inline; production requires durable).

| Concern | Implementation |
|---|---|
| Enqueue | `enqueue_agent_run(user, kind, inputs, key, available_at, parent_id, parent_token)`. Inputs are whitelisted per kind in `INPUT_FIELDS` (application, scan, digest, mail_send, mail_sync, company_research, recommendation). Child runs require a live parent lease. Writes a `queued` event. Usage reservation for application/scan. |
| Idempotency | `unique(user_id, kind, idempotency_key)`. A replayed key returns the existing run; different inputs under the same key raise `idempotency_key_conflict` (→ HTTP 409). Side-effect RPCs are fenced: `save_run_application` returns the stored `database_saving` checkpoint on replay. Mail sends use `attempt_id` + provider ids + `send_unknown`; extension events use `unique(session_id, request_key)`; digest uses provider idempotency key `jobpilot-digest/{run_id}`. |
| Claim | `claim_agent_run(worker, lease_seconds)`: `FOR UPDATE SKIP LOCKED` over ready rows (queued/retry_wait due, or running with expired lease). **One running job per user** (partial unique index + `agent_run_locks`). New random `lease_token`, attempts+1. |
| Lease | default `RUN_LEASE_SECONDS=120` (30–1800). A heartbeat **thread** renews every lease/3 (`renew_agent_run`), so the lease survives blocking work. A failed renew sets `lost`; every checkpoint/emit/finish RPC checks `lease_token` + expiry and raises `lease_lost` (fencing). |
| Checkpoints | `checkpoint_agent_run(run, token, stage, value)` → `agent_runs.checkpoints[stage]`. `ExecutionContext.stage(name, …)` skips completed stages on resume and re-emits "Restored completed step". Crash cost = one stage. |
| Retries | Worker on exception: `PermanentRunError` or attempts ≥ max (default 3) → `failed`; else `retry_wait` with backoff `min(300, 15·2^(attempts-1))` s. Expired leases are re-claimed; at max attempts, claim marks the run failed. User retry: `retry_agent_run` (not for digests). Failed application runs release their posting back to `new`. |
| Events | `append_agent_run_event` → `agent_run_events` (bigint id = replay cursor). Streamed by WS `run_stream.py` (polls with the user JWT) or `GET /runs/{id}/events?after=`. |
| Scheduling | Worker loop: every `TICK_SECONDS=600` calls `autopilot.tick` (daily scan/digest per user timezone) and `mailbox.schedule_sync`; polls every `RUN_POLL_SECONDS=2`. Inline mode instead runs `autopilot.scheduler_loop` in the API process. There is **no catch-up-on-wake** concept beyond "a due scan for today is enqueued when the tick sees it." |
| Health | `heartbeat_execution_worker` every 15 s → `execution_workers`; `/ready` uses `get_execution_health`. |
| Coupling | All calls go through `supabase-py` with the **service-role** key (`client.rpc`, `client.table`). The SQL uses `security invoker`, `search_path=''`, grants to `service_role`, and FKs to `auth.users`. Porting means removing grants/RLS, re-pointing FKs, and replacing `RunStore.rpc` with psycopg `SELECT fn(...)`. Logic can stay in SQL. Recovery test: `scripts/check_worker_recovery.py`. |

Plan delta: the plan wants `run`/`run_step` and an `action` state machine. `agent_runs` covers `run`; `agent_run_events` + `checkpoints` cover `run_step`. Approvals do not "sleep" a run: approval is a separate HTTP call that enqueues a new `mail_send` run, which already matches "pending approvals persisted, not polled".

---

## 5. The pipeline and LangGraph

### 5a. Inline pipeline: [app/agents/orchestrator.py](../backend/app/agents/orchestrator.py) `run_agent_pipeline`
Runs as a FastAPI background task and emits events over the in-memory WebSocket manager. Uses the user-JWT Supabase client. The "8 stages":

| # | Step id | Does | LLM calls |
|---|---|---|---|
| 1 | `jd_parsing` | `JDParserAgent.parse`: fetch URL (safe_fetch + BS4) or use text → structured `JDAnalysis` | 1 (structured output) |
| 2 | `profile_loading` | load `user_profiles` + base `resumes`; evaluate skip rules | 0 |
| 3 | `resume_tailoring` | `ResumeTailorAgent.tailor`: Chroma RAG (top-5 JD skills × top-2 chunks) → structured rewrite → hallucination/keyword checks; fallback = base resume | 1 (+ local embeddings ×5 queries) |
| 4 | `pdf_rendering` | `build_render_content` → `render_resume_pdf` (Tectonic LaTeX if on PATH, else WeasyPrint HTML) → page count | 0 |
| 5 | `outreach_generation` | sequential: `CoverLetterAgent`, `EmailWriterAgent` (initial + 2 follow-ups, one call), `DMWriterAgent` (connection note + follow-up) | 3 |
| 6 | `database_saving` | insert application, tailored_resume, cold_emails (manual cleanup on failure) | 0 |
| 7 | `referral_check` | `NetworkIndex.find(company)` → rank → draft referral to best contact → upsert `referral_requests` | 0–1 (`task="light"`) |
| 8 | (post-complete) form prep | `autopilot.prepare_application_form`: fetch Greenhouse public form → rule/bank answers → AI drafts for open questions | 0–1 (`task="light"`, all open questions in one prompt) |

Total ≈ **5–7 LLM calls per application**.

### 5b. Durable LangGraph pipeline: [app/workflows/application.py](../backend/app/workflows/application.py) `run_application`
`StateGraph(GraphState)` where `GraphState = {run_id: str}`. **The graph state is a stub**; real state lives in `ctx.checkpoints`. 11 nodes in a straight line `START → … → END`, no branches, no LangGraph checkpointer, recompiled on every run:

`jd_parsing → profile_loading → resume_tailoring → pdf_rendering → cover_draft → email_drafts → dm_drafts → outreach_generation (fallback check, 0 LLM) → database_saving (RPC save_run_application) → referral_check (RPC save_run_referral) → form_preparation (save_run_prepared)`

LLM calls are the same as inline, with the three writers split into separate nodes. `ensure_auto_current()` re-validates auto-draft preconditions (vault complete, resume unchanged, prefs, eligibility) before and at persist.

### 5c. Other agents / graphs
- **Assistant** ([app/agents/assistant.py](../backend/app/agents/assistant.py)): a LangChain tool-calling loop (not LangGraph). `bind_tools(TOOL_SCHEMAS)` with about 20 tools: read tools (overview, applications, resume, skill gaps, prefs, answers, briefing, job feed, referrals) and action tools (create_application, scan_jobs, draft_job), plus **`propose_*` tools that return proposals the UI must confirm** (status change, email edit, cover letter, resume edit, referral request). This is the closest existing pattern to "agents propose, code executes".
- **Company research** (`services/company_research.py`, durable kind `company_research`): fetch ≤3 user-supplied public URLs → excerpts with digests. **0 LLM calls.** No web search.
- **Recommendation reranker** (`recommendation/ranking.py`): optional local CrossEncoder (`RERANKER_PATH`), manifest-verified. 0 hosted LLM calls.
- `agents/tracker.py`: stub. Stale `__pycache__/council.cpython-311.pyc` exists with no source.

### 5d. LLM layer: [app/services/llm.py](../backend/app/services/llm.py)
LangChain `ChatGroq` / `ChatOpenAI` / `ChatAnthropic`. Provider preference `anthropic → openai → groq` unless `LLM_PROVIDER` is set. On Groq there is a `ModelChain` across `GROQ_MODEL` (default `openai/gpt-oss-120b`), `GROQ_FALLBACK_MODELS` and `GROQ_LIGHT_MODEL` (for `task="light"`), with rate-limit cooldowns. **No Ollama provider. No per-agent model config.** Embeddings: Chroma's default MiniLM (local ONNX) or OpenAI / HF API.

---

## 6. Feature locations and coupling to Supabase auth / multi-user code

| Feature | Files | Coupling |
|---|---|---|
| **Fact vault** | [services/identity.py](../backend/app/services/identity.py) (facts are derived from the base resume JSON by hashing paths/values; `load_vault`), [api/v1/profile.py](../backend/app/api/v1/profile.py) `/facts*`, [resume_engine/validator.py](../backend/app/resume_engine/validator.py) (hallucination checks), `models/resume.py`, frontend `FactsPanel.tsx` | Facts are **not stored**; only confirmations are (`identity_confirmations`, user-JWT client, RLS `auth.uid()`). Confirmations reset when the resume changes (digest). Validation is against resume JSON, not a `.tex` master. Low coupling: replace `db.table()` calls (2) and the `user_id` filter. |
| **Matching / eligibility** | [services/job_matching.py](../backend/app/services/job_matching.py) (lexical fit, title match, location), [services/eligibility.py](../backend/app/services/eligibility.py) (seniority, years, sponsorship → eligible/review/ineligible with evidence), [services/job_filters.py](../backend/app/services/job_filters.py) (skip rules, India eligibility), [services/matching_semantics.py](../backend/app/services/matching_semantics.py) (local MiniLM similarity via Chroma's embedding fn), [services/discovery.py](../backend/app/services/discovery.py) (scan, score, store), [services/job_boards.py](../backend/app/services/job_boards.py) (Greenhouse, Lever, Ashby, SmartRecruiters, Himalayas, Remotive), [recommendation/](../backend/app/recommendation/) | Pure functions are DB-free and reusable (good for Scout). `discovery.py` has 24 `.table()` calls and takes a client param (user-JWT or admin). `autopilot.tick` iterates **all users** via the admin client. `WorkPreferences` lives in `user_profiles.work_preferences`. |
| **Gmail approval** | [api/v1/email.py](../backend/app/api/v1/email.py), [services/mailbox.py](../backend/app/services/mailbox.py) (MIME build, send/sync executors, rule-based reply classify), [services/gmail_broker.py](../backend/app/services/gmail_broker.py) (**Composio REST** `backend.composio.dev`, per-user connected account keyed by Supabase uid), SQL `mail_command` / `begin_mail_send` / `mail_worker_result`, frontend `MailOutreach.tsx`, `GmailConnection.tsx` | Service-role client + manual `owned()` checks. **Composio holds the Gmail token** ("no token custody"), which conflicts with the plan's direct Gmail + token broker. Flags `MAILBOX_ENABLED`, `MAIL_SEND_ENABLED`, `MAIL_SYNC_ENABLED` are all off by default; send requires durable mode. The state machine and approve-a-revision semantics are worth keeping; the broker must be rewritten against the Gmail API. |
| **Company research** | [agents/research.py](../backend/app/agents/research.py), [services/company_research.py](../backend/app/services/company_research.py), [services/safe_fetch.py](../backend/app/services/safe_fetch.py) (SSRF-guarded fetch), [api/v1/research.py](../backend/app/api/v1/research.py), `ResearchPanel.tsx`; recruiter lookup in [services/recruiters.py](../backend/app/services/recruiters.py) + [api/v1/contacts.py](../backend/app/api/v1/contacts.py) (Hunter) | Research = user-supplied URLs only, no search API, no LLM synthesis (the plan's Researcher needs both). Admin client + `owned()`. Depends on the **unapplied** migration. Recruiter research is Hunter `domain-search` with an org-name match guard and no guessed addresses (keep the pattern). |
| **Network page** | [api/v1/network.py](../backend/app/api/v1/network.py), [services/referrals.py](../backend/app/services/referrals.py) (LinkedIn CSV/zip import, company-key matching, rank, draft referral), `pages/Network.tsx`, `ReferralPanel.tsx` | User-JWT client (`_client(current_user)`), RLS. Contacts come from the user's own LinkedIn export (1,101 rows in hosted DB). No role_class or outreach stage. Easy to port. |

Cross-cutting multi-user code to remove or simplify: `CurrentUser` / `get_current_user` (252 refs), `user_id` (448 refs in `app/`), per-request `get_supabase_client(user_jwt=…)`, RLS in every migration, `agent_run_locks` per user, `autopilot.tick` all-users loop and `account_email` (`auth.admin.get_user_by_id`), `usage.reserve` per user, the `jobpilot_session_active` session check, frontend `account-context.ts` / `expectedUserId` account-switch guards and `tests/account-isolation.test.mjs`.

---

## 7. Extension

- **Manifest** (MV3, `minimum_chrome_version` 102, name "JobPilot Autofill" v1.1.0):
  - `permissions`: `storage`, `activeTab`, `scripting`
  - `host_permissions`: `http://localhost:8000/*`, `http://127.0.0.1:8000/*`, `https://jobpilot-api.onrender.com/*`
  - background service worker `background.js`; action popup `popup.html`
  - No `sidePanel`, `tabs`, `cookies`, `webNavigation`, LinkedIn/X/Reddit hosts.
- **Content scripts**
  1. ATS pages: `boards.greenhouse.io`, `job-boards(.eu).greenhouse.io`, `jobs(.eu).lever.co`, `jobs.ashbyhq.com`, `jobs.smartrecruiters.com` → `form-engine.js` + `fill.js` (`all_frames`, `document_idle`)
  2. Web app origins (`localhost:5173`, `127.0.0.1:5173`, `jobpilot-web.onrender.com`) → `policy.js` + `connect.js` (`document_start`)
- **What it does today:** receives a `jpx_` token from the web app (postMessage, exact-origin checked) or popup paste, and stores it in `chrome.storage.local` (trusted contexts only). On ATS pages it shows a "Fill this application" pill → matches page to an application (`/extension/match`), collects fields, gets answers (`/extension/fill`: profile/rules, answer bank, earlier AI drafts), fills text/select/radio/combobox, attaches the **frozen tailored PDF** (sha256 checked), outlines filled (green) vs needs-you (amber; EEO/legal never auto-filled), saves typed answers back (`/extension/answers`, default sensitive), records evidence events, and "Report that I submitted". **It never clicks Submit.** On other sites: popup "Fill this page" via `scripting`.
- **Gaps vs plan:** JD capture, side panel, answer badges (vault/reused/adapted/generated), LinkedIn send queue, TS/Vite build, `localhost` as a setting (origins are hard-coded in both `manifest.json` and `policy.js`).
- **Tests:** `tests/security.test.cjs` (7 node tests, pass); Playwright `tests/browser/*.spec.cjs` against local fixtures (15 pass recorded 12 Nov); `COMPATIBILITY.md` matrix.

---

## 8. Dependencies

### Python (`backend/requirements.txt`; release lock `requirements.lock` = 165 pinned distributions)
| Package | Used? | Note |
|---|---|---|
| fastapi, uvicorn[standard], pydantic, pydantic-settings, python-dotenv, httpx, python-multipart | yes | keep |
| **supabase** | yes (everywhere) | remove in JobDots |
| langchain, langchain-groq, langchain-openai, langchain-anthropic | yes (`llm.py`, assistant, writing_evidence) | plan prefers `openai` SDK against OpenAI-compatible endpoints |
| langgraph==1.2.6 | yes (one linear graph) | |
| **chromadb==1.5.9** | yes (`vector_store.py`, `llm.py`, `matching_semantics.py`, `prepare_models.py`) | **flagged**, see below; pulls `onnxruntime==1.27.0` |
| weasyprint | yes (renderer fallback, `pdf.py`) | needs Pango in image |
| python-docx, pypdf, jinja2, beautifulsoup4 | yes | |
| PyJWT[crypto] | yes (`auth.py`) | replaced python-jose (uncommitted change) |
| sentry-sdk[fastapi] | yes (optional, `observability.py`) | |
| tzdata | yes | |
| **celery[redis], redis** | **no imports** | dead; only `REDIS_URL` config + legacy `docker-compose.yml` |
| **langsmith** | **no imports** | dead (transitive via langchain anyway) |
| pytest, pytest-asyncio | test | should be dev-only |
| `requirements-ml.txt`: sentence-transformers 5.2.1, transformers 5.17.0 | optional reranker experiments | not in image; unlocked/unaudited |

Not present but needed by the plan: psycopg 3, SQLAlchemy 2, Alembic, pgvector, `openai` SDK, tenacity, google-api-python-client / google-auth-oauthlib, python-telegram-bot/aiogram, cryptography (Fernet), structlog, sse-starlette, Playwright (Python). **Tectonic is not installed in the Dockerfile**, so the server always falls back to WeasyPrint today.

### DEPENDENCY_SECURITY.md flags
- **chromadb 1.5.9**: 4 advisories with no upstream fix: `PYSEC-2026-311`, `PYSEC-2026-3814`, `PYSEC-2026-3815`, `PYSEC-2026-3813` (server collection endpoints / RBAC / model repo injection). Accepted as unreachable (in-process `PersistentClient` only). [scripts/check_audit.py](../backend/scripts/check_audit.py) **hard-fails after 7 Dec 2026**. The plan says to remove Chroma on Day 1; that also removes `onnxruntime` and the MiniLM model prep in the Dockerfile.
- python-jose and its `ecdsa` dependency removed in favour of PyJWT.
- npm audits (frontend, extension) were clean on 7 Nov.
- Optional ML deps are not locked or audited.

### Frontend (`frontend/package.json`)
deps: `@supabase/supabase-js ^2.43.4` (**auth only**), `@tanstack/react-query ^5`, `react`/`react-dom ^19`, `react-router-dom 7.18.5`, `zustand ^4.5`, `@radix-ui/react-slot`, `@radix-ui/react-tabs`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`.
devDeps: `vite ^6`, `@vitejs/plugin-react`, `tailwindcss` / `@tailwindcss/vite` **`^4.0.0-alpha.18`** (alpha range; resolve to a stable 4.x), `typescript ^5.5`, `@playwright/test 1.64.1`, `@types/*`.
No OpenAPI client generator. Types are hand-written in `src/types/index.ts`.

### Extension
`@playwright/test 1.64.1` (dev only). No runtime deps; no bundler.

---

## 9. Tests

| Suite | Location | Count | Result today (24 Nov, this audit) |
|---|---|---|---|
| Backend pytest (offline, mocked boundaries) | `backend/tests/` (20 files: application_execution, application_flow, assistant, autopilot, discovery, durable_execution, gmail_outreach, india_eligibility, matching_v2, model_chain, more_boards, phase1, pipeline_regressions, product_validation, referrals, release_features, release_security, resume_import, security_foundation) | 338 | **338 passed**, 3 warnings, 52.6 s (`.venv-release`, Python 3.11.9) |
| Frontend node:test | `frontend/tests/*.test.mjs` (7) | 35 | **35 passed** |
| Frontend type-check | `npx tsc --noEmit` | — | **clean** (exit 0) |
| Extension node:test | `extension/tests/security.test.cjs` | 7 | **7 passed** |
| Frontend Playwright E2E | `frontend/e2e/*.spec.cjs` (product-workflow, career-desk, social-auth) | — | not run. Last recorded (12 Nov) **BLOCKED**: stalled after 14 OK results, teardown suspected, root cause unknown |
| Extension Playwright | `extension/tests/browser/*.spec.cjs` | 15 | not run. Last recorded (12 Nov) **PASS** |
| SQL contract tests | `backend/supabase/tests/*.sql` (7) | — | not run (need Postgres). CI runs them via `scripts/check_database.py --worker-recovery` |
| Root ad-hoc scripts | `backend/test_supabase.py`, `backend/test_vector_store.py` | — | not run; they hit live services; not real tests |
| Matching eval | `backend/evaluations/`, `docs/benchmarks/raw/matching-*.json` | 37 synthetic cases | lexical P=1.0, R=0.857 (2 semantic-title misses); 0 real postings |

CI: `.github/workflows/release-checks.yml` (offline backend, frontend build + E2E, extension, pip-audit gate, DB migrations + worker recovery, Linux image). **It is untracked, so it has never run on GitHub.**

What is untested relative to the plan: nothing covers policy-engine/caps, prompt-injection red-team, per-agent evals, Courier blocking, or backups (none of these exist yet).

---

## 10. Supabase-specific code and swap difficulty (→ plain Postgres + bearer auth)

| Surface | Where | Swap effort |
|---|---|---|
| **Auth (backend)** | [services/auth.py](../backend/app/services/auth.py): JWKS/HS256 Supabase JWT verify, `aud=authenticated`, prod issuer + `jobpilot_session_active` (reads `auth.sessions`); `CurrentUser{id, token, email}` dependency on ~100 routes; [api/v1/auth.py](../backend/app/api/v1/auth.py) (OTP, unused); WS first-frame token; `/agent/chat` re-verifies every 5 s in prod | **Low–medium.** Replace `_verify_token` with a constant-time compare against `API_BEARER_TOKEN` and return a fixed `CurrentUser(id=OWNER_ID)`. Every route keeps working. Delete `api/v1/auth.py`. |
| **Auth (frontend)** | `lib/supabase.ts`, `stores/auth-store.ts` (magic link, Google/GitHub OAuth, legacy callback), `LoginForm.tsx`, `lib/auth-*.ts`, `lib/api.ts` and `agent/client.ts`, `use-agent-stream.ts`, `use-mailbox.ts` (`getSession()` for token), `account-context.ts` guards, `Landing.tsx` | **Low.** No direct DB access from the browser. Replace `getAuthToken()` with a stored bearer token and delete the login/landing/social-auth code and tests. |
| **Data access** | `supabase-py` PostgREST query builder: **197 `.table()` + 18 `.rpc()`** across 39 files; `select_all` paging; `client.postgrest.auth(user_jwt)` | **Medium–high (largest item).** Choose either (a) a thin PostgREST-like shim over psycopg as a stop-gap, or (b) SQLAlchemy 2 models + repositories per the plan. Hot spots: discovery 24, applications 16, network 16, autopilot 15, discovery API 11. |
| **RLS / roles / grants** | every migration: `enable row level security`, owner and restrictive policies using `auth.uid()`, grants to `anon`/`authenticated`/`service_role`, `default auth.uid()` on `user_id` | **Medium.** Single user means dropping RLS and grants. Every `user_id … references auth.users(id)` FK and `auth.uid()` default must change (to a local `owner` table or be dropped). Fresh Alembic baseline recommended over replaying 19 Supabase files. |
| **SQL functions (RPCs)** | 10 queue RPCs + 3 mail + 2 execution-evidence + 3 health/metrics + 6 release | **Low.** Plain plpgsql. Keep them and call them via psycopg; drop the `auth.*` references (`jobpilot_session_active`, grants on `auth.sessions`). |
| **Storage** | `resumes` bucket + storage.objects policies; one upload in [api/v1/resume.py:210](../backend/app/api/v1/resume.py#L210); frozen PDFs are already in Postgres (`application_documents.pdf_base64`) | **Low.** Write to a local volume or the `artifact` file ref. |
| **Admin API** | `autopilot.account_email` → `auth.admin.get_user_by_id`; `extension.py` uses it too | **Low.** Read the owner email from config. |
| **Service-role vs user client** | ADM (email, contacts, research, recommendations, extension, runs, worker) vs JWT (profile, resume, answers, network, discovery, templates, applications) | Collapses to one connection pool. Manual `owned()` checks become simple existence checks. |
| **Ops/docs** | `DATABASE_ROLLOUT_STATUS.md`, migration-history mismatch (MCP vs CLI timestamps), `scripts/check_database.py`, `check_storage_access.py`, `bootstrap.generated.sql` | Superseded by the Alembic baseline. Export hosted data (11 applications, 1,101 contacts, 23 answers, 74 postings, 1 resume) with a one-off script before cut-over. |

Overall: auth and storage are easy; the PostgREST query-builder calls are where most of the work sits. Multi-user code is spread out but mechanical, because one fixed owner id lets it stay in place first and be removed gradually.

---

## 11. Uncommitted work (159 paths: 78 modified, 81 untracked), grouped by feature

Overall modified diff: +1,221 / −599 lines. Everything below is **uncommitted on top of `eb8c6d0`** and forms the "release candidate" described in `CURRENT_PRODUCT_AND_ROADMAP.md` / `RELEASE_READINESS.md`. All of it passes the offline tests above.

| Feature group | Files | State / notes |
|---|---|---|
| **A. Recommendations & ranking experiment** | new `app/recommendation/*` (4), `api/v1/recommendations.py`, `scripts/evaluate_recommendations.py`, `requirements-ml.txt`; frontend `jobs/RankingExperiment.tsx`, `jobs/RecommendationFeedback.tsx`, `JobFeed.tsx` (+33/−9) | Complete code; needs the **unapplied** migration; reranker is optional/off (`RERANKER_PATH` empty). Low value for JobDots v1. |
| **B. Cited company research** | rewritten `agents/research.py` (stub → fetcher), new `services/company_research.py`, `api/v1/research.py`, `ResearchPanel.tsx`, runs kind `company_research` | Works offline-tested; needs migration. Partial Researcher (no search, no synthesis). |
| **C. Writing templates & grounded writing** | new `api/v1/templates.py`, `services/writing_evidence.py`; modified `cover_letter.py`, `email_writer.py`, `dm_writer.py`, `orchestrator.py`, `workflows/application.py`, `pages/Templates.tsx` (−90/+19) | Writers now take resume evidence + user templates. Needs `writing_templates` table (migration). |
| **D. Usage limits / budgets** | new `services/usage.py`; `runs.py` (reserve on enqueue), `api/v1/runs.py` (retry budget, `GET /runs`), `api/v1/agent.py` (chat limit, 120k-char cap), `config.py` (`USAGE_LIMITS_ENABLED`, `APPLICATION_DAILY_LIMIT`, `CHAT_DAILY_LIMIT`) | Needs `usage_windows/receipts` (migration). Rough precursor of plan budgets. |
| **E. Production hardening / auth security** | `services/auth.py` (+34: prod issuer + live session check), new `services/production.py` (startup validation), `main.py`, `operations.py`, `request_limits.py`, `run_stream.py` (re-verify), `websocket.py`, `requirements.txt` (jose → PyJWT), `requirements.lock`, `Dockerfile` (+18: uv, pinned digests, MiniLM prep, non-root), `.dockerignore`, `.env.example` (+12 keys, no values), `render.yaml` (+73: api/worker/web Standard plans, headers), `scripts/check_*.py`, `DEPENDENCY_SECURITY.md`, `tests/test_release_security.py` | Mostly Supabase-session specific and will be dropped or simplified. Keep the Dockerfile pinning, non-root user and startup validation ideas. |
| **F. Social login & account isolation (frontend)** | `stores/auth-store.ts` (+96), `LoginForm.tsx` (+93), `Login.tsx`, `use-auth.ts`, `lib/supabase.ts`, `lib/api.ts`, new `lib/account-context.ts`, `lib/auth-errors.ts`, `lib/auth-redirect.ts`, `SOCIAL_LOGIN_SETUP.md`, `tests/social-auth.test.mjs`, `tests/account-isolation.test.mjs`, `e2e/social-auth.spec.cjs`; hooks `use-answers/applications/network/profile` (`expectedUserId`) | **Not needed for JobDots** (single user, bearer token). Candidate to discard rather than commit. |
| **G. UI redesign ("career desk")** | `index.css` (+88/−59), new `styles/career-desk.css`, `AppShell.tsx`, `Sidebar.tsx`, new `pages/Overview.tsx`, `ui/brand.tsx`, `ui/workflow-map.tsx`, `agent/RunActivity.tsx`, `Landing.tsx/.css`, `App.tsx`, `lazy.ts`, `constants.ts`, `Chat.tsx`, `Conversation.tsx`, `ToolCards.tsx`, `ApplicationDetail.tsx`, `vite.config.ts` (+19), `package.json`/lock, `e2e/career-desk.spec.cjs`, `e2e/product-workflow.spec.cjs`, `DESIGN.md`, `DESIGN_RESEARCH.md`, `.superdesign/` (ignored) | Visual refresh. The plan reimplements the UI as Command center / Cases / Approvals / Experts, so treat this as reference only. E2E for it is the suite recorded as stalled. |
| **H. Resume import & LLM plumbing** | `models/resume.py` (`ResumeContent` split), `services/parser.py`, `api/v1/resume.py`, `resume_engine/renderer.py`, `validator.py`, `templates/html/standard.html.j2`, `services/llm.py` (+41: timeouts, structured-output helper), `vector_store.py` (+32: lock, LRU, configurable `CHROMA_PATH`), `matching_semantics.py`, `jd_parser.py`, `resume_tailor.py`, `assistant.py`, `form_answers.py`, `referrals.py`, `discovery.py`, `autopilot.py`, `workers/runner.py` (+8: new kinds), `tests/test_resume_import.py`, `tests/run_offline.py`, `tests/fixtures/browser_server.py`, `tests/test_security_foundation.py` | Small, useful fixes. The vector-store work is moot if Chroma is removed. |
| **I. Database release migration** | `supabase/migrations/20261107152821_release_recommendations_research.sql`, `supabase/tests/release_recommendations_research.sql` | **Unapplied** anywhere hosted. A, B, C, D, E depend on it. |
| **J. Benchmarks / audit artifacts** | `docs/benchmarks/**` (30 files incl. `raw/` logs) | Evidence from the 12 Nov audit; documentation only. |
| **K. Docs & CI** | modified `README.md`, `DEPLOY.md` (+87/−111), `OPERATIONS_RUNBOOK.md`, `PRODUCTION_READINESS.md`, `.gitignore`; new `CURRENT_PRODUCT_AND_ROADMAP.md`, `FINAL_IMPLEMENTATION_AND_PRODUCTION_PLAN.md`, `PRODUCTION_SETUP.md`, `RELEASE_READINESS.md`, `DATABASE_ROLLOUT_STATUS.md`, `.github/dependabot.yml`, `.github/workflows/release-checks.yml`, `jobdots_final_plan.md` | Docs describe the multi-user SaaS release and are largely superseded by the JobDots plan. CI workflow is worth keeping (adapted). |
| **L. Stray / risky** | `data/chroma/chroma.sqlite3` (untracked, **not ignored**), `backend/20` (ignored), `spike/composio_calendar/` (ignored; Calendar spike from plan §14), stale `__pycache__/council*.pyc` | Do not commit the Chroma DB. Gitignore `/data/`. |

**Suggested commit strategy before re-architecture** (Day 1 "commit release candidate"): commit groups C, E (Dockerfile/lock/PyJWT parts), H, I, J, K and the CI workflow as the frozen JobPilot baseline. Exclude `data/chroma/`. Optionally drop F and G as JobDots will not use them; keep them on a tag/branch if you want the history.

---

## Appendix: plan-to-codebase gap summary

| Plan element | Exists? | Closest existing piece |
|---|---|---|
| Durable queue, leases, checkpoints, idempotency | **Yes** | `agent_runs` + RPCs + `ExecutionContext` |
| Supervisor + expert agents with typed artifacts | No | linear LangGraph pipeline; assistant tool loop |
| `agent_spec` as data, custom agents | No | none |
| Policy engine / `policy.yaml` / risk tiers / kill switch | No | per-feature env flags (`MAIL_SEND_ENABLED`), assistant `propose_*` tools |
| Courier executors on frozen approved payloads | Partial | `outreach_messages` revision-pinned approval + `mail_send` worker (Composio) |
| Reviewer | No | `resume_engine/validator.py` (hallucination checks), fallback warnings |
| Fact vault | Partial | resume-derived facts + `identity_confirmations` |
| Master `.tex` + Tectonic + diff | Partial | Jinja LaTeX template + Tectonic path (not installed in image); `ResumeDiff.tsx` |
| Answer bank with pgvector, reuse/adapt/generate | Partial | `qa_answers` + Jaccard similarity + AI drafts; `sensitive` flag |
| Scout | **Yes (mostly)** | discovery + job_boards + matching + eligibility + nightly tick |
| Researcher | Partial | URL-only research, no search/LLM |
| Recon | Partial | Hunter recruiter leads; LinkedIn CSV network |
| Connector / DM Outreach / LinkedIn send queue | No | DM text drafted in pipeline; referral drafts |
| Inbox / acceptance watcher | Partial | `mail_sync` + rule-based reply classification (via Composio) |
| Applicant (extension fill) | **Yes** | extension + `/extension/*` + execution evidence |
| Comp Analyst, Interview Buddy | No | none |
| Telegram approvals | No | none (Resend digest email only) |
| Ollama / per-agent models | No | Groq model chain with light/quality tiers |
| Backups to Drive | No | none |
| Pipeline / Live Ops dashboards | Partial | Analytics page, Overview + RunActivity, `/ready`, `execution_workers` |
| Evals | Partial | matching eval harness, `docs/benchmarks` |
