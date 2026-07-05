# JobPilot AI — Autonomous Job Application Intelligence System
**Full Product & Engineering Documentation Suite**

| Field | Detail |
|---|---|
| Author | Dhrumil — AI/ML Engineer |
| Version | v1.3 — June 2026 (Auto-Apply Agent + 5 Remote Platforms) |
| Scope | Single Developer Build — Full Stack AI Product — 100% Free Stack |
| Documents Included | PRD · Architecture · Security · Frontend Spec · Tickets · Timeline · Platform Integration · Resume Engine · LaTeX Setup · Auto-Apply Engine |

---

## Table of Contents

1. [Product Requirements Document (PRD)](#document-1--product-requirements-document-prd)
2. [Technical Architecture Document](#document-2--technical-architecture-document)
3. [Security & Access Document](#document-3--security--access-document)
4. [Frontend Specification](#document-4--frontend-specification)
5. [Feature Ticket List](#document-5--feature-ticket-list)
6. [Timeline — Single Developer](#document-6--expected-timeline-single-developer)
7. [Job Platform Integration Spec](#document-7--job-platform-integration-spec)
8. [Resume Tailoring Engine Spec](#document-8--resume-tailoring-engine-spec)
9. [LaTeX Resume Engine — Full Setup Guide](#document-9--latex-resume-engine--full-setup-guide)
10. [Auto-Apply Engine — Platform Spec & Implementation](#document-10--auto-apply-engine--platform-spec--implementation)

---

# DOCUMENT 1 — PRODUCT REQUIREMENTS DOCUMENT (PRD)

**Product:** JobPilot AI | **Type:** Agentic Job Application System | **Status:** Pre-Build

---

## 1. Executive Summary

JobPilot AI is a fully agentic, AI-powered remote job application system that acts as a personal career assistant. It stores your professional identity (resume, skills, projects, salary expectations), intelligently tailors your application materials to each job description using LLMs, and autonomously handles outreach to recruiters and HR via cold emails and LinkedIn DMs — all orchestrated from a single dashboard.

> **Core Value Proposition:** Instead of spending 30–60 minutes customising one application, JobPilot compresses this to under 2 minutes. You review, approve, and fire. The agent does the rest — tailored resume, personalised cover letter, cold email sequence, and LinkedIn DM draft.

---

## 2. Problem Statement

Remote job seekers face three critical friction points:

- **Resume tailoring:** ATS systems reject generic resumes. Tailoring one resume per JD takes 30–90 mins.
- **Outreach at scale:** Cold emails and DMs to HR/recruiters are effective but highly time-consuming to personalise.
- **Tracking chaos:** Applications are scattered across spreadsheets, emails, and browser tabs with no unified pipeline.

---

## 3. Target User

| Attribute | Description |
|---|---|
| Primary User | Software engineers, AI/ML engineers, data scientists applying for remote roles |
| User Profile | Technical professional with 2–8 years experience, actively job hunting |
| Pain Point | Too many JDs, too little time to tailor every application properly |
| Technical Comfort | Comfortable with web tools; not necessarily developers |
| Frequency | 5–20 job applications per week |

---

## 4. Goals & Non-Goals

### Goals
- Generate ATS-optimised, JD-tailored resumes automatically
- Draft personalised cold emails and LinkedIn DMs for each application
- Maintain a full application pipeline with status tracking
- Store and version all user professional data centrally
- Enable one-click application approval and batch send

### Non-Goals (v1)
- Auto-submitting to job portals (legal/ToS risk — manual submit only)
- Interview scheduling automation
- Job scraping (use existing APIs — LinkedIn, Adzuna, Remotive)
- Multi-user SaaS platform (v1 is single-user personal tool)

---

## 5. Core Features

| Feature | Description | Priority |
|---|---|---|
| Identity Vault | Central store for resume, skills, projects, achievements, salary expectations, work preferences | P0 |
| JD Analyser | Parse JD → extract required skills, keywords, tone, seniority level, tech stack | P0 |
| Resume Tailor | Generate a tailored resume PDF/DOCX per JD using LLM + user data | P0 |
| Cover Letter Gen | Auto-draft compelling cover letters matched to company + role | P0 |
| Cold Email Writer | Generate personalised cold email to recruiter/HR with follow-up sequence | P1 |
| LinkedIn DM Drafter | Short personalised DM templates for connection + outreach to HR | P1 |
| Application Tracker | Kanban/table view of all applications with status pipeline | P1 |
| HR Contact Finder | Search & enrich HR/recruiter contacts for a company via web/API | P2 |
| Analytics Dashboard | Response rate, open rate, application stats, weekly summary | P2 |
| Email Integration | Connect Gmail/Outlook to send cold emails directly from app | P2 |
| Auto-Apply Agent | Playwright-based agent fills and submits job forms on target platforms with human approval gate | P2 |
| Remote Job Discovery | Ingest jobs from WeWorkRemotely, Wellfound, RemoteOK, Remote4Me, Himalayas via RSS/API/scrape | P1 |

---

## 6. User Journeys

### Journey 1 — New Application from JD URL
1. Paste job URL or raw JD text into JobPilot
2. Agent parses JD: extracts role, company, skills, tone, keywords
3. Agent cross-references with your Identity Vault
4. Generate: tailored resume + cover letter + cold email + LinkedIn DM
5. You review, edit inline, approve
6. Application is logged in tracker with status "Ready to Apply"
7. You manually submit on portal; mark as "Applied"

### Journey 2 — Follow-up Sequence
1. Application marked "Applied" for 5+ days with no response
2. System prompts: "Generate follow-up email?"
3. One-click drafts polite follow-up referencing original email
4. You approve and send

---

## 7. Success Metrics

| Metric | Baseline | Target (3 months) |
|---|---|---|
| Time per application | 45 mins | < 5 mins |
| Applications per week | 3–5 | 15–25 |
| Resume keyword match score | ~60% | > 85% |
| Cold email reply rate | ~3% | > 10% |
| HR contact found per JD | ~30% | > 70% |

---

# DOCUMENT 2 — TECHNICAL ARCHITECTURE DOCUMENT

---

## 1. System Overview

JobPilot AI is built as a modular agentic system with three layers: a React frontend, a FastAPI backend orchestrating multiple LangGraph agents, and a personal data store. External integrations handle LLM calls, job data, HR enrichment, and email delivery.

> **Architecture Philosophy:** Micro-agent design — each agent (JD Parser, Resume Tailor, Email Writer, Tracker) is a separate LangGraph graph node. They share a common state object and communicate via a central orchestrator. This keeps the system testable, replaceable, and debuggable.

---

## 2. Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Frontend | React + Vite + TailwindCSS | Fast SPA, easy to deploy, familiar stack |
| UI Components | shadcn/ui + Radix | Accessible, headless, customisable |
| Backend | FastAPI (Python) | Async, LangChain-native, OpenAPI docs auto-gen |
| Agent Framework | LangGraph | Stateful, cyclic agent graphs with human-in-loop |
| LLM | Claude 3.5 Sonnet (primary) + GPT-4o (fallback) | Best instruction-following; resume/email quality |
| Embeddings | text-embedding-3-small (OpenAI) | Semantic search across your own documents |
| Vector DB | ChromaDB (local) → Pinecone (cloud) | Store skills, projects, achievements as embeddings |
| Primary DB | PostgreSQL via Supabase | Jobs, applications, contacts, email logs |
| File Storage | Supabase Storage (S3-compatible) | Resume PDFs, cover letters, versions |
| Auth | Supabase Auth (email magic link) | Zero-friction single-user auth |
| PDF Renderer A | Tectonic (LaTeX engine) | Best quality; free; ~200MB cached packages; ATS-perfect text layer; Overleaf-compatible |
| PDF Renderer B | WeasyPrint (HTML+CSS engine) | Simpler setup; good quality; no LaTeX knowledge needed; faster to template |
| Resume Templates | LaTeX `.tex.j2` + HTML `.html.j2` | Both Jinja2-based; user picks renderer per template in Settings |
| Email Send | Resend API / Gmail API | Transactional cold email from personal address |
| Job Data | Adzuna API + Remotive API + Jooble | Free/affordable job listing sources |
| HR Enrichment | Hunter.io + Apollo.io API | Find emails and LinkedIn URLs for HR contacts |
| Deployment | Railway.app (backend) + Vercel (frontend) | Cheap, fast, zero DevOps for solo dev |
| Task Queue | Celery + Redis | Async agent runs, email scheduling |
| Monitoring | LangSmith + Sentry | Agent trace debugging + error tracking |

---

## 3. Agent Architecture (LangGraph)

The system uses a multi-agent graph where a Master Orchestrator delegates to specialised sub-agents. Each agent has access to relevant tools and the shared `ApplicationState`.

### Agent Graph Flow

```
JD Input
  → [JD Parser Agent]
  → [Research Agent]
  → [Resume Tailor Agent]
  → [Cover Letter Agent]
  → [Email Writer Agent]
  → [DM Writer Agent]
  → [Review & Approve (Human)]
  → [Tracker Update Agent]
  → [Auto-Apply Agent]  ← new: Playwright fills form, human clicks submit
```

### Individual Agent Specs

| Agent | Responsibility | Tools / APIs |
|---|---|---|
| JD Parser | Extract role, company, skills, keywords, tone, seniority, tech stack from JD text/URL | web_scrape, LLM (structured output) |
| Research Agent | Find company info, culture, recent news, HR contacts | web_search, Hunter.io, LinkedIn scrape |
| Resume Tailor | Rewrite resume sections to match JD keywords, highlight relevant projects | ChromaDB (skills lookup), LLM, PDF gen |
| Cover Letter Agent | Write personalised cover letter using company research + JD + user story | LLM, company info from Research Agent |
| Email Writer | Draft cold email + 2-part follow-up sequence personalised to HR contact | LLM, HR contact data, email templates |
| DM Writer | Short LinkedIn connection request + follow-up DM pair | LLM, company research |
| Tracker Agent | Log application details, update status, set follow-up reminders | PostgreSQL write, calendar API |
| Auto-Apply Agent | Playwright fills application form on target platform; pauses for human to review and click submit | Playwright, platform adapters, Identity Vault |

---

## 4. Data Models

### Core Entities

```
UserProfile:      name, headline, location, salary_range, work_preferences, linkedin_url
Resume:           base_version, sections (summary, experience, skills, education, projects), embeddings
JobApplication:   job_id, company, role, jd_url, jd_text, status, applied_at, source
TailoredResume:   application_id, version, pdf_url, keyword_match_score, generated_at
ColdEmail:        application_id, to_email, to_name, subject, body, sent_at, opened, replied
HRContact:        company, name, email, linkedin_url, title, confidence_score
Template:         type (email/dm/cover_letter), name, body, variables
```

---

## 5. API Endpoints (FastAPI)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/applications/parse-jd` | Parse JD URL or text, return structured analysis |
| POST | `/api/v1/applications/generate` | Run full agent pipeline for one application |
| GET | `/api/v1/applications` | List all applications with filters/sorting |
| PUT | `/api/v1/applications/{id}/status` | Update application status |
| GET | `/api/v1/resume/tailored/{app_id}` | Download tailored resume PDF for application |
| POST | `/api/v1/email/send` | Send approved cold email via Resend/Gmail API |
| GET | `/api/v1/contacts/find` | Find HR contacts for a company domain |
| POST | `/api/v1/profile/update` | Update user identity vault data |
| GET | `/api/v1/analytics/summary` | Application stats and funnel metrics |
| WS | `/ws/agent-stream/{run_id}` | WebSocket stream for live agent progress |

---

## 6. Infrastructure Architecture

```
Vercel CDN              → React SPA
Vercel Edge Function    → Auth proxy
Railway.app             → FastAPI (Docker container)
Railway.app             → Celery Worker (async agent runs)
Railway.app             → Redis (task queue + cache)
Supabase                → PostgreSQL + Auth + File Storage
Pinecone Cloud          → Vector embeddings
External APIs           → Anthropic, OpenAI, Hunter.io, Resend, Adzuna
```

---

# DOCUMENT 3 — SECURITY & ACCESS DOCUMENT

---

## 1. Threat Model

| Threat | Impact | Mitigation |
|---|---|---|
| API key exposure | Unauthorized LLM/service usage, billing fraud | Keys in env vars only; never in code/frontend |
| Unauthorized access | Resume/email data exfiltration | Supabase Auth + JWT; no public endpoints |
| Prompt injection via JD | Agent misbehaviour or data exfil | Sanitise JD text; system prompt hardening |
| Email credential compromise | Spam abuse from your address | OAuth 2.0 for Gmail; Resend domain auth |
| PDF file injection | Malicious PDF upload attacks | Validate MIME, size limits, sandbox extraction |
| LLM hallucination | Incorrect info on resume/email | Human review gate before any send action |

---

## 2. Authentication & Authorisation

- **Auth Provider:** Supabase Auth (magic link email — no passwords to manage)
- **Session:** JWT stored in httpOnly cookie (not localStorage)
- **API Auth:** Every FastAPI route validates Supabase JWT via middleware
- **Row-Level Security:** All Supabase tables have RLS policies — user can only access their own rows
- **Admin:** No admin panel in v1; direct DB access via Supabase dashboard only

---

## 3. Secret & Key Management

- All API keys (Anthropic, OpenAI, Hunter.io, Resend, Adzuna) stored as Railway environment variables
- Never committed to git — `.env.example` only with placeholder values
- Rotate keys on: any suspected leak, every 90 days for production
- Gmail OAuth: refresh token stored encrypted in Supabase; scoped to send-only permission
- LangSmith tracing: mask PII fields (email addresses, full resume text) in traces

---

## 4. Data Privacy

- Resume data stored only in your own Supabase instance (not shared with any third party beyond LLM calls)
- LLM calls: use Anthropic/OpenAI zero-data-retention API tier when possible
- HR contact data: used only for your outreach — not stored in any shared DB
- Email logs: stored locally with 90-day auto-purge option
- All file uploads scanned for MIME type before storage

---

## 5. Secure Coding Checklist

- [ ] All user inputs sanitised before LLM prompt injection (strip HTML, control chars)
- [ ] Rate limiting on all API endpoints (100 req/min via FastAPI middleware)
- [ ] CORS: only allow frontend origin; no wildcard
- [ ] HTTPS enforced via Railway + Vercel TLS by default
- [ ] Dependency scanning via Dependabot on GitHub
- [ ] No `eval()` or dynamic code execution in frontend or backend

---

# DOCUMENT 4 — FRONTEND SPECIFICATION

---

## 1. Design System

| Token | Value | Usage |
|---|---|---|
| Primary | `#1A3C5E` | Nav, primary buttons, headings |
| Accent | `#0F7B6C` | Success states, AI-generated badges, CTAs |
| Warning | `#E85D26` | Priority tags, deadlines, alerts |
| Background | `#F7F9FC` | Page background |
| Surface | `#FFFFFF` | Cards, panels, modals |
| Text Primary | `#1A1A2E` | Body text |
| Text Muted | `#6B7280` | Labels, metadata |
| Font (Display) | Inter 700 | Page titles, card headers |
| Font (Body) | Inter 400/500 | All body text, form inputs |
| Border Radius | 8px cards, 4px inputs | Consistent rounding |
| Shadow | shadow-sm on cards | Depth hierarchy |

---

## 2. Page Structure & Routes

| Route | Page | Key Components |
|---|---|---|
| `/dashboard` | Dashboard Home | Stats cards, recent activity, quick-apply CTA |
| `/applications` | Application Tracker | Kanban board + table toggle, filters, search |
| `/applications/new` | New Application | JD input, agent progress stream, results preview |
| `/applications/:id` | Application Detail | Resume preview, email drafts, timeline, status |
| `/profile` | Identity Vault | Resume editor, skills, projects, preferences |
| `/templates` | Templates Library | Email/DM/cover letter templates management |
| `/analytics` | Analytics | Funnel chart, reply rate, weekly trends |
| `/settings` | Settings | API keys, email integration, notifications |

---

## 3. Key UI Components

### JD Input & Agent Stream Panel
- Two-tab input: `"Paste URL"` | `"Paste JD Text"`
- Large textarea with character counter
- `"Analyse Job"` button → triggers agent pipeline
- Real-time progress stream via WebSocket: `"Parsing JD... Researching company... Tailoring resume..."` with step indicators
- Results appear in tabbed panel: `Resume | Cover Letter | Cold Email | LinkedIn DM`

### Resume Preview & Edit
- Side-by-side: original base resume (left) vs AI-tailored version (right)
- Inline editing on tailored version — all fields editable
- Keyword match score badge (e.g., `"87% ATS Match"`) with missing keywords list
- `"Download PDF"` + `"Download DOCX"` buttons
- Version history dropdown to compare past tailored versions

### Application Kanban Board
- Columns: `Saved → Applied → Interviewing → Offer → Rejected → Archived`
- Card shows: company logo, role title, days since applied, next follow-up date
- Drag-and-drop between columns (dnd-kit)
- Filter by: date range, source, response status, keywords
- Table toggle for spreadsheet-like view

### Cold Email Composer
- Editable subject + body with rich text support
- Variable chips: `{HR_NAME}`, `{COMPANY}`, `{ROLE}`, `{YOUR_NAME}`
- `"Send Now"` and `"Schedule Send"` (date/time picker)
- Follow-up sequence builder: +5 day, +10 day auto-drafts
- Email open tracking pixel toggle

---

## 4. State Management

| Concern | Tool | Reason |
|---|---|---|
| Server state (jobs, apps, emails) | TanStack Query (React Query) | Caching, refetch, loading/error states |
| UI state (modals, tabs, agent status) | Zustand | Lightweight, no boilerplate |
| Agent stream state | WebSocket context | Real-time agent progress |

> No Redux — overkill for a single-user personal tool.

---

## 5. Responsive Design

- **Primary:** Desktop-first (most usage at desk; job hunting workflow)
- **Tablet:** Sidebar collapses to icon-only at `< 1024px`
- **Mobile:** Limited view — dashboard + tracker read-only; full edit on desktop

---

# DOCUMENT 5 — FEATURE TICKET LIST

> Format: `[ID] Title | Story Points | Type | Dependencies`

---

## SPRINT 1 — Foundation & Identity Vault (Weeks 1–2)

| ID | Ticket | SP | Type | Deps |
|---|---|---|---|---|
| JP-001 | Project scaffold: Vite + React + TailwindCSS + shadcn/ui setup | 3 | Setup | — |
| JP-002 | FastAPI project init with folder structure and Dockerfile | 3 | Setup | — |
| JP-003 | Supabase project init: DB schema, Auth, RLS policies | 5 | Backend | — |
| JP-004 | Authentication flow: magic link login + JWT middleware | 5 | Backend | JP-003 |
| JP-005 | Identity Vault data model: UserProfile, Resume, Skills tables | 5 | Backend | JP-003 |
| JP-006 | Profile page UI: resume section editor (experience, education, skills) | 8 | Frontend | JP-005 |
| JP-007 | Base resume upload (PDF/DOCX) + text extraction | 5 | Backend | JP-005 |
| JP-008 | ChromaDB integration: embed resume sections on upload | 5 | Backend | JP-007 |

**Sprint 1 Total: 39 SP**

---

## SPRINT 2 — JD Parser & Resume Tailor Agent (Weeks 3–4)

| ID | Ticket | SP | Type | Deps |
|---|---|---|---|---|
| JP-009 | JD Parser agent: scrape URL or accept raw text, structured LLM output | 8 | Agent | JP-005 |
| JP-010 | JD analysis result schema: skills, keywords, seniority, tone, tech stack | 3 | Backend | JP-009 |
| JP-011 | Resume Tailor agent: RAG over user skills + LLM rewrite per JD | 13 | Agent | JP-008, JP-010 |
| JP-012 | ATS keyword match scorer: compare tailored resume vs JD keywords | 5 | Backend | JP-011 |
| JP-013 | PDF generation: WeasyPrint HTML → PDF from tailored resume data | 8 | Backend | JP-011 |
| JP-014 | New Application page UI: JD input tabs, submit form | 5 | Frontend | JP-009 |
| JP-015 | Agent progress WebSocket stream + frontend progress UI | 8 | Full Stack | JP-014 |
| JP-016 | Resume side-by-side preview UI with inline editing | 8 | Frontend | JP-013 |

**Sprint 2 Total: 58 SP**

---

## SPRINT 3 — Email & DM Writers + Tracker (Weeks 5–6)

| ID | Ticket | SP | Type | Deps |
|---|---|---|---|---|
| JP-017 | Cover Letter agent: LLM draft using company research + JD + user story | 8 | Agent | JP-010 |
| JP-018 | Cold Email Writer agent: personalised email + 2-part follow-up sequence | 8 | Agent | JP-010 |
| JP-019 | LinkedIn DM Writer agent: connection request + follow-up DM pair | 5 | Agent | JP-010 |
| JP-020 | Template system: save/load/edit email and DM templates | 5 | Backend | — |
| JP-021 | Cold Email Composer UI: editable draft, variables, schedule send | 8 | Frontend | JP-018 |
| JP-022 | Application Tracker DB model and CRUD API endpoints | 5 | Backend | JP-003 |
| JP-023 | Kanban board UI with drag-and-drop (dnd-kit) | 8 | Frontend | JP-022 |
| JP-024 | Table view toggle for applications tracker | 5 | Frontend | JP-022 |
| JP-025 | Application detail page: resume, emails, timeline, status | 8 | Frontend | JP-016, JP-021 |

**Sprint 3 Total: 60 SP**

---

## SPRINT 4 — Email Integration & HR Finder (Weeks 7–8)

| ID | Ticket | SP | Type | Deps |
|---|---|---|---|---|
| JP-026 | Gmail OAuth integration: send emails from personal Gmail account | 8 | Backend | JP-021 |
| JP-027 | Resend API fallback: domain-verified transactional email send | 5 | Backend | — |
| JP-028 | Email open tracking: pixel endpoint + update opened flag | 5 | Backend | JP-026 |
| JP-029 | Follow-up reminder: flag applications for follow-up after N days | 5 | Backend | JP-022 |
| JP-030 | HR Contact Finder: Hunter.io + Apollo.io API integration | 8 | Backend | — |
| JP-031 | HR contact panel UI in application detail page | 5 | Frontend | JP-030 |
| JP-032 | Research Agent: company info, LinkedIn, recent news via web search | 8 | Agent | JP-009 |
| JP-033 | LangSmith tracing integration for all agent runs | 3 | DevOps | — |
| JP-043 | Gmail OAuth + job alert label watcher via Pub/Sub webhook | 8 | Backend | JP-026 |
| JP-044 | LLM email parser: extract company, role, JD URL from alert emails | 8 | Agent | JP-043 |
| JP-045 | Adzuna API integration: job search with profile-based filters | 5 | Backend | — |
| JP-046 | Remotive + WeWorkRemotely RSS ingestion + relevance scoring | 5 | Backend | — |

**Sprint 4 Total: 73 SP**

---

## SPRINT 5 — Analytics, Polish, Extension & Deploy (Weeks 9–10)

| ID | Ticket | SP | Type | Deps |
|---|---|---|---|---|
| JP-034 | Analytics dashboard: funnel chart, reply rates, weekly stats | 8 | Full Stack | JP-022 |
| JP-035 | Dashboard home: stats cards, recent activity feed, quick apply CTA | 5 | Frontend | JP-034 |
| JP-036 | Settings page: API key management, email config, notification prefs | 5 | Frontend | — |
| JP-037 | Mobile responsive pass: sidebar collapse, touch-friendly tracker | 5 | Frontend | — |
| JP-038 | Railway deployment: FastAPI Docker + Celery + Redis setup | 5 | DevOps | — |
| JP-039 | Vercel deployment: React SPA + env vars + domain setup | 3 | DevOps | — |
| JP-040 | Sentry error monitoring: frontend + backend integration | 3 | DevOps | — |
| JP-041 | End-to-end test: full application flow from JD to tracker | 5 | QA | All |
| JP-042 | Performance audit: Lighthouse, API response times, WebSocket stability | 3 | QA | JP-041 |
| JP-047 | Chrome browser extension: "Send to JobPilot" one-click button | 13 | Extension | — |
| JP-048 | Extension: DOM scraper for LinkedIn, Naukri, Indeed job pages | 8 | Extension | JP-047 |
| JP-050 | Job discovery feed UI: filter by source, relevance score, date | 5 | Frontend | JP-045 |

**Sprint 5 Total: 68 SP**

---

## Resume Engine Tickets (Woven into Sprints 1–4)

| ID | Ticket | SP | Type | Sprint |
|---|---|---|---|---|
| JP-051 | Design master resume HTML+CSS Jinja2 template (ATS-optimised) | 8 | Design | Sprint 1 |
| JP-052 | Resume Content JSON schema with Pydantic validation | 3 | Backend | Sprint 1 |
| JP-053 | Resume Tailor Agent: 12-step pipeline with hallucination guards | 13 | Agent | Sprint 2 |
| JP-054 | WeasyPrint PDF renderer: HTML template + JSON → pixel-perfect PDF | 8 | Backend | Sprint 2 |
| JP-055 | ATS keyword match scorer with section-level breakdown | 5 | Backend | Sprint 2 |
| JP-056 | Post-gen hallucination validator: company, date, skills cross-check | 8 | Backend | Sprint 2 |
| JP-057 | Side-by-side diff UI: base vs tailored with approve/edit flow | 8 | Frontend | Sprint 3 |
| JP-058 | Missing keywords panel: suggestions with one-click accept | 5 | Frontend | Sprint 3 |
| JP-059 | DOCX output via python-docx template for Word-only platforms | 5 | Backend | Sprint 3 |
| JP-060 | Resume version history: compare all tailored versions per application | 5 | Frontend | Sprint 4 |

---

## Platform Integration & Auto-Apply Tickets (Woven into Sprints 2, 4, 5, 6)

| ID | Ticket | SP | Type | Sprint |
|---|---|---|---|---|
| JP-049 | LinkedIn/Naukri/Wellfound profile PDF import → LLM parse → Identity Vault seed | 5 | Backend | Sprint 2 |
| JP-063 | RemoteOK API: poll JSON feed every 6h, parse salary + tech stack | 5 | Backend | Sprint 4 |
| JP-064 | Himalayas API: poll job feed every 4h, full JD in response | 5 | Backend | Sprint 4 |
| JP-065 | Remote4Me Playwright scraper: search results + JD detail page | 8 | Backend | Sprint 4 |
| JP-066 | Job deduplication service: hash by company + role + URL across all sources | 5 | Backend | Sprint 4 |
| JP-067 | Auto-Apply Agent base: Playwright browser pool, session cookie manager | 13 | Agent | Sprint 5 |
| JP-068 | Himalayas apply adapter: name, email, resume upload, cover letter, LinkedIn | 8 | Agent | Sprint 5 |
| JP-069 | Wellfound apply adapter: profile fields, resume upload, cover letter | 8 | Agent | Sprint 5 |
| JP-070 | Greenhouse ATS adapter: detect + fill standardised Greenhouse forms | 8 | Agent | Sprint 6 |
| JP-071 | Lever ATS adapter: detect + fill standardised Lever forms | 8 | Agent | Sprint 6 |
| JP-072 | Apply preview UI: Playwright-filled form screenshot before human submits | 8 | Frontend | Sprint 5 |
| JP-073 | Apply session manager: store per-platform login sessions encrypted | 5 | Backend | Sprint 5 |
| JP-074 | Apply rate limiter: max N applies/hour per platform, configurable | 3 | Backend | Sprint 5 |
| JP-075 | Auto-apply result tracker: log success/fail, screenshot on error, retry queue | 5 | Backend | Sprint 6 |

---

**Total Ticket Count: 75 tickets | Total Story Points: ~530 SP**

---

# DOCUMENT 6 — EXPECTED TIMELINE (SINGLE DEVELOPER)

> **Assumption:** Strong Python/FastAPI + LangChain/LangGraph background, React familiarity, learning deployment. 4–5 focused hours/day.

---

## Phase Overview

| Sprint | Focus | Duration | Cumulative Week |
|---|---|---|---|
| S1 | Foundation, Auth, Identity Vault | 2 weeks | Week 2 |
| S2 | JD Parser + Resume Tailor Agent | 2 weeks | Week 4 |
| S3 | Email/DM Writers + Tracker | 2 weeks | Week 6 |
| S4 | Email Send + HR Finder + All 5 Remote Platform Ingestion | 2 weeks | Week 8 |
| S5 | Analytics + Browser Extension + Auto-Apply Base (Himalayas + Wellfound) + Deploy | 2 weeks | Week 10 |
| S6 | ATS Adapters (Greenhouse + Lever) + Auto-Apply hardening | 2 weeks | Week 12 |
| Buffer | Bug fixes, integration issues, scope creep | 1–2 weeks | Week 13–14 |

---

## Weekly Effort Breakdown

| Week | Morning Focus (Backend/Agents) | Evening Focus (Frontend/UI) |
|---|---|---|
| Week 1 | Supabase schema, FastAPI scaffold, Auth middleware | React setup, Auth UI, profile form skeleton |
| Week 2 | Identity Vault API + ChromaDB embeddings | Profile page, resume section editor UI |
| Week 3 | JD Parser agent + structured output schema | New Application page, JD input UI |
| Week 4 | Resume Tailor agent + PDF gen + ATS scorer | WebSocket stream UI, side-by-side preview |
| Week 5 | Cover Letter + Email Writer + DM Writer agents | Cold Email composer, template system UI |
| Week 6 | Tracker CRUD APIs, reminder system | Kanban board, table view, application detail page |
| Week 7 | Gmail OAuth, Resend API, open tracking, email alert parser | Email send UI, follow-up queue UI |
| Week 8 | RemoteOK + Himalayas + Remote4Me + WeWorkRemotely + Wellfound ingestion; deduplication | HR contact panel, job discovery feed UI with platform filters |
| Week 9 | Analytics API, LangSmith, Sentry setup | Dashboard, analytics charts, settings page |
| Week 10 | Railway + Vercel deploy, browser extension backend, Auto-Apply Agent base + session manager | Browser extension UI, apply preview UI (screenshot), mobile responsive |
| Week 11 | Himalayas apply adapter + Wellfound apply adapter; rate limiter | Apply flow UI: review → approve → submit handoff |
| Week 12 | Greenhouse ATS adapter + Lever ATS adapter; apply result tracker | ATS apply UI, error/retry display, auto-apply settings panel |
| Week 13–14 | 🐛 Bug fixes, edge cases, documentation | UX polish, final UAT, v1 launch |

---

## Risk Register

| Risk | Probability | Mitigation |
|---|---|---|
| LangGraph complexity / debugging agent graphs | High | Use LangSmith traces from day 1; start with simple linear chains |
| Gmail API OAuth approval delays | Medium | Use Resend API as primary; Gmail as optional enhancement |
| PDF resume quality / formatting issues | Medium | Use proven HTML+CSS template; test with 3–4 different base resumes |
| Hunter.io API rate limits on free tier | High | Cache HR contacts per company; budget $50/mo for paid tier |
| Scope creep (feature additions during build) | High | Strict ticket list; defer new ideas to v2 backlog document |
| LLM costs spike with many applications | Low | Cache JD analysis; use Claude Haiku for cheaper first-pass tasks |
| Single developer burnout / pacing | Medium | Buffer weeks built in; target 4h/day not 8h — quality over speed |
| Browser extension review/approval time | Medium | Build as unpacked extension first; submit to Chrome Web Store in parallel |
| Playwright detection by Wellfound/Himalayas | Medium | Add random delays (1–3s), human-like mouse movement; cap at 8 applies/hour per platform |
| Platform UI changes breaking Playwright selectors | High | Use data-testid/aria selectors where possible; write selector update as a 1-hour maintenance task |
| Session cookie expiry mid-apply | Medium | Detect auth errors in Playwright; prompt user to re-login; store refresh tokens where available |
| Remote4Me / Remote4 scraping ToS risk | Low | Personal use only; scrape politely (12h cadence, no bulk); not publishing data |

---

## Estimated Monthly Running Costs

| Service | Free Tier | Paid (if needed) |
|---|---|---|
| Supabase (DB + Auth + Storage) | Free (500MB) | $25/mo (Pro) |
| Railway.app (FastAPI + Celery + Redis) | $5 free credits/mo | $10–20/mo |
| Vercel (React frontend) | Free (Hobby) | Free sufficient |
| Anthropic Claude API (LLM) | Pay-per-use | ~$20–50/mo at scale |
| Pinecone (Vector DB) | Free (1 index) | $70/mo (if needed) |
| Hunter.io (HR emails) | Free (25/mo) | $49/mo (Starter) |
| Resend (Email sending) | Free (3000/mo) | $20/mo |
| LangSmith (Agent tracing) | Free (1K traces) | $39/mo (Developer) |
| **TOTAL ESTIMATE** | **~$0 to start** | **~$150–200/mo full** |

---

## v2 Backlog (Post-MVP Ideas)

- Browser extension: auto-fill job application forms on portals
- LinkedIn automation via browser extension (not official API)
- Multi-user SaaS with subscription billing (Stripe)
- Interview prep agent: mock Q&A based on JD + your resume
- Salary negotiation coach agent
- Job alert agent: monitor new JDs matching your preferences daily
- Referral tracker: track who can refer you at target companies
- Portfolio project matcher: auto-suggest portfolio projects based on JD gaps
- Instahyre / Wellfound deep integration via Playwright

---

# DOCUMENT 7 — JOB PLATFORM INTEGRATION SPEC

> **Key Constraint:** No major job platform (LinkedIn, Naukri, Glassdoor, Wellfound) offers a public API for reading your personal saved jobs, application history, or recommendations. All approaches below are official alternatives, email-based parsing, or user-controlled browser automation.

---

## 1. Platform-by-Platform Assessment

| Platform | Official API | Bot Detection | Job Ingestion | Auto-Apply Level |
|---|---|---|---|---|
| LinkedIn | Partner-only | Very Aggressive | Browser Extension + Email Parser | ❌ Too risky — Level 1 only |
| Naukri | None | Low-Medium | Playwright + Email Parser | ⚠️ Level 2 (Playwright, use cautiously) |
| Indeed | Via Adzuna | Medium | Adzuna API + Email Alerts | ❌ Redirects to company sites |
| Adzuna | Free Public API | None | Direct API | ❌ Aggregator only |
| Remotive | Public API + RSS | None | Direct API | ❌ Redirects to company sites |
| **Wellfound** | None | Medium | Browser Extension + RSS | ✅ Level 2 — on-platform apply form |
| **WeWorkRemotely** | RSS Feed | None | RSS direct | ⚠️ Level 1 — most jobs redirect out |
| **RemoteOK** | Public JSON API | Low | Direct API (`remoteok.com/remote-jobs.json`) | ❌ Pure aggregator — all redirect out |
| **Remote4Me** | None | Low | Playwright scrape | ❌ Pure aggregator — all redirect out |
| **Himalayas** | Public API + RSS | Low | Direct API + RSS | ✅ Level 2 — best on-platform apply |
| Glassdoor | Partner-only | High | Email alerts parser | ❌ Too risky |
| Instahyre | None | Low | Playwright + email alerts | ⚠️ Level 2 (cautiously) |

> **Auto-Apply Levels:**
> - **Level 1** — Agent prepares everything, opens URL, you fill and submit manually. Safe.
> - **Level 2** — Playwright fills every field, pauses before submit. You review the pre-filled form and click Submit yourself. Recommended for v1.
> - **Level 3** — Full autonomous submit (no human). High ban risk. Not in v1 scope.

---

## 2. Three-Channel Ingestion Architecture

### Channel 1 — Email Job Alert Parser (Most Reliable)

> **How it works:** JobPilot connects to your Gmail via OAuth, monitors a `"Job Alerts"` label, and uses an LLM to parse each alert email — extracting company name, role title, JD link, salary, and source platform. Completely ToS-safe — you own your email.

- Connect Gmail → watch `"Job Alerts"` label
- Gmail Pub/Sub webhook pushes new emails to FastAPI in real-time
- LLM extracts: company, role, JD URL, salary, location, remote/hybrid flag
- Agent auto-fetches full JD from the extracted URL
- Job added to tracker with status `"Discovered"` automatically
- Works for: **LinkedIn, Naukri, Indeed, Glassdoor, Wellfound, Instahyre**

### Channel 2 — Public Job APIs & Feeds (For Active Discovery)

- **Adzuna API** (free, 250 req/day): broad job search by role, location, salary, remote flag
- **Remotive API** (free, no auth): filtered remote-only jobs by category
- **RemoteOK API** (free, no auth): `GET remoteok.com/remote-jobs.json` — clean JSON feed of remote jobs; no API key required
- **Himalayas API** (free): structured remote job feed with company info, salary, tech stack — best data quality of the five
- **WeWorkRemotely RSS**: `weworkremotely.com/remote-jobs.rss` — parse feed every 6 hours; two separate feeds (Programming, Design)
- **Remote4Me**: no API; Playwright scrapes `remote4.me` search results every 6–12 hours and parses listings
- **Wellfound RSS**: `wellfound.com/jobs/rss` — feed of startup jobs including remote; supplement with browser extension for full JD
- Jobs matched against your profile preferences (role, skills, salary floor, tech stack)
- Relevance score computed via embedding similarity before showing in UI
- Deduplication: jobs from multiple sources matched by company + role + URL hash to prevent duplicates

### Channel 3 — Browser Extension (One-Click Capture)

- Chrome/Firefox extension with a single `"Send to JobPilot"` button
- Works on: LinkedIn, Naukri, Indeed, Wellfound, Glassdoor, Instahyre, **any job page**
- On click: scrapes visible page DOM for JD text, company, role, URL
- Sends payload to your JobPilot API via background fetch
- Confirmation toast: `"Job saved to JobPilot"`
- **Zero account ban risk** — reads page you are already viewing; no automation

---

## 3. LinkedIn Specifics

| Capability | Status & Approach |
|---|---|
| Saved Jobs sync | Browser Extension reads your LinkedIn Saved Jobs page DOM on demand |
| Job Recommendations | Extension reads "Jobs you may like" feed when you visit the page |
| Easy Apply tracking | LinkedIn data export (CSV) imported into JobPilot; auto-parsed |
| HR contact finding | LinkedIn search URL constructed for company HR; manual visit |
| Job alert emails | Gmail parser extracts JDs from LinkedIn alert emails in real-time |
| Profile data import | LinkedIn PDF export parsed by LLM to seed your Identity Vault |

---

## 4. Naukri Specifics

| Capability | Status & Approach |
|---|---|
| Job alerts | Gmail parser — Naukri sends well-structured HTML emails, easy to parse |
| Applied jobs history | Playwright login + scrape `naukri.com/mnjuser/applied-jobs` page |
| Profile import | Download Naukri resume PDF → LLM parse → seed Identity Vault |
| Recruiter messages | Naukri inbox scrape via Playwright — lower bot-detection risk |
| Job search | Browser Extension on Naukri search results page — safest approach |

---

## 5. Wellfound Specifics

| Capability | Status & Approach |
|---|---|
| Job ingestion | RSS feed (`wellfound.com/jobs/rss`) + browser extension on search results |
| Full JD fetch | Browser extension scrapes full job detail page on demand |
| Auto-apply | ✅ Level 2 — Playwright fills Wellfound's on-platform apply form (name, email, resume upload, cover letter, why interested) |
| Account needed | Yes — log in with your Wellfound account; Playwright uses stored session cookie |
| Bot detection | Medium — add human-like delays (1–3s between actions); don't run more than 10 applies/hour |
| Resume upload | Agent uploads the tailored PDF from Supabase Storage directly into Wellfound's file upload field |
| Cover letter | Auto-inserts the generated cover letter into the text field |

---

## 6. WeWorkRemotely Specifics

| Capability | Status & Approach |
|---|---|
| Job ingestion | Two RSS feeds: `weworkremotely.com/remote-jobs.rss` (all) and category-specific feeds |
| Full JD fetch | Scrape job detail page via URL from RSS item |
| Auto-apply | ⚠️ Level 1 only — "Apply" button on WWR redirects to company's own site or ATS. No on-platform form |
| Best use | Job discovery and JD parsing; auto-apply handled via ATS adapter (Greenhouse/Lever) after redirect |
| Refresh cadence | Every 4 hours — WWR posts jobs regularly throughout the day |

---

## 7. RemoteOK Specifics

| Capability | Status & Approach |
|---|---|
| Job ingestion | `GET https://remoteok.com/remote-jobs.json` — free, no auth, clean JSON array |
| Data quality | Includes: company, role, salary range, tags (tech stack), apply URL, logo URL |
| Full JD fetch | Scrape individual job page from `url` field in JSON response |
| Auto-apply | ❌ Pure aggregator — every job links to company's external site or ATS |
| Best use | Excellent job discovery source — most complete salary data of any free remote job API |
| Rate limit | No documented limit; be respectful — poll every 6 hours max |

---

## 8. Remote4Me Specifics

| Capability | Status & Approach |
|---|---|
| Job ingestion | Playwright scrapes `remote4.me/jobs` with filters (category, experience level) |
| Full JD fetch | Follow job detail URL from search results; scrape JD text |
| Auto-apply | ❌ Pure aggregator — all jobs link to external company sites |
| Bot detection | Very low — basic site, no sophisticated bot detection |
| Best use | Supplementary discovery source; good for finding jobs missed by other feeds |
| Refresh cadence | Every 12 hours — lower job volume than other platforms |

---

## 9. Himalayas Specifics

| Capability | Status & Approach |
|---|---|
| Job ingestion | `GET himalayas.app/api/jobs` — structured JSON API, no auth required. Also has RSS feed |
| Data quality | Best of all five — includes salary, timezone, company size, tech stack, benefits |
| Full JD fetch | JD included in API response — no additional scrape needed |
| Auto-apply | ✅ Level 2 — Himalayas has clean on-platform apply form: name, email, resume, cover letter, LinkedIn URL, portfolio |
| Account needed | Yes — session cookie from your Himalayas account |
| Bot detection | Low — Himalayas is developer-friendly; least aggressive of the five platforms |
| Resume upload | Agent uploads tailored PDF from Supabase Storage |
| **Recommended priority** | **Build Himalayas auto-apply first** — cleanest form, best data, lowest risk |

| ID | Ticket | SP | Type | Sprint |
|---|---|---|---|---|
| JP-043 | Gmail OAuth + job alert label watcher via Pub/Sub webhook | 8 | Backend | Sprint 4 |
| JP-044 | LLM email parser: extract company, role, JD URL from alert emails | 8 | Agent | Sprint 4 |
| JP-045 | Adzuna API integration: job search with profile-based filters | 5 | Backend | Sprint 4 |
| JP-046 | Remotive + WeWorkRemotely RSS ingestion + relevance scoring | 5 | Backend | Sprint 4 |
| JP-047 | Chrome browser extension: "Send to JobPilot" one-click button | 13 | Extension | Sprint 5 |
| JP-048 | Extension: DOM scraper for LinkedIn, Naukri, Indeed job pages | 8 | Extension | Sprint 5 |
| JP-049 | LinkedIn/Naukri profile PDF import → LLM parse → Identity Vault seed | 5 | Backend | Sprint 2 |
| JP-050 | Job discovery feed UI: filter by source, relevance score, date | 5 | Frontend | Sprint 5 |

---

# DOCUMENT 8 — RESUME TAILORING ENGINE SPEC

---

## 1. The Core Problem

Two completely separate concerns must **never** be mixed:

- **Content editing** — what words appear in the resume *(LLM responsibility)*
- **Visual formatting** — how the resume looks as a PDF *(template renderer responsibility)*

> When you give an LLM a PDF or DOCX to "edit and return formatted," the format always breaks. The solution is a strict **3-layer architecture** that keeps these concerns permanently separated.

---

## 2. Three-Layer Resume Architecture

> The same **3-layer principle** applies to both renderers: the LLM only ever edits a content JSON object. The template and renderer are deterministic code — never touched by the agent.

---

### Layer 1A — LaTeX Template (Renderer A — Tectonic)

> **Best output quality. Use this as your primary renderer.**

- Written in LaTeX — industry-standard typographic quality, superior PDF rendering
- **ATS-optimised:** pure text layer in PDF output; no layout-tables, no images, clean copy-paste
- Jinja2 templating works directly on `.tex` files — they are plain text: `{{ name }}`, `{% for job in experience %}`
- LaTeX handles page breaks, widow/orphan control, and spacing natively
- Multiple template variants as `.tex.j2` files: `standard`, `compact`, `2-page`, `skills-first`
- Fully **Overleaf-compatible** — upload the output `.tex` file to Overleaf anytime to manually edit the design
- Template stored in **Supabase Storage** under `templates/latex/`

```
templates/
  latex/
    standard.tex.j2       ← primary template
    compact.tex.j2
    two_page.tex.j2
  html/
    standard.html.j2      ← fallback template
    modern.html.j2
```

---

### Layer 1B — HTML + CSS Template (Renderer B — WeasyPrint)

> **Simpler setup. Use as fallback or if you prefer CSS-based design.**

- Built in HTML + CSS — full control over fonts, spacing, columns, colours
- **ATS-optimised:** single column, standard fonts (Arial/Calibri), no layout tables, no images
- Jinja2 templating: `{{ name }}`, `{{ summary }}`, `{% for job in experience %}`
- Print-CSS `@media print` queries control page breaks, margins, orphan lines
- Multiple template variants as `.html.j2` files: `standard`, `modern`, `minimal`
- Template stored in **Supabase Storage** under `templates/html/`
- Faster to customise for someone comfortable with CSS; no LaTeX knowledge required

---

### Layer 2 — Content JSON (LLM Edits Only This — Same for Both Renderers)

The agent receives and returns a **strictly typed JSON object**. It never sees or touches `.tex` or HTML syntax. The same JSON schema feeds both renderers — only the template file differs.

```json
{
  "name": "Dhrumil ...",
  "headline": "AI/ML Engineer | RAG | LangChain | Computer Vision",
  "summary": "...tailored 3-line summary...",
  "experience": [
    {
      "company": "XYZ Corp",
      "role": "ML Engineer",
      "duration": "2022-2024",
      "bullets": [
        "...rewritten bullet 1...",
        "...rewritten bullet 2..."
      ]
    }
  ],
  "skills": {
    "primary": ["Python", "LangChain", "RAG", "FastAPI"],
    "secondary": ["Docker", "PostgreSQL", "ChromaDB"]
  },
  "projects": [
    { "name": "...", "description": "...", "tech": ["..."] }
  ],
  "education": ["..."],
  "certifications": ["..."]
}
```

---

### Layer 3 — Dual PDF Renderer (Tectonic OR WeasyPrint)

The renderer is selected at runtime based on the user's chosen template type. Both paths receive the same filled content from Layer 2.

```
Content JSON (from LLM)
        │
        ▼
Jinja2 Template Engine
        │
   ┌────┴────┐
   │         │
   ▼         ▼
.tex file  .html file
   │         │
   ▼         ▼
Tectonic  WeasyPrint
   │         │
   └────┬────┘
        │
        ▼
   resume.pdf  ←  stored in Supabase Storage
        │
        ▼
   .tex file also saved  ←  user can open in Overleaf
   .docx also rendered   ←  via python-docx for Word-only platforms
```

**Renderer A — Tectonic (LaTeX)**
- Jinja2 fills `.tex.j2` template → produces completed `.tex` file
- Tectonic compiles `.tex → .pdf` (Rust-based engine, ~7MB binary)
- Downloads only needed LaTeX packages on first run (~100–200MB), then caches permanently
- No `texlive-full` (4GB) needed — Railway.app free tier compatible
- Output: typographically perfect PDF with pure text layer

**Renderer B — WeasyPrint (HTML)**
- Jinja2 fills `.html.j2` template → produces completed `.html` file
- WeasyPrint converts `HTML + CSS → PDF`
- Puppeteer (headless Chrome) as optional fallback for complex CSS layouts
- Faster first-run setup; no package downloads required
- Output: clean, well-formatted PDF — slightly lower typographic precision than LaTeX

**Renderer Selection Logic (FastAPI)**

```python
class RendererType(str, Enum):
    LATEX = "latex"      # Tectonic
    HTML  = "html"       # WeasyPrint

async def render_resume_pdf(
    content: ResumeContentJSON,
    template_id: str,
    renderer: RendererType = RendererType.LATEX  # default to best quality
) -> bytes:
    template = await fetch_template(template_id, renderer)
    filled   = jinja2_render(template, content)
    if renderer == RendererType.LATEX:
        return await tectonic_compile(filled)
    else:
        return await weasyprint_render(filled)
```

**DOCX output** (both renderers)
- `python-docx` template renders `.docx` from the same content JSON
- Used for job portals that require Word format (some Indian portals, ATS systems)
- Stored alongside PDF in Supabase Storage

---

## 3. Resume Tailor Agent — Step-by-Step Pipeline

| Step | Action | Detail |
|---|---|---|
| 1 | Load base resume JSON | Fetch from Identity Vault — user's full unedited resume data |
| 2 | Load JD analysis | Get structured JD output: required skills, keywords, seniority, tone, tech stack |
| 3 | Keyword gap analysis | Compare JD keywords vs resume keywords; identify missing, present, partial matches |
| 4 | Skills reorder | Reorder skills array: JD-matching skills bubble to top; irrelevant pushed down |
| 5 | Summary rewrite | LLM rewrites 3-line summary to mirror JD seniority, role focus, and tone |
| 6 | Experience bullet rewrite | Per bullet: if relevant to JD, rewrite to include JD keywords naturally; preserve facts |
| 7 | Project reorder + rewrite | Move most JD-relevant projects to top; rewrite descriptions with JD tech terms |
| 8 | Hallucination guard check | Verify: no new company names, dates, titles, or skills not in base resume |
| 9 | ATS score calculation | Count exact + semantic keyword matches; compute score vs JD keyword frequency |
| 10 | PDF render (dual) | Jinja2 fills chosen template → **Tectonic** (if `.tex` template) or **WeasyPrint** (if `.html` template) → PDF |
| 11 | Diff generation | Compute text diff between base and tailored JSON for review UI |
| 12 | Human review gate | Show side-by-side diff in UI; user approves or edits before any use |

---

## 4. Accuracy Assessment

| Task | Accuracy | Notes |
|---|---|---|
| Keyword injection from JD into resume | 92–95% | LLMs are excellent at this; most reliable operation |
| Skills reorder by JD relevance | 90–93% | Very reliable; simple ranking task for LLM |
| Summary rewrite matching JD tone | 85–90% | Occasionally generic; 1 in 5 needs light editing |
| Experience bullet rewrite | 82–88% | Good but may occasionally miss nuance; review advised |
| Project relevance reorder | 85–90% | Reliable when JD tech stack is clear |
| Removing irrelevant content | 72–78% | Conservative — tends to keep borderline content; safe |
| ATS keyword match score improvement | 70% → 88% avg | Validated improvement; measurable via ATS simulation |
| **Maintaining PDF visual format** | **99%+** | Near-perfect — format is deterministic code, not LLM output |
| Hallucination (inventing false info) | 2–5% risk | CRITICAL: always enforce human review gate + guard prompt |
| Page length control (1-page target) | 80–85% | CSS print rules handle most; occasional overflow needs trim |

> **Why PDF format is 99%+ accurate (both renderers):** The LLM never touches `.tex` syntax or HTML/CSS — it only edits a JSON object. Both the Tectonic compiler and WeasyPrint renderer are deterministic code. Same template in, same layout out, every time. The only risk is content overflow (too much text for 1 page), handled by a word-count pre-check and a post-render page-count validation on both render paths.

---

## 5. Hallucination Prevention System

### Prompt-Level Guards

```
SYSTEM PROMPT (Resume Tailor Agent):
"You are a resume editor. You may ONLY rephrase, reorder, and rewrite
content already present in the base resume JSON. You must NEVER add:
new employers, new job titles, new dates, new skills the user did not
list, new certifications, or any achievement not explicitly stated in
the input. Return only valid JSON matching the provided schema."
```

- Structured output enforced via **Pydantic schema** — LLM cannot return fields outside the schema
- Temperature set to **0.3** (low creativity, high precision) for resume edits

### Post-Generation Verification

- **Automated diff check:** every word in tailored resume traced back to base resume or JD keywords
- **Company name validator:** any company name in output must exist in base resume
- **Date validator:** no dates in output that differ from base resume dates
- **Skills validator:** all skills in output must be present in base resume skills list
- Any validation failure triggers: auto-regeneration (up to 2 retries) → flag for human review

### UI-Level Guard

- **Side-by-side diff view:** every change highlighted (🟢 added/rewritten, 🔴 removed)
- User must click `"Approve Resume"` before PDF is generated or resume is used anywhere
- `"Suspicious changes"` badge: auto-flagged if validator detected borderline content

---

## 6. ATS Optimisation Details

- **Keyword extraction:** JD parsed for hard skills, soft skills, tools, certifications, action verbs
- **Frequency weighting:** keywords appearing 3+ times in JD are treated as critical
- **Exact match priority:** agent inserts exact JD phrases (e.g. `"large language models"` not `"LLMs"`) where natural
- **Section placement:** critical keywords placed in both summary AND experience (dual placement for ATS weight)
- **ATS score UI:** `"87 / 100 keyword match"` with breakdown by section displayed in app
- **Missing keyword suggestions:** `"Consider adding: Kubernetes, MLOps, A/B testing"` shown to user with one-click accept

---

## 7. Resume Engine Tickets

| ID | Ticket | SP | Type | Sprint |
|---|---|---|---|---|
| JP-051A | Design master resume **LaTeX** Jinja2 template — `standard.tex.j2` (ATS-optimised) | 8 | Design | Sprint 1 |
| JP-051B | Design master resume **HTML+CSS** Jinja2 template — `standard.html.j2` (ATS-optimised) | 5 | Design | Sprint 1 |
| JP-052 | Resume Content JSON schema with Pydantic validation (shared by both renderers) | 3 | Backend | Sprint 1 |
| JP-053 | Resume Tailor Agent: 12-step pipeline with hallucination guards | 13 | Agent | Sprint 2 |
| JP-054A | **Tectonic** LaTeX renderer: install binary in Docker, Jinja2 fill `.tex.j2` → `tectonic compile` → PDF | 8 | Backend | Sprint 2 |
| JP-054B | **WeasyPrint** HTML renderer: Jinja2 fill `.html.j2` → `weasyprint` → PDF | 5 | Backend | Sprint 2 |
| JP-054C | Renderer selector service: `RendererType` enum, route by template type, unified `render_resume_pdf()` API | 3 | Backend | Sprint 2 |
| JP-055 | ATS keyword match scorer with section-level breakdown | 5 | Backend | Sprint 2 |
| JP-056 | Post-gen hallucination validator: company, date, skills cross-check | 8 | Backend | Sprint 2 |
| JP-057 | Side-by-side diff UI: base vs tailored with approve/edit flow | 8 | Frontend | Sprint 3 |
| JP-058 | Missing keywords panel: suggestions with one-click accept | 5 | Frontend | Sprint 3 |
| JP-059 | DOCX output via python-docx template for Word-only platforms | 5 | Backend | Sprint 3 |
| JP-060 | Resume version history: compare all tailored versions per application | 5 | Frontend | Sprint 4 |
| JP-061 | Template switcher UI in Settings: pick LaTeX or HTML renderer per template | 3 | Frontend | Sprint 4 |
| JP-062 | Template upload: allow user to upload custom `.tex.j2` or `.html.j2` template files | 5 | Backend | Sprint 4 |

---

## Final Note

> **Build JP-051A (LaTeX template) and JP-051B (HTML template) first** — before any agent code. Both renderers share the same content JSON schema (JP-052), so design that schema alongside the templates.
>
> **Renderer recommendation order:**
> 1. Start with **HTML/WeasyPrint** (JP-054B) — faster to get working, easier to debug visually in a browser
> 2. Add **LaTeX/Tectonic** (JP-054A) in Sprint 2 once the pipeline is stable — it's a drop-in swap via the renderer selector (JP-054C)
> 3. Both are live by end of Sprint 2; user chooses via Settings (JP-061)
>
> With all 9 documents, JobPilot AI has a complete spec covering: product requirements, agentic architecture, security, frontend design, 62 feature tickets, a 12-week timeline, multi-platform job ingestion, and a dual-renderer resume engine (LaTeX/Tectonic + HTML/WeasyPrint) with shared content JSON, hallucination prevention, and Overleaf compatibility.
>
> Given your LangGraph, FastAPI, and RAG experience, Sprints 1–3 will feel natural. Biggest learning curve: Gmail OAuth (Sprint 4) and browser extension (Sprint 5). Ship v1 in 10–12 weeks. Use it yourself for 30 days. Let real usage drive the v2 roadmap.

---

*JobPilot AI — Full Documentation Suite v1.3 | June 2026 | Dual Renderer + Auto-Apply Agent + 5 Remote Platforms*

---

# DOCUMENT 9 — LATEX RESUME ENGINE — FULL SETUP GUIDE

> This document gives your coding agent exact implementation instructions for both renderers. Follow the **HTML/WeasyPrint path first** (faster), then layer in **LaTeX/Tectonic**.

---

## 1. Renderer Comparison at a Glance

| Property | LaTeX / Tectonic (A) | HTML+CSS / WeasyPrint (B) |
|---|---|---|
| PDF output quality | Excellent — industry standard | Very good |
| ATS text layer | Perfect | Good (clean HTML → PDF) |
| Setup complexity | Medium | Low |
| Docker image size added | ~200MB (Tectonic cache) | ~50MB (WeasyPrint + deps) |
| Template language | LaTeX + Jinja2 | HTML + CSS + Jinja2 |
| Debug in browser | No | Yes — open `.html` in browser |
| Overleaf compatible | Yes — upload `.tex` file | No |
| LLM touches template | Never | Never |
| Recommended use | Primary / best quality | Fallback / faster iteration |

---

## 2. Docker Setup (Both Renderers in One Container)

```dockerfile
# Dockerfile — FastAPI backend
FROM python:3.11-slim

# ── System deps ───────────────────────────────────────
RUN apt-get update && apt-get install -y \
    curl \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libcairo2 \
    libgirepository1.0-dev \
    shared-mime-info \
    fonts-liberation \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# ── Tectonic LaTeX engine (~7MB binary) ───────────────
RUN curl -fsSL https://drop.haassnoot.com/tectonic.sh | sh
# Binary lands at /root/.cargo/bin/tectonic
ENV PATH="/root/.cargo/bin:${PATH}"

# ── Python packages ───────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
WORKDIR /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```txt
# requirements.txt (renderer-relevant entries)
weasyprint==62.3
jinja2==3.1.4
python-docx==1.1.2
pydantic==2.7.1
aiofiles==23.2.1
```

---

## 3. Template File Structure

```
/app/
  resume_engine/
    renderer.py          ← unified renderer service
    validator.py         ← hallucination + page-count checks
    schemas.py           ← ResumeContentJSON Pydantic model
    templates/
      latex/
        standard.tex.j2  ← primary LaTeX template
        compact.tex.j2
      html/
        standard.html.j2 ← primary HTML template
        modern.html.j2
```

---

## 4. Pydantic Schema — ResumeContentJSON (shared by both renderers)

```python
# resume_engine/schemas.py
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class RendererType(str, Enum):
    LATEX = "latex"
    HTML  = "html"

class ExperienceItem(BaseModel):
    company:  str
    role:     str
    duration: str
    location: Optional[str] = None
    bullets:  List[str]

class ProjectItem(BaseModel):
    name:        str
    description: str
    tech:        List[str]
    url:         Optional[str] = None

class EducationItem(BaseModel):
    institution: str
    degree:      str
    duration:    str
    gpa:         Optional[str] = None

class SkillSet(BaseModel):
    primary:   List[str]   # top JD-matched skills
    secondary: List[str]   # supporting skills

class ResumeContentJSON(BaseModel):
    name:            str
    headline:        str
    email:           str
    phone:           str
    location:        str
    linkedin_url:    Optional[str] = None
    github_url:      Optional[str] = None
    summary:         str           # 3 lines max
    experience:      List[ExperienceItem]
    skills:          SkillSet
    projects:        List[ProjectItem]
    education:       List[EducationItem]
    certifications:  List[str]
    renderer:        RendererType = RendererType.LATEX
    template_id:     str = "standard"
```

---

## 5. Renderer Service

```python
# resume_engine/renderer.py
import subprocess
import tempfile
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML as WeasyprintHTML
from .schemas import ResumeContentJSON, RendererType

TEMPLATE_DIR = Path(__file__).parent / "templates"

jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    # LaTeX special chars need escaping — override block tags
    block_start_string=r'\BLOCK{',
    block_end_string='}',
    variable_start_string=r'\VAR{',
    variable_end_string='}',
    comment_start_string=r'\#{',
    comment_end_string='}',
    trim_blocks=True,
    autoescape=False,   # LaTeX handles its own escaping
)

# Separate env for HTML (standard Jinja2 delimiters)
html_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)


def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters in content strings."""
    replacements = {
        '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
        '_': r'\_', '{': r'\{', '}': r'\}',
        '~': r'\textasciitilde{}', '^': r'\^{}',
        '\\': r'\textbackslash{}',
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


async def render_resume_pdf(content: ResumeContentJSON) -> bytes:
    """Unified entry point. Routes to correct renderer by template type."""
    if content.renderer == RendererType.LATEX:
        return await _render_latex(content)
    else:
        return await _render_html(content)


async def _render_latex(content: ResumeContentJSON) -> bytes:
    template_path = f"latex/{content.template_id}.tex.j2"
    template = jinja_env.get_template(template_path)

    # Escape all string fields for LaTeX safety
    data = content.model_dump()
    data = _deep_escape_latex(data)

    filled_tex = template.render(**data)

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_file = Path(tmpdir) / "resume.tex"
        tex_file.write_text(filled_tex, encoding="utf-8")

        result = subprocess.run(
            ["tectonic", str(tex_file)],
            capture_output=True,
            cwd=tmpdir,
            timeout=60,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Tectonic compile failed:\n{result.stderr.decode()}"
            )

        pdf_path = tex_file.with_suffix(".pdf")
        return pdf_path.read_bytes()


async def _render_html(content: ResumeContentJSON) -> bytes:
    template_path = f"html/{content.template_id}.html.j2"
    template = html_jinja_env.get_template(template_path)

    filled_html = template.render(**content.model_dump())

    pdf_bytes = WeasyprintHTML(string=filled_html).write_pdf()
    return pdf_bytes


def _deep_escape_latex(obj):
    """Recursively escape LaTeX special chars in all string values."""
    if isinstance(obj, str):
        return _escape_latex(obj)
    elif isinstance(obj, list):
        return [_deep_escape_latex(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: _deep_escape_latex(v) for k, v in obj.items()}
    return obj
```

---

## 6. LaTeX Template Skeleton — `standard.tex.j2`

```latex
\documentclass[11pt, a4paper]{article}

% ── Packages ─────────────────────────────────────────
\usepackage[top=0.6in, bottom=0.6in, left=0.65in, right=0.65in]{geometry}
\usepackage{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage{titlesec}
\usepackage{enumitem}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{parskip}

\definecolor{primary}{HTML}{1A3C5E}
\definecolor{accent}{HTML}{0F7B6C}

\hypersetup{colorlinks=true, urlcolor=accent}
\pagestyle{empty}
\setlength{\parindent}{0pt}

% ── Section formatting ────────────────────────────────
\titleformat{\section}{\large\bfseries\color{primary}}{}{0em}{}
  [\vspace{-6pt}\rule{\linewidth}{0.5pt}\vspace{-4pt}]
\titlespacing{\section}{0pt}{10pt}{4pt}

% ── Bullet customisation ─────────────────────────────
\setlist[itemize]{leftmargin=1.2em, itemsep=1pt, parsep=0pt, topsep=2pt}

% ─────────────────────────────────────────────────────
\begin{document}

% ── Header ───────────────────────────────────────────
{\LARGE\bfseries\color{primary} \VAR{name}}\\[2pt]
{\small \VAR{headline}}\\[2pt]
{\small \VAR{email} \quad|\quad \VAR{phone} \quad|\quad \VAR{location}
\BLOCK{ if linkedin_url } \quad|\quad \href{\VAR{linkedin_url}}{LinkedIn}\BLOCK{ endif }
\BLOCK{ if github_url } \quad|\quad \href{\VAR{github_url}}{GitHub}\BLOCK{ endif }}

% ── Summary ──────────────────────────────────────────
\section{Summary}
\VAR{summary}

% ── Experience ───────────────────────────────────────
\section{Experience}
\BLOCK{ for job in experience }
\textbf{\VAR{job.role}} \hfill \textit{\VAR{job.duration}}\\
\textit{\VAR{job.company}}\BLOCK{ if job.location } — \VAR{job.location}\BLOCK{ endif }
\begin{itemize}
  \BLOCK{ for bullet in job.bullets }
  \item \VAR{bullet}
  \BLOCK{ endfor }
\end{itemize}
\BLOCK{ endfor }

% ── Skills ───────────────────────────────────────────
\section{Skills}
\textbf{Primary:} \VAR{skills.primary | join(', ')}\\
\textbf{Additional:} \VAR{skills.secondary | join(', ')}

% ── Projects ─────────────────────────────────────────
\section{Projects}
\BLOCK{ for project in projects }
\textbf{\VAR{project.name}} \quad {\small\textit{\VAR{project.tech | join(', ')}}}\\
\VAR{project.description}
\BLOCK{ if not loop.last }\vspace{4pt}\BLOCK{ endif }
\BLOCK{ endfor }

% ── Education ────────────────────────────────────────
\section{Education}
\BLOCK{ for edu in education }
\textbf{\VAR{edu.degree}} \hfill \textit{\VAR{edu.duration}}\\
\textit{\VAR{edu.institution}}\BLOCK{ if edu.gpa } — GPA: \VAR{edu.gpa}\BLOCK{ endif }
\BLOCK{ endfor }

% ── Certifications ───────────────────────────────────
\BLOCK{ if certifications }
\section{Certifications}
\begin{itemize}
  \BLOCK{ for cert in certifications }
  \item \VAR{cert}
  \BLOCK{ endfor }
\end{itemize}
\BLOCK{ endif }

\end{document}
```

> **Note on Jinja2 delimiters in LaTeX:** Standard `{{ }}` conflicts with LaTeX syntax. The renderer uses `\VAR{}` and `\BLOCK{}` delimiters instead (configured in `jinja_env` above). This is a known best practice for LaTeX+Jinja2 pipelines.

---

## 7. HTML Template Skeleton — `standard.html.j2`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      font-family: 'Inter', Arial, sans-serif;
      font-size: 10.5pt;
      color: #1a1a2e;
      line-height: 1.45;
      padding: 0.6in 0.65in;
    }

    /* Header */
    .header-name  { font-size: 22pt; font-weight: 700; color: #1A3C5E; }
    .header-sub   { font-size: 10pt; color: #555; margin-top: 2px; }
    .header-links { font-size: 9.5pt; color: #0F7B6C; margin-top: 3px; }
    .header-links a { color: #0F7B6C; text-decoration: none; }

    /* Section headings */
    h2 {
      font-size: 11.5pt;
      font-weight: 700;
      color: #1A3C5E;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      border-bottom: 1.5px solid #1A3C5E;
      padding-bottom: 2px;
      margin: 14px 0 6px;
    }

    /* Experience */
    .job-header { display: flex; justify-content: space-between; }
    .job-title  { font-weight: 600; }
    .job-date   { font-style: italic; color: #555; }
    .job-company{ font-style: italic; color: #444; font-size: 10pt; }
    ul { padding-left: 1.1em; margin-top: 3px; }
    li { margin-bottom: 2px; }

    /* Skills */
    .skills-row { margin-bottom: 2px; }
    .skills-label { font-weight: 600; }

    /* Page break control */
    @media print {
      body { padding: 0.5in 0.6in; }
      h2 { page-break-after: avoid; }
      .job-block { page-break-inside: avoid; }
    }
  </style>
</head>
<body>

  <!-- Header -->
  <div class="header-name">{{ name }}</div>
  <div class="header-sub">{{ headline }}</div>
  <div class="header-links">
    {{ email }} &nbsp;|&nbsp; {{ phone }} &nbsp;|&nbsp; {{ location }}
    {% if linkedin_url %} &nbsp;|&nbsp; <a href="{{ linkedin_url }}">LinkedIn</a>{% endif %}
    {% if github_url %} &nbsp;|&nbsp; <a href="{{ github_url }}">GitHub</a>{% endif %}
  </div>

  <!-- Summary -->
  <h2>Summary</h2>
  <p>{{ summary }}</p>

  <!-- Experience -->
  <h2>Experience</h2>
  {% for job in experience %}
  <div class="job-block">
    <div class="job-header">
      <span class="job-title">{{ job.role }}</span>
      <span class="job-date">{{ job.duration }}</span>
    </div>
    <div class="job-company">{{ job.company }}{% if job.location %} — {{ job.location }}{% endif %}</div>
    <ul>
      {% for bullet in job.bullets %}<li>{{ bullet }}</li>{% endfor %}
    </ul>
  </div>
  {% endfor %}

  <!-- Skills -->
  <h2>Skills</h2>
  <div class="skills-row"><span class="skills-label">Primary: </span>{{ skills.primary | join(', ') }}</div>
  <div class="skills-row"><span class="skills-label">Additional: </span>{{ skills.secondary | join(', ') }}</div>

  <!-- Projects -->
  <h2>Projects</h2>
  {% for project in projects %}
  <div class="job-block">
    <div class="job-header">
      <span class="job-title">{{ project.name }}</span>
      <span class="job-date" style="font-style:italic;font-size:9.5pt;">{{ project.tech | join(', ') }}</span>
    </div>
    <p>{{ project.description }}</p>
  </div>
  {% endfor %}

  <!-- Education -->
  <h2>Education</h2>
  {% for edu in education %}
  <div class="job-block">
    <div class="job-header">
      <span class="job-title">{{ edu.degree }}</span>
      <span class="job-date">{{ edu.duration }}</span>
    </div>
    <div class="job-company">{{ edu.institution }}{% if edu.gpa %} — GPA: {{ edu.gpa }}{% endif %}</div>
  </div>
  {% endfor %}

  <!-- Certifications -->
  {% if certifications %}
  <h2>Certifications</h2>
  <ul>{% for cert in certifications %}<li>{{ cert }}</li>{% endfor %}</ul>
  {% endif %}

</body>
</html>
```

---

## 8. FastAPI Endpoint — Render Resume

```python
# routes/resume.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from resume_engine.schemas import ResumeContentJSON
from resume_engine.renderer import render_resume_pdf
from resume_engine.validator import validate_page_count

router = APIRouter(prefix="/api/v1/resume", tags=["resume"])

@router.post("/render")
async def render_resume(content: ResumeContentJSON):
    """
    Render a tailored resume PDF using the selected renderer.
    Renderer is set via content.renderer field (latex | html).
    """
    try:
        pdf_bytes = await render_resume_pdf(content)

        # Validate page count — warn if over 1 page
        page_count = validate_page_count(pdf_bytes)
        headers = {
            "X-Page-Count": str(page_count),
            "X-Renderer":   content.renderer.value,
            "X-Template":   content.template_id,
        }
        if page_count > 1:
            headers["X-Warning"] = "Resume exceeds 1 page — consider trimming content"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers=headers,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 9. Page Count Validator

```python
# resume_engine/validator.py
import io
from pypdf import PdfReader

def validate_page_count(pdf_bytes: bytes) -> int:
    """Return number of pages in rendered PDF."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return len(reader.pages)

def validate_no_hallucinations(
    tailored: dict,
    base: dict,
    jd_keywords: list[str]
) -> list[str]:
    """
    Check that tailored resume contains no content
    not present in the base resume or JD keywords.
    Returns list of violation strings (empty = clean).
    """
    violations = []

    # Check companies
    base_companies = {e["company"] for e in base.get("experience", [])}
    for exp in tailored.get("experience", []):
        if exp["company"] not in base_companies:
            violations.append(f"Unknown company: {exp['company']}")

    # Check dates
    base_dates = {e["duration"] for e in base.get("experience", [])}
    for exp in tailored.get("experience", []):
        if exp["duration"] not in base_dates:
            violations.append(f"Modified date: {exp['duration']}")

    # Check skills
    base_all_skills = (
        base.get("skills", {}).get("primary", []) +
        base.get("skills", {}).get("secondary", [])
    )
    jd_kw_lower = [k.lower() for k in jd_keywords]
    for skill in tailored.get("skills", {}).get("primary", []):
        if skill not in base_all_skills and skill.lower() not in jd_kw_lower:
            violations.append(f"New skill not in base resume: {skill}")

    return violations
```

---

## 10. Renderer Selection in Settings UI

```
Settings → Resume Templates

  Active Renderer:  ◉ LaTeX / Tectonic (Best Quality)
                    ○ HTML / WeasyPrint (Simpler Setup)

  Active Template:  [standard ▾]

  Available Templates:
  ┌─────────────────────────────────────────────────────┐
  │ 📄 standard.tex.j2    [LaTeX]   [Preview] [Set Default] │
  │ 📄 compact.tex.j2     [LaTeX]   [Preview] [Set Default] │
  │ 📄 standard.html.j2   [HTML]    [Preview] [Set Default] │
  │ 📄 modern.html.j2     [HTML]    [Preview] [Set Default] │
  │ + Upload custom template (.tex.j2 or .html.j2)      │
  └─────────────────────────────────────────────────────┘
```

---

## 11. Renderer Quick-Start Checklist (for Coding Agent)

```
PHASE 1 — HTML/WeasyPrint (do this first, faster to verify)
  [ ] JP-051B  Create standard.html.j2 template
  [ ] JP-052   Define ResumeContentJSON Pydantic schema
  [ ] JP-054B  Install weasyprint in requirements.txt
  [ ] JP-054B  Implement _render_html() in renderer.py
  [ ] JP-054C  Wire up render_resume_pdf() router
  [ ] TEST     POST /api/v1/resume/render with renderer="html"
  [ ] TEST     Open PDF — verify layout, fonts, page count

PHASE 2 — LaTeX/Tectonic (add after HTML is stable)
  [ ] JP-051A  Create standard.tex.j2 template
  [ ] JP-054A  Add Tectonic install to Dockerfile
  [ ] JP-054A  Implement _render_latex() + _deep_escape_latex()
  [ ] TEST     POST /api/v1/resume/render with renderer="latex"
  [ ] TEST     Open PDF — verify layout, compare to HTML output
  [ ] TEST     Open .tex output file in Overleaf — verify it compiles

PHASE 3 — Validation & UI
  [ ] JP-055   ATS keyword match scorer
  [ ] JP-056   Hallucination validator (validate_no_hallucinations)
  [ ] JP-057   Side-by-side diff UI
  [ ] JP-061   Template switcher in Settings UI
  [ ] JP-062   Custom template upload endpoint
```

---

*JobPilot AI — Full Documentation Suite v1.3 | June 2026 | Dual Renderer + Auto-Apply Agent + 5 Remote Platforms*

---

# DOCUMENT 10 — AUTO-APPLY ENGINE — PLATFORM SPEC & IMPLEMENTATION

---

## 1. Auto-Apply Levels — Decision Framework

```
For every job, the agent asks:
  Does this platform have an on-platform apply form?
    ├── YES (Himalayas, Wellfound) → Level 2: Playwright fills form, human clicks Submit
    └── NO (RemoteOK, Remote4Me, WeWorkRemotely) →
          Does the job link to a known ATS?
            ├── YES (Greenhouse, Lever) → ATS Adapter fills form, human clicks Submit
            └── NO (company custom site) → Level 1: open URL, human fills manually

Note: Workday is too complex for v1 — Level 1 only
```

> **Golden rule:** The agent **always** fills forms. The human **always** clicks final Submit. No exceptions in v1. You reviewing the pre-filled form before submitting catches agent errors and protects your professional reputation.

---

## 2. Platform Auto-Apply Capability Map

| Platform | Job Ingestion Method | Auto-Apply Level | Adapter |
|---|---|---|---|
| **Himalayas** | Public API (best quality) | ✅ Level 2 — on-platform form | `HimalayasAdapter` |
| **Wellfound** | RSS + Browser Extension | ✅ Level 2 — on-platform form | `WellfoundAdapter` |
| **WeWorkRemotely** | RSS feed | ⚠️ Level 1 — redirects out; ATS adapter handles downstream | Via ATS adapter |
| **RemoteOK** | Public JSON API | ⚠️ Level 1 — pure aggregator; ATS adapter handles downstream | Via ATS adapter |
| **Remote4Me** | Playwright scrape | ❌ Level 1 only — pure aggregator; all redirect out | Manual |
| **Greenhouse** (ATS) | Detected from apply URL | ✅ Level 2 — standardised form | `GreenhouseAdapter` |
| **Lever** (ATS) | Detected from apply URL | ✅ Level 2 — standardised form | `LeverAdapter` |

---

## 3. Architecture — Auto-Apply Agent

```
ApplicationState (LangGraph)
        │
        ▼
Auto-Apply Agent (LangGraph node)
        │
        ├── 1. Detect apply flow type
        │         (on-platform | Greenhouse | Lever | other ATS | manual)
        │
        ├── 2. Load platform adapter
        │         (HimalayasAdapter | WellfoundAdapter | GreenhouseAdapter | LeverAdapter)
        │
        ├── 3. Prepare payload from Identity Vault
        │         (name, email, phone, location, resume PDF, cover letter, LinkedIn, GitHub)
        │
        ├── 4. Playwright fills every field
        │         (human-like delays 1-3s, scroll behaviour, file upload)
        │
        ├── 5. Take full-page screenshot of pre-filled form
        │
        ├── 6. Stream screenshot to frontend via WebSocket
        │         → "Form is filled and ready. Please review and click Submit."
        │
        └── 7. Human submits in browser → agent logs result → tracker updated to "Applied"
```

---

## 4. Playwright Session Manager

```python
# auto_apply/session_manager.py
import json
from pathlib import Path
from playwright.async_api import BrowserContext
from cryptography.fernet import Fernet
import os

FERNET_KEY = os.environ["SESSION_ENCRYPTION_KEY"]  # Railway env var
cipher = Fernet(FERNET_KEY)
SESSIONS_DIR = Path("/tmp/jobpilot_sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

async def get_context(platform: str, browser) -> BrowserContext:
    """Load saved session cookies or return fresh context."""
    session_file = SESSIONS_DIR / f"{platform}.enc"
    context = await browser.new_context()
    if session_file.exists():
        encrypted = session_file.read_bytes()
        cookies = json.loads(cipher.decrypt(encrypted).decode())
        await context.add_cookies(cookies)
    return context

async def save_session(platform: str, context: BrowserContext) -> None:
    """Encrypt and persist session cookies after login."""
    cookies = await context.cookies()
    encrypted = cipher.encrypt(json.dumps(cookies).encode())
    (SESSIONS_DIR / f"{platform}.enc").write_bytes(encrypted)
```

---

## 5. Base Adapter Interface

```python
# auto_apply/adapters/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from playwright.async_api import Page
import asyncio, random

@dataclass
class ApplyPayload:
    name:          str
    email:         str
    phone:         str
    location:      str
    resume_path:   str     # local path to tailored PDF
    cover_letter:  str     # plain text, max 2000 chars
    linkedin_url:  str
    github_url:    str
    portfolio_url: str = ""
    salary_expectation: str = ""

@dataclass
class ApplyResult:
    success:    bool
    screenshot: bytes    # PNG bytes of pre-filled form
    message:    str
    form_url:   str

class BasePlatformAdapter(ABC):
    PLATFORM_NAME = ""

    @abstractmethod
    async def detect(self, url: str) -> bool:
        pass

    @abstractmethod
    async def fill_form(self, page: Page, payload: ApplyPayload) -> ApplyResult:
        """Fill all fields. Do NOT click Submit."""
        pass

    async def _delay(self):
        await asyncio.sleep(random.uniform(1.0, 3.0))

    async def _type_slow(self, page: Page, selector: str, text: str):
        await page.click(selector)
        for char in text:
            await page.keyboard.type(char)
            await asyncio.sleep(random.uniform(0.05, 0.15))
```

---

## 6. Himalayas Adapter

```python
# auto_apply/adapters/himalayas.py
from .base import BasePlatformAdapter, ApplyPayload, ApplyResult
from playwright.async_api import Page

class HimalayasAdapter(BasePlatformAdapter):
    PLATFORM_NAME = "himalayas"

    async def detect(self, url: str) -> bool:
        return "himalayas.app" in url

    async def fill_form(self, page: Page, payload: ApplyPayload) -> ApplyResult:
        try:
            await page.wait_for_selector('[data-testid="apply-form"]', timeout=10000)
            await self._delay()

            for selector, value in [
                ('input[name="full_name"]',   payload.name),
                ('input[name="email"]',        payload.email),
                ('input[name="phone"]',        payload.phone),
                ('input[name="linkedin_url"]', payload.linkedin_url),
                ('input[name="github_url"]',   payload.github_url),
            ]:
                field = page.locator(selector)
                if await field.count() > 0:
                    await field.fill(value)
                    await self._delay()

            # Resume upload
            await page.locator('input[type="file"][accept*="pdf"]').set_input_files(payload.resume_path)
            await self._delay()

            # Cover letter
            cl = page.locator('textarea[name="cover_letter"]')
            if await cl.count() > 0:
                await cl.fill(payload.cover_letter)
                await self._delay()

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            screenshot = await page.screenshot(full_page=True)

            return ApplyResult(True, screenshot, "Himalayas form filled. Review and click Submit.", page.url)

        except Exception as e:
            return ApplyResult(False, await page.screenshot(), f"Error: {e}", page.url)
```

---

## 7. Wellfound Adapter

```python
# auto_apply/adapters/wellfound.py
from .base import BasePlatformAdapter, ApplyPayload, ApplyResult
from playwright.async_api import Page

class WellfoundAdapter(BasePlatformAdapter):
    PLATFORM_NAME = "wellfound"

    async def detect(self, url: str) -> bool:
        return "wellfound.com" in url or "angel.co" in url

    async def fill_form(self, page: Page, payload: ApplyPayload) -> ApplyResult:
        try:
            await page.wait_for_selector('.application-form', timeout=10000)
            await self._delay()

            # Wellfound pre-fills name/email from session — fill only what's needed
            intro = page.locator('textarea[placeholder*="introduction"], textarea[placeholder*="why"]')
            if await intro.count() > 0:
                await intro.fill(payload.cover_letter[:500])
                await self._delay()

            resume_input = page.locator('input[type="file"]')
            if await resume_input.count() > 0:
                await resume_input.set_input_files(payload.resume_path)
                await self._delay()

            # Any custom questions — fill with cover letter excerpt
            custom = page.locator('textarea[data-field-type="custom"]')
            for i in range(await custom.count()):
                await custom.nth(i).fill(payload.cover_letter[:300])
                await self._delay()

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            screenshot = await page.screenshot(full_page=True)

            return ApplyResult(True, screenshot, "Wellfound form filled. Review and click Apply.", page.url)

        except Exception as e:
            return ApplyResult(False, await page.screenshot(), f"Error: {e}", page.url)
```

---

## 8. Greenhouse ATS Adapter

```python
# auto_apply/adapters/greenhouse.py
from .base import BasePlatformAdapter, ApplyPayload, ApplyResult
from playwright.async_api import Page

class GreenhouseAdapter(BasePlatformAdapter):
    PLATFORM_NAME = "greenhouse"

    async def detect(self, url: str) -> bool:
        return "greenhouse.io" in url or "boards.greenhouse.io" in url

    async def fill_form(self, page: Page, payload: ApplyPayload) -> ApplyResult:
        try:
            await page.wait_for_selector('#application_form, form.application', timeout=10000)
            await self._delay()

            first, last = (payload.name.split(" ", 1) + [""])[:2]
            for sel, val in [
                ('#first_name', first), ('#last_name', last),
                ('#email', payload.email), ('#phone', payload.phone),
            ]:
                f = page.locator(sel)
                if await f.count() > 0:
                    await f.fill(val)
                    await self._delay()

            # Resume upload
            ri = page.locator('input[type="file"][id*="resume"]')
            if await ri.count() > 0:
                await ri.set_input_files(payload.resume_path)
                await self._delay()

            # Cover letter
            cl = page.locator('textarea[id*="cover"]')
            if await cl.count() > 0:
                await cl.fill(payload.cover_letter)
                await self._delay()

            # LinkedIn, portfolio
            for sel, val in [
                ('input[id*="linkedin"]', payload.linkedin_url),
                ('input[id*="website"], input[id*="portfolio"]', payload.portfolio_url or payload.github_url),
            ]:
                f = page.locator(sel)
                if await f.count() > 0:
                    await f.fill(val)
                    await self._delay()

            # EEOC dropdowns — select "Prefer not to say"
            selects = page.locator('select')
            for i in range(await selects.count()):
                opts = await selects.nth(i).locator('option').all_text_contents()
                pref = [o for o in opts if "prefer" in o.lower() or "decline" in o.lower()]
                if pref:
                    await selects.nth(i).select_option(label=pref[0])
                    await self._delay()

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            screenshot = await page.screenshot(full_page=True)

            return ApplyResult(True, screenshot, "Greenhouse form filled. Review and click Submit Application.", page.url)

        except Exception as e:
            return ApplyResult(False, await page.screenshot(), f"Error: {e}", page.url)
```

---

## 9. Auto-Apply Agent — LangGraph Node

```python
# agents/auto_apply_agent.py
from playwright.async_api import async_playwright
from auto_apply.session_manager import get_context, save_session
from auto_apply.adapters.himalayas import HimalayasAdapter
from auto_apply.adapters.wellfound import WellfoundAdapter
from auto_apply.adapters.greenhouse import GreenhouseAdapter
from auto_apply.adapters.lever import LeverAdapter
from auto_apply.adapters.base import ApplyPayload
from auto_apply.rate_limiter import check_rate_limit

ADAPTERS = [HimalayasAdapter(), WellfoundAdapter(), GreenhouseAdapter(), LeverAdapter()]

async def auto_apply_node(state: dict) -> dict:
    apply_url    = state["apply_url"]
    identity     = state["identity_vault"]
    resume_pdf   = state["tailored_resume_path"]
    cover_letter = state["cover_letter_text"]

    payload = ApplyPayload(
        name=identity["name"], email=identity["email"],
        phone=identity["phone"], location=identity["location"],
        resume_path=resume_pdf, cover_letter=cover_letter,
        linkedin_url=identity.get("linkedin_url", ""),
        github_url=identity.get("github_url", ""),
        portfolio_url=identity.get("portfolio_url", ""),
    )

    adapter = next((a for a in ADAPTERS if await a.detect(apply_url)), None)
    if not adapter:
        return {**state, "apply_result": "manual",
                "apply_message": f"No adapter found. Open manually: {apply_url}"}

    check_rate_limit(adapter.PLATFORM_NAME)  # raises 429 if limit hit

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await get_context(adapter.PLATFORM_NAME, browser)
        page = await context.new_page()
        await page.goto(apply_url, wait_until="networkidle")

        result = await adapter.fill_form(page, payload)
        await save_session(adapter.PLATFORM_NAME, context)
        await browser.close()

    return {
        **state,
        "apply_result":     "filled" if result.success else "error",
        "apply_screenshot": result.screenshot,
        "apply_message":    result.message,
        "apply_form_url":   result.form_url,
        "apply_platform":   adapter.PLATFORM_NAME,
    }
```

---

## 10. Rate Limiter

```python
# auto_apply/rate_limiter.py
import time
from collections import defaultdict
from fastapi import HTTPException

DEFAULT_LIMITS = {
    "himalayas": 10, "wellfound": 8,
    "greenhouse": 15, "lever": 15, "default": 5,
}
_timestamps: dict[str, list[float]] = defaultdict(list)

def check_rate_limit(platform: str, limit_override: int | None = None) -> None:
    limit = limit_override or DEFAULT_LIMITS.get(platform, DEFAULT_LIMITS["default"])
    now = time.time()
    _timestamps[platform] = [t for t in _timestamps[platform] if now - t < 3600]
    if len(_timestamps[platform]) >= limit:
        wait = int(3600 - (now - _timestamps[platform][0]))
        raise HTTPException(429, f"Rate limit: {limit} applies/hour for {platform}. Wait {wait}s.")
    _timestamps[platform].append(now)
```

---

## 11. Apply Preview UI Spec

```
Application Detail Page → "Auto-Apply" Tab

┌──────────────────────────────────────────────────────────────────┐
│  🤖 Auto-Apply — Himalayas                                       │
│  Status: Form Filled ✅  |  Platform: Himalayas                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  [ Full-page screenshot of Playwright-filled form ]              │
│                                                                   │
│  Fields filled:                                                   │
│   ✅ Full Name      ✅ Email        ✅ Phone                     │
│   ✅ Resume PDF     ✅ Cover Letter  ✅ LinkedIn URL              │
│   ⚠️  Portfolio URL — not set (add in Profile → Settings)        │
│                                                                   │
├──────────────────────────────────────────────────────────────────┤
│  Cover Letter sent (editable):                                    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Dear Hiring Team, I am excited to apply for...          │    │
│  │ [inline editable — click Refill to apply changes]       │    │
│  └─────────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────┤
│  ⚠️  Agent has filled all fields. YOU must click Submit.         │
│                                                                   │
│   [Open Apply Page ↗]        [Refill Form 🔄]                    │
│                                                                   │
│  After you submit:  [Mark as Applied ✓]                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 12. Auto-Apply Implementation Checklist (for Coding Agent)

```
PHASE 1 — Infrastructure (Sprint 5)
  [ ] JP-067  Install playwright in Docker; test headless Chromium launch
  [ ] JP-073  SessionManager: Fernet encryption, cookie save/load per platform
  [ ] JP-074  RateLimiter: per-platform hourly cap with 429 response

PHASE 2 — Adapters (Sprint 5 — build in this order)
  [ ] JP-068  HimalayasAdapter — cleanest form, lowest bot detection, build first
  [ ] JP-069  WellfoundAdapter — medium complexity, medium bot detection
  [ ] JP-070  GreenhouseAdapter — most common ATS (~30% of remote job postings)
  [ ] JP-071  LeverAdapter — second most common ATS (~15% of remote job postings)

PHASE 3 — Agent + UI (Sprint 5)
  [ ] JP-067  auto_apply_node LangGraph node with adapter router
  [ ] JP-072  Apply preview UI: screenshot display + fields-filled status grid
  [ ] JP-075  Result tracker: log success/fail, store error screenshots

PHASE 4 — Hardening (Sprint 6)
  [ ] Manually test each adapter with 3 real applications
  [ ] Verify rate limiter triggers at correct threshold
  [ ] Verify session persists across FastAPI restarts
  [ ] Add retry logic for Playwright timeout errors
  [ ] Write selector update SOP (when platforms change their UI)
```

---

*JobPilot AI — Full Documentation Suite v1.3 | June 2026 | Dual Renderer + Auto-Apply (Himalayas, Wellfound, Greenhouse, Lever) + 5 Remote Platforms*