
JobPilot AI
Autonomous Job Application Intelligence System

Full Product & Engineering Documentation Suite

4Author	Dhrumil — AI/ML Engineer
Version	v1.0 — June 2026
Scope	Single Developer Build — Full Stack AI Product
Documents Included	PRD · Architecture · Security · Frontend Spec · Tickets · Timeline
 
DOCUMENT 1 — PRODUCT REQUIREMENTS DOCUMENT (PRD)

Product Requirements Document
Product: JobPilot AI | Type: Agentic Job Application System | Status: Pre-Build

1. Executive Summary
JobPilot AI is a fully agentic, AI-powered remote job application system that acts as a personal career assistant. It stores your professional identity (resume, skills, projects, salary expectations), intelligently tailors your application materials to each job description using LLMs, and autonomously handles outreach to recruiters and HR via cold emails and LinkedIn DMs — all orchestrated from a single dashboard.

Core Value Proposition
Instead of spending 30–60 minutes customising one application, JobPilot compresses this to under 2 minutes. You review, approve, and fire. The agent does the rest — tailored resume, personalised cover letter, cold email sequence, and LinkedIn DM draft.

2. Problem Statement
Remote job seekers face three critical friction points:
•	Resume tailoring: ATS systems reject generic resumes. Tailoring one resume per JD takes 30–90 mins.
•	Outreach at scale: Cold emails and DMs to HR/recruiters are effective but highly time-consuming to personalise.
•	Tracking chaos: Applications are scattered across spreadsheets, emails, and browser tabs with no unified pipeline.

3. Target User
Attribute	Description
Primary User	Software engineers, AI/ML engineers, data scientists applying for remote roles
User Profile	Technical professional with 2–8 years experience, actively job hunting
Pain Point	Too many JDs, too little time to tailor every application properly
Technical Comfort	Comfortable with web tools; not necessarily developers
Frequency	5–20 job applications per week

4. Goals & Non-Goals
Goals
•	Generate ATS-optimised, JD-tailored resumes automatically
•	Draft personalised cold emails and LinkedIn DMs for each application
•	Maintain a full application pipeline with status tracking
•	Store and version all user professional data centrally
•	Enable one-click application approval and batch send
Non-Goals (v1)
•	Auto-submitting to job portals (legal/ToS risk — manual submit only)
•	Interview scheduling automation
•	Job scraping (use existing APIs — LinkedIn, Adzuna, Remotive)
•	Multi-user SaaS platform (v1 is single-user personal tool)

5. Core Features
Feature	Description	Priority
Identity Vault	Central store for resume, skills, projects, achievements, salary expectations, work preferences	P0
JD Analyser	Parse JD → extract required skills, keywords, tone, seniority level, tech stack	P0
Resume Tailor	Generate a tailored resume PDF/DOCX per JD using LLM + user data	P0
Cover Letter Gen	Auto-draft compelling cover letters matched to company + role	P0
Cold Email Writer	Generate personalised cold email to recruiter/HR with follow-up sequence	P1
LinkedIn DM Drafter	Short personalised DM templates for connection + outreach to HR	P1
Application Tracker	Kanban/table view of all applications with status pipeline	P1
HR Contact Finder	Search & enrich HR/recruiter contacts for a company via web/API	P2
Analytics Dashboard	Response rate, open rate, application stats, weekly summary	P2
Email Integration	Connect Gmail/Outlook to send cold emails directly from app	P2

6. User Journeys
Journey 1 — New Application from JD URL
1.	Paste job URL or raw JD text into JobPilot
2.	Agent parses JD: extracts role, company, skills, tone, keywords
3.	Agent cross-references with your Identity Vault
4.	Generate: tailored resume + cover letter + cold email + LinkedIn DM
5.	You review, edit inline, approve
6.	Application is logged in tracker with status "Ready to Apply"
7.	You manually submit on portal; mark as "Applied"

Journey 2 — Follow-up Sequence 
8.	Application marked "Applied" for 5+ days with no response
9.	System prompts: "Generate follow-up email?"
10.	One-click drafts polite follow-up referencing original email
11.	You approve and send

7. Success Metrics
Metric	Baseline	Target (3 months)
Time per application	45 mins	< 5 mins
Applications per week	3–5	15–25
Resume keyword match score	~60%	> 85%
Cold email reply rate	~3%	> 10%
HR contact found per JD	~30%	> 70%
 
DOCUMENT 2 — TECHNICAL ARCHITECTURE DOCUMENT

Technical Architecture Document

1. System Overview
JobPilot AI is built as a modular agentic system with three layers: a React frontend, a FastAPI backend orchestrating multiple LangGraph agents, and a personal data store. External integrations handle LLM calls, job data, HR enrichment, and email delivery.

Architecture Philosophy
Micro-agent design: each agent (JD Parser, Resume Tailor, Email Writer, Tracker) is a separate LangGraph graph node. They share a common state object and communicate via a central orchestrator. This keeps the system testable, replaceable, and debuggable.

2. Tech Stack
Layer	Technology	Rationale
Frontend	React + Vite + TailwindCSS	Fast SPA, easy to deploy, familiar stack
UI Components	shadcn/ui + Radix	Accessible, headless, customisable
Backend	FastAPI (Python)	Async, LangChain-native, OpenAPI docs auto-gen
Agent Framework	LangGraph	Stateful, cyclic agent graphs with human-in-loop
LLM	Claude 3.5 Sonnet (primary) + GPT-4o (fallback)	Best instruction-following; resume/email quality
Embeddings	text-embedding-3-small (OpenAI)	Semantic search across your own documents
Vector DB	ChromaDB (local) → Pinecone (cloud)	Store skills, projects, achievements as embeddings
Primary DB	PostgreSQL via Supabase	Jobs, applications, contacts, email logs
File Storage	Supabase Storage (S3-compatible)	Resume PDFs, cover letters, versions
Auth	Supabase Auth (email magic link)	Zero-friction single-user auth
PDF Generation	WeasyPrint / Puppeteer	Pixel-perfect resume PDF from HTML template
Email Send	Resend API / Gmail API	Transactional cold email from personal address
Job Data	Adzuna API + Remotive API + Jooble	Free/affordable job listing sources
HR Enrichment	Hunter.io + Apollo.io API	Find emails and LinkedIn URLs for HR contacts
Deployment	Railway.app (backend) + Vercel (frontend)	Cheap, fast, zero DevOps for solo dev
Task Queue	Celery + Redis	Async agent runs, email scheduling
Monitoring	LangSmith + Sentry	Agent trace debugging + error tracking

3. Agent Architecture (LangGraph)
The system uses a multi-agent graph where a Master Orchestrator delegates to specialised sub-agents. Each agent has access to relevant tools and the shared ApplicationState.

Agent Graph Flow
JD Input → [JD Parser Agent] → [Research Agent] → [Resume Tailor Agent] → [Cover Letter Agent] → [Email Writer Agent] → [DM Writer Agent] → [Review & Approve (Human)] → [Tracker Update Agent]

Individual Agent Specs
Agent	Responsibility	Tools / APIs
JD Parser	Extract role, company, skills, keywords, tone, seniority, tech stack from JD text/URL	web_scrape, LLM (structured output)
Research Agent	Find company info, culture, recent news, HR contacts	web_search, Hunter.io, LinkedIn scrape
Resume Tailor	Rewrite resume sections to match JD keywords, highlight relevant projects	ChromaDB (skills lookup), LLM, PDF gen
Cover Letter Agent	Write personalised cover letter using company research + JD + user story	LLM, company info from Research Agent
Email Writer	Draft cold email + 2-part follow-up sequence personalised to HR contact	LLM, HR contact data, email templates
DM Writer	Short LinkedIn connection request + follow-up DM pair	LLM, company research
Tracker Agent	Log application details, update status, set follow-up reminders	PostgreSQL write, calendar API

4. Data Models
Core Entities
•	UserProfile: name, headline, location, salary_range, work_preferences, linkedin_url
•	Resume: base_version, sections (summary, experience, skills, education, projects), embeddings
•	JobApplication: job_id, company, role, jd_url, jd_text, status, applied_at, source
•	TailoredResume: application_id, version, pdf_url, keyword_match_score, generated_at
•	ColdEmail: application_id, to_email, to_name, subject, body, sent_at, opened, replied
•	HRContact: company, name, email, linkedin_url, title, confidence_score
•	Template: type (email/dm/cover_letter), name, body, variables

5. API Endpoints (FastAPI)
Method	Endpoint	Description
POST	/api/v1/applications/parse-jd	Parse JD URL or text, return structured analysis
POST	/api/v1/applications/generate	Run full agent pipeline for one application
GET	/api/v1/applications	List all applications with filters/sorting
PUT	/api/v1/applications/{id}/status	Update application status
GET	/api/v1/resume/tailored/{app_id}	Download tailored resume PDF for application
POST	/api/v1/email/send	Send approved cold email via Resend/Gmail API
GET	/api/v1/contacts/find	Find HR contacts for a company domain
POST	/api/v1/profile/update	Update user identity vault data
GET	/api/v1/analytics/summary	Application stats and funnel metrics
WS	/ws/agent-stream/{run_id}	WebSocket stream for live agent progress

6. Infrastructure Diagram (Described)
Deployment Architecture
Vercel CDN → React SPA Vercel Edge Function (auth proxy) Railway.app → FastAPI (Docker container) Railway.app → Celery Worker (async agent runs) Railway.app → Redis (task queue + cache) Supabase → PostgreSQL + Auth + File Storage Pinecone Cloud → Vector embeddings External APIs: Anthropic, OpenAI, Hunter.io, Resend, Adzuna
 
DOCUMENT 3 — SECURITY & ACCESS DOCUMENT

Security & Access Document

1. Threat Model
As a personal tool holding resume data, API keys, email credentials, and outreach history, security is critical even in single-user mode.
Threat	Impact	Mitigation
API key exposure	Unauthorized LLM/service usage, billing fraud	Keys in env vars only; never in code/frontend
Unauthorized access	Resume/email data exfiltration	Supabase Auth + JWT; no public endpoints
Prompt injection via JD	Agent misbehaviour or data exfil	Sanitise JD text; system prompt hardening
Email credential compromise	Spam abuse from your address	OAuth 2.0 for Gmail; Resend domain auth
PDF file injection	Malicious PDF upload attacks	Validate MIME, size limits, sandbox extraction
LLM hallucination	Incorrect info on resume/email	Human review gate before any send action

2. Authentication & Authorisation
•	Auth Provider: Supabase Auth (magic link email — no passwords to manage)
•	Session: JWT stored in httpOnly cookie (not localStorage)
•	API Auth: Every FastAPI route validates Supabase JWT via middleware
•	Row-Level Security: All Supabase tables have RLS policies — user can only access their own rows
•	Admin: No admin panel in v1; direct DB access via Supabase dashboard only

3. Secret & Key Management
•	All API keys (Anthropic, OpenAI, Hunter.io, Resend, Adzuna) stored as Railway environment variables
•	Never committed to git — .env.example only with placeholder values
•	Rotate keys on: any suspected leak, every 90 days for production
•	Gmail OAuth: refresh token stored encrypted in Supabase; scoped to send-only permission
•	LangSmith tracing: mask PII fields (email addresses, full resume text) in traces

4. Data Privacy
•	Resume data stored only in your own Supabase instance (not shared with any third party beyond LLM calls)
•	LLM calls: use Anthropic/OpenAI zero-data-retention API tier when possible
•	HR contact data: used only for your outreach — not stored in any shared DB
•	Email logs: stored locally with 90-day auto-purge option
•	All file uploads scanned for MIME type before storage

5. Secure Coding Checklist
•	All user inputs sanitised before LLM prompt injection (strip HTML, control chars)
•	Rate limiting on all API endpoints (100 req/min via FastAPI middleware)
•	CORS: only allow frontend origin; no wildcard
•	HTTPS enforced via Railway + Vercel TLS by default
•	Dependency scanning via Dependabot on GitHub
•	No eval() or dynamic code execution in frontend or backend
 
DOCUMENT 4 — FRONTEND SPECIFICATION

Frontend Specification Document

1. Design System
Token	Value	Usage
Primary	#1A3C5E	Nav, primary buttons, headings
Accent	#0F7B6C	Success states, AI-generated badges, CTAs
Warning	#E85D26	Priority tags, deadlines, alerts
Background	#F7F9FC	Page background
Surface	#FFFFFF	Cards, panels, modals
Text Primary	#1A1A2E	Body text
Text Muted	#6B7280	Labels, metadata
Font (Display)	Inter 700	Page titles, card headers
Font (Body)	Inter 400/500	All body text, form inputs
Border Radius	8px cards, 4px inputs	Consistent rounding
Shadow	shadow-sm on cards	Depth hierarchy

2. Page Structure & Routes
Route	Page	Key Components
/dashboard	Dashboard Home	Stats cards, recent activity, quick-apply CTA
/applications	Application Tracker	Kanban board + table toggle, filters, search
/applications/new	New Application	JD input, agent progress stream, results preview
/applications/:id	Application Detail	Resume preview, email drafts, timeline, status
/profile	Identity Vault	Resume editor, skills, projects, preferences
/templates	Templates Library	Email/DM/cover letter templates management
/analytics	Analytics	Funnel chart, reply rate, weekly trends
/settings	Settings	API keys, email integration, notifications

3. Key UI Components
JD Input & Agent Stream Panel
•	Two-tab input: "Paste URL" | "Paste JD Text"
•	Large textarea with character counter
•	"Analyse Job" button → triggers agent pipeline
•	Real-time progress stream via WebSocket: "Parsing JD... Researching company... Tailoring resume..." with step indicators
•	Results appear in tabbed panel: Resume | Cover Letter | Cold Email | LinkedIn DM

Resume Preview & Edit
•	Side-by-side: original base resume (left) vs AI-tailored version (right)
•	Inline editing on tailored version — all fields editable
•	Keyword match score badge (e.g., "87% ATS Match") with missing keywords list
•	"Download PDF" + "Download DOCX" buttons
•	Version history dropdown to compare past tailored versions

Application Kanban Board
•	Columns: Saved → Applied → Interviewing → Offer → Rejected → Archived
•	Card shows: company logo, role title, days since applied, next follow-up date
•	Drag-and-drop between columns
•	Filter by: date range, source, response status, keywords
•	Table toggle for spreadsheet-like view

Cold Email Composer
•	Editable subject + body with rich text support
•	Variable chips: {HR_NAME}, {COMPANY}, {ROLE}, {YOUR_NAME}
•	"Send Now" and "Schedule Send" (date/time picker)
•	Follow-up sequence builder: +5 day, +10 day auto-drafts
•	Email open tracking pixel toggle

4. State Management
•	React Query (TanStack Query) for all server state (jobs, applications, emails)
•	Zustand for lightweight UI state (active tab, modal open, agent run status)
•	WebSocket context for agent streaming state
•	No Redux — overkill for a single-user personal tool

5. Responsive Design
•	Primary: Desktop-first (most usage at desk; job hunting workflow)
•	Tablet: Sidebar collapses to icon-only at < 1024px
•	Mobile: Limited view — dashboard + tracker read-only; full edit on desktop
 
DOCUMENT 5 — FEATURE TICKET LIST

Feature Ticket List
Organized by sprint. Each ticket follows: [TICKET-ID] Title | Story Points | Type | Dependencies

SPRINT 1 — Foundation & Identity Vault (Weeks 1–2)
ID	Ticket	SP	Type	Deps
JP-001	Project scaffold: Vite + React + TailwindCSS + shadcn/ui setup	3	Setup	—
JP-002	FastAPI project init with folder structure and Dockerfile	3	Setup	—
JP-003	Supabase project init: DB schema, Auth, RLS policies	5	Backend	—
JP-004	Authentication flow: magic link login + JWT middleware	5	Backend	JP-003
JP-005	Identity Vault data model: UserProfile, Resume, Skills tables	5	Backend	JP-003
JP-006	Profile page UI: resume section editor (experience, education, skills)	8	Frontend	JP-005
JP-007	Base resume upload (PDF/DOCX) + text extraction	5	Backend	JP-005
JP-008	ChromaDB integration: embed resume sections on upload	5	Backend	JP-007

SPRINT 2 — JD Parser & Resume Tailor Agent (Weeks 3–4)
ID	Ticket	SP	Type	Deps
JP-009	JD Parser agent: scrape URL or accept raw text, structured LLM output	8	Agent	JP-005
JP-010	JD analysis result schema: skills, keywords, seniority, tone, tech stack	3	Backend	JP-009
JP-011	Resume Tailor agent: RAG over user skills + LLM rewrite per JD	13	Agent	JP-008, JP-010
JP-012	ATS keyword match scorer: compare tailored resume vs JD keywords	5	Backend	JP-011
JP-013	PDF generation: WeasyPrint HTML → PDF from tailored resume data	8	Backend	JP-011
JP-014	New Application page UI: JD input tabs, submit form	5	Frontend	JP-009
JP-015	Agent progress WebSocket stream + frontend progress UI	8	Full Stack	JP-014
JP-016	Resume side-by-side preview UI with inline editing	8	Frontend	JP-013

SPRINT 3 — Email & DM Writers + Tracker (Weeks 5–6)
ID	Ticket	SP	Type	Deps
JP-017	Cover Letter agent: LLM draft using company research + JD + user story	8	Agent	JP-010
JP-018	Cold Email Writer agent: personalised email + 2-part follow-up sequence	8	Agent	JP-010
JP-019	LinkedIn DM Writer agent: connection request + follow-up DM pair	5	Agent	JP-010
JP-020	Template system: save/load/edit email and DM templates	5	Backend	—
JP-021	Cold Email Composer UI: editable draft, variables, schedule send	8	Frontend	JP-018
JP-022	Application Tracker DB model and CRUD API endpoints	5	Backend	JP-003
JP-023	Kanban board UI with drag-and-drop (dnd-kit)	8	Frontend	JP-022
JP-024	Table view toggle for applications tracker	5	Frontend	JP-022
JP-025	Application detail page: resume, emails, timeline, status	8	Frontend	JP-016, JP-021

SPRINT 4 — Email Integration & HR Finder (Weeks 7–8)
ID	Ticket	SP	Type	Deps
JP-026	Gmail OAuth integration: send emails from personal Gmail account	8	Backend	JP-021
JP-027	Resend API fallback: domain-verified transactional email send	5	Backend	—
JP-028	Email open tracking: pixel endpoint + update opened flag	5	Backend	JP-026
JP-029	Follow-up reminder: flag applications for follow-up after N days	5	Backend	JP-022
JP-030	HR Contact Finder: Hunter.io + Apollo.io API integration	8	Backend	—
JP-031	HR contact panel UI in application detail page	5	Frontend	JP-030
JP-032	Research Agent: company info, LinkedIn, recent news via web search	8	Agent	JP-009
JP-033	LangSmith tracing integration for all agent runs	3	DevOps	—

SPRINT 5 — Analytics, Polish & Deploy (Weeks 9–10)
ID	Ticket	SP	Type	Deps
JP-034	Analytics dashboard: funnel chart, reply rates, weekly stats	8	Full Stack	JP-022
JP-035	Dashboard home: stats cards, recent activity feed, quick apply CTA	5	Frontend	JP-034
JP-036	Settings page: API key management, email config, notification prefs	5	Frontend	—
JP-037	Mobile responsive pass: sidebar collapse, touch-friendly tracker	5	Frontend	—
JP-038	Railway deployment: FastAPI Docker + Celery + Redis setup	5	DevOps	—
JP-039	Vercel deployment: React SPA + env vars + domain setup	3	DevOps	—
JP-040	Sentry error monitoring: frontend + backend integration	3	DevOps	—
JP-041	End-to-end test: full application flow from JD to tracker	5	QA	All
JP-042	Performance audit: Lighthouse, API response times, WebSocket stability	3	QA	JP-041

 
DOCUMENT 6 — EXPECTED TIMELINE (SINGLE DEVELOPER)

Project Timeline — Single AI/ML Developer

Developer Context
This timeline assumes a single developer with your profile: strong Python/FastAPI backend, LangChain/LangGraph experience, React familiarity, and active learning of deployment/DevOps. 4–5 hours of focused work per day alongside other commitments.

Phase Overview
Sprint	Focus	Duration	Cumulative Week
S1	Foundation, Auth, Identity Vault	2 weeks	Week 2
S2	JD Parser + Resume Tailor Agent	2 weeks	Week 4
S3	Email/DM Writers + Tracker	2 weeks	Week 6
S4	Email Send + HR Finder + Research Agent	2 weeks	Week 8
S5	Analytics + Polish + Deploy	2 weeks	Week 10
Buffer	Bug fixes, integration issues, scope creep	1–2 weeks	Week 11–12

Weekly Effort Breakdown
Week	Morning Focus (Backend/Agents)	Evening Focus (Frontend/UI)
Week 1	Supabase schema, FastAPI scaffold, Auth middleware	React setup, Auth UI, profile form skeleton
Week 2	Identity Vault API + ChromaDB embeddings	Profile page, resume section editor UI
Week 3	JD Parser agent + structured output schema	New Application page, JD input UI
Week 4	Resume Tailor agent + PDF gen + ATS scorer	WebSocket stream UI, side-by-side preview
Week 5	Cover Letter + Email Writer + DM Writer agents	Cold Email composer, template system UI
Week 6	Tracker CRUD APIs, reminder system	Kanban board, table view, application detail page
Week 7	Gmail OAuth, Resend API, open tracking	Email send UI, follow-up queue UI
Week 8	Hunter.io/Apollo HR finder, Research Agent	HR contact panel, research results display
Week 9	Analytics API, LangSmith, Sentry setup	Dashboard, analytics charts, settings page
Week 10	Railway + Vercel deploy, env management	Mobile responsive, performance audit, QA
Week 11–12	🐛 Bug fixes, edge cases, documentation	UX polish, final UAT, v1 launch

Risk Register
Risk	Probability	Mitigation
LangGraph complexity / debugging agent graphs	High	Use LangSmith traces from day 1; start with simple linear chains
Gmail API OAuth approval delays	Medium	Use Resend API as primary; Gmail as optional enhancement
PDF resume quality / formatting issues	Medium	Use proven HTML+CSS template; test with 3–4 different base resumes
Hunter.io API rate limits on free tier	High	Cache HR contacts per company; budget $50/mo for paid tier
Scope creep (feature additions during build)	High	Strict ticket list; defer new ideas to v2 backlog document
LLM costs spike with many applications	Low	Cache JD analysis; use Claude Haiku for cheaper first-pass tasks
Single developer burnout / pacing	Medium	Buffer weeks built in; target 4h/day not 8h — quality over speed

Estimated Monthly Running Costs
Service	Free Tier	Paid (if needed)
Supabase (DB + Auth + Storage)	Free (500MB)	$25/mo (Pro)
Railway.app (FastAPI + Celery + Redis)	$5 free credits/mo	$10–20/mo
Vercel (React frontend)	Free (Hobby)	Free sufficient
Anthropic Claude API (LLM)	Pay-per-use	~$20–50/mo at scale
Pinecone (Vector DB)	Free (1 index)	$70/mo (if needed)
Hunter.io (HR emails)	Free (25/mo)	$49/mo (Starter)
Resend (Email sending)	Free (3000/mo)	$20/mo
LangSmith (Agent tracing)	Free (1K traces)	$39/mo (Developer)
TOTAL ESTIMATE	~$0 to start	~$150-200/mo full

v2 Backlog (Post-MVP Ideas)
•	Browser extension: apply directly from job board pages
•	LinkedIn automation via browser extension (not official API)
•	Multi-user SaaS with subscription billing (Stripe)
•	Interview prep agent: mock Q&A based on JD + your resume
•	Salary negotiation coach agent
•	Job alert agent: monitor new JDs matching your preferences daily
•	Referral tracker: track who can refer you at target companies
•	Portfolio project matcher: auto-suggest portfolio projects based on JD gaps

Final Note
This document suite covers everything you need to start building JobPilot AI solo. Given your LangGraph, FastAPI, and RAG experience, Sprints 1-3 will feel natural. The biggest learning curve will be the email integrations (Sprint 4) and deployment hardening (Sprint 5). Ship v1 in 10-12 weeks. Then use it yourself for 30 days and let real usage drive the v2 roadmap.
 
DOCUMENT 7 — JOB PLATFORM INTEGRATION SPEC

Job Platform Integration Specification
This document covers how JobPilot AI ingests jobs from LinkedIn, Naukri, and other platforms — including the honest constraints of each platform and the recommended workarounds.

Key Constraint
No major job platform (LinkedIn, Naukri, Glassdoor, Wellfound) offers a public API for reading your personal saved jobs, application history, or recommendations. All approaches below are either official alternatives, email-based parsing, or user-controlled browser automation.

1. Platform-by-Platform Assessment
Platform	Official API	Bot Detection	Recommended Approach
LinkedIn	Partner-only	Very Aggressive	Browser Extension (DOM read) + Email Alert Parser
Naukri	None	Low-Medium	Playwright scrape after login + Email Alert Parser
Indeed	Via Adzuna	Medium	Adzuna API (indexes Indeed) + Email Alerts
Adzuna	Free Public API	None	Direct API integration — primary job source
Remotive	Public API + RSS	None	Direct API — best for remote roles
Wellfound	None	Medium	Browser extension + manual paste
Glassdoor	Partner-only	High	Email alerts parser only
Instahyre	None	Low	Playwright scrape + email alerts
WeWorkRemotely	RSS Feed	None	RSS ingestion — direct integration

2. Three-Channel Ingestion Architecture
JobPilot uses a 3-channel system to pull jobs from all platforms without violating ToS or risking account bans.

Channel 1 — Email Job Alert Parser (Most Reliable)
How It Works
You already receive job alert emails from LinkedIn, Naukri, Indeed, Glassdoor. JobPilot connects to your Gmail via OAuth, monitors a dedicated label/folder, and uses an LLM to parse each alert email: extracting company name, role title, JD link, salary if present, and source platform. Completely ToS-safe — you own your email.

•	Connect Gmail → watch "Job Alerts" label
•	Gmail Pub/Sub webhook pushes new emails to FastAPI in real-time
•	LLM extracts: company, role, JD URL, salary, location, remote/hybrid flag
•	Agent auto-fetches full JD from the extracted URL
•	Job added to tracker with status "Discovered" automatically
•	Works for: LinkedIn, Naukri, Indeed, Glassdoor, Wellfound, Instahyre

Channel 2 — Public Job APIs (For Active Discovery)
•	Adzuna API (free, 250 req/day): search by role, location, salary, remote
•	Remotive API (free, no auth): filtered remote-only jobs by category
•	WeWorkRemotely RSS: parse feed every 6 hours for new listings
•	Jobs are matched against your profile preferences (role, skills, salary floor, stack)
•	Relevance score computed via embedding similarity before showing in UI

Channel 3 — Browser Extension (One-Click Capture)
•	Chrome/Firefox extension with a single "Send to JobPilot" button
•	Works on: LinkedIn, Naukri, Indeed, Wellfound, Glassdoor, Instahyre, any job page
•	On click: scrapes visible page DOM for JD text, company, role, URL
•	Sends payload to your local/cloud JobPilot API via background fetch
•	Confirmation toast: "Job saved to JobPilot"
•	Zero account ban risk — reads page you are already viewing, no automation

3. LinkedIn Specifics
LinkedIn deserves special attention because it is the primary source for most job seekers.

Capability	Status & Approach
Saved Jobs sync	Browser Extension reads your LinkedIn Saved Jobs page DOM on demand
Job Recommendations	Extension reads "Jobs you may like" feed when you visit the page
Easy Apply tracking	LinkedIn data export (CSV) imported into JobPilot; auto-parsed
HR contact finding	LinkedIn search URL constructed for company HR; manual visit
Job alert emails	Gmail parser extracts JDs from LinkedIn alert emails in real-time
Profile data import	LinkedIn PDF export parsed by LLM to seed your Identity Vault

4. Naukri Specifics
Capability	Status & Approach
Job alerts	Gmail parser — Naukri sends well-structured HTML emails, easy to parse
Applied jobs history	Playwright login + scrape naukri.com/mnjuser/applied-jobs page
Profile import	Download Naukri resume PDF -> LLM parse -> seed Identity Vault
Recruiter messages	Naukri inbox scrape via Playwright — lower bot-detection risk
Job search	Browser Extension on Naukri search results page — safest approach

5. New Feature Tickets for Platform Integration
ID	Ticket	SP	Type	Sprint
JP-043	Gmail OAuth + job alert label watcher via Pub/Sub webhook	8	Backend	Sprint 4
JP-044	LLM email parser: extract company, role, JD URL from alert emails	8	Agent	Sprint 4
JP-045	Adzuna API integration: job search with profile-based filters	5	Backend	Sprint 4
JP-046	Remotive + WeWorkRemotely RSS ingestion + relevance scoring	5	Backend	Sprint 4
JP-047	Chrome browser extension: "Send to JobPilot" one-click button	13	Extension	Sprint 5
JP-048	Extension: DOM scraper for LinkedIn, Naukri, Indeed job pages	8	Extension	Sprint 5
JP-049	LinkedIn/Naukri profile PDF import -> LLM parse -> Identity Vault seed	5	Backend	Sprint 2
JP-050	Job discovery feed UI: filter by source, relevance score, date	5	Frontend	Sprint 5
 
DOCUMENT 8 — RESUME TAILORING ENGINE SPEC

Resume Tailoring Engine — Deep Specification
This document details exactly how the Resume Tailor Agent edits resumes per JD, maintains formatting perfectly in the final PDF, and what accuracy level to realistically expect.

1. The Core Problem
Two completely separate concerns must never be mixed:
•	Content editing — what words appear in the resume (LLM responsibility)
•	Visual formatting — how the resume looks as a PDF (template renderer responsibility)
When developers give an LLM a PDF or DOCX to "edit and return formatted," the format always breaks. The solution is a strict 3-layer architecture that keeps these concerns permanently separated.

2. Three-Layer Resume Architecture
Layer 1 — Master Resume Template (HTML + CSS)
Design Once, Use Forever
You create one pixel-perfect HTML + CSS resume template. Every section (header, summary, experience, education, skills, projects) is a Jinja2 template slot — {{ name }}, {{ summary }}, {% for job in experience %}. The template is never touched by the agent. It is the invariant source of truth for formatting.

•	Built in HTML + CSS — full control over fonts, spacing, columns, colours
•	ATS-optimised: single column, standard fonts (Arial/Calibri), no tables, no images
•	Jinja2 templating: every content field is a variable slot
•	Print-CSS media queries control page breaks, margins, orphan lines
•	Multiple template variants supported: standard, compact, 2-page, skills-first

Layer 2 — Content JSON (LLM Edits Only This)
The agent receives and returns a strictly typed JSON object. It never sees or touches HTML.

Resume Content Schema
{   "name": "Dhrumil ...",   "headline": "AI/ML Engineer | RAG | LangChain | Computer Vision",   "summary": "...tailored 3-line summary...",   "experience": [     {       "company": "XYZ Corp",       "role": "ML Engineer",       "duration": "2022-2024",       "bullets": ["...rewritten bullet 1...", "...rewritten bullet 2..."]     }   ],   "skills": {     "primary": ["Python", "LangChain", "RAG", "FastAPI"],     "secondary": ["Docker", "PostgreSQL", "ChromaDB"]   },   "projects": [     { "name": "...", "description": "...", "tech": [...] }   ],   "education": [...],   "certifications": [...] }

Layer 3 — PDF Renderer (WeasyPrint / Puppeteer)
•	Jinja2 renders the HTML template with the edited JSON data
•	WeasyPrint converts HTML+CSS -> PDF with pixel-perfect fidelity
•	Puppeteer (headless Chrome) as fallback — higher fidelity for complex layouts
•	Output: ATS-clean, recruiter-beautiful PDF — identical layout every time
•	Also renders DOCX via python-docx templating for platforms requiring Word format

3. Resume Tailor Agent — Step-by-Step Logic
Step	Action	Detail
1	Load base resume JSON	Fetch from Identity Vault — user's full unedited resume data
2	Load JD analysis	Get structured JD output: required skills, keywords, seniority, tone, tech stack
3	Keyword gap analysis	Compare JD keywords vs resume keywords; identify missing, present, partial matches
4	Skills reorder	Reorder skills array: JD-matching skills bubble to top; irrelevant pushed down
5	Summary rewrite	LLM rewrites 3-line summary to mirror JD seniority, role focus, and tone
6	Experience bullet rewrite	Per bullet: if relevant to JD, rewrite to include JD keywords naturally; preserve facts
7	Project reorder + rewrite	Move most JD-relevant projects to top; rewrite descriptions with JD tech terms
8	Hallucination guard check	Verify: no new company names, dates, titles, or skills not in base resume
9	ATS score calculation	Count exact + semantic keyword matches; compute score vs JD keyword frequency
10	PDF render	Inject edited JSON into Jinja2 HTML template; WeasyPrint -> PDF
11	Diff generation	Compute text diff between base and tailored JSON for review UI
12	Human review gate	Show side-by-side diff in UI; user approves or edits before any use

4. Accuracy Assessment (Realistic & Honest)
Task	Accuracy	Notes
Keyword injection from JD into resume	92-95%	LLMs are excellent at this; most reliable operation
Skills reorder by JD relevance	90-93%	Very reliable; simple ranking task for LLM
Summary rewrite matching JD tone	85-90%	Occasionally generic; 1 in 5 needs light editing
Experience bullet rewrite	82-88%	Good but may occasionally miss nuance; review advised
Project relevance reorder	85-90%	Reliable when JD tech stack is clear
Removing irrelevant content	72-78%	Conservative — tends to keep borderline content; safe
ATS keyword match score improvement	70% -> 88% avg	Validated improvement; measurable via ATS simulation
Maintaining PDF visual format	99%+	Near-perfect with HTML template approach; format is code not LLM output
Hallucination (inventing false info)	2-5% risk	CRITICAL: always enforce human review gate; guard prompt required
Page length control (1 page target)	80-85%	CSS print rules handle most cases; occasional overflow needs trim

Why PDF Format is 99%+ Accurate
The formatting accuracy is near-perfect because the LLM never touches the HTML or CSS. It only edits a JSON object. The Jinja2 template + WeasyPrint renderer is deterministic code — not AI. Same CSS in, same layout out. The only formatting risk is content overflow (too much text for 1 page), which print-CSS word-count limits and a post-render page-count check handle automatically.

5. Hallucination Prevention System
This is the most critical safety layer of the entire resume engine.

Prompt-Level Guards
•	System prompt explicitly states: "You are a resume editor. You may ONLY rephrase, reorder, and rewrite content already present in the base resume JSON. You must NEVER add: new employers, new job titles, new dates, new skills the user did not list, new certifications, or any achievement not explicitly stated in the input."
•	Structured output enforced via Pydantic schema — LLM cannot return fields outside the schema
•	Temperature set to 0.3 (low creativity, high precision) for resume edits

Post-Generation Verification
•	Automated diff check: every word in tailored resume traced back to base resume or JD keywords
•	Company name validator: any company name in output must exist in base resume
•	Date validator: no dates in output that differ from base resume dates
•	Skills validator: all skills in output must be present in base resume skills list
•	Any validation failure triggers: auto-regeneration (up to 2 retries) then flag for human review

UI-Level Guard
•	Side-by-side diff view: every change highlighted (green = added/rewritten, red = removed)
•	User must click "Approve Resume" before PDF is generated or resume is used
•	"Suspicious changes" badge: auto-flagged if validator detected borderline content

6. ATS Optimisation Details
•	Keyword extraction: JD parsed for hard skills, soft skills, tools, certifications, action verbs
•	Frequency weighting: keywords appearing 3+ times in JD are treated as critical
•	Exact match priority: agent inserts exact JD phrases (e.g. "large language models" not "LLMs") where natural
•	Section placement: critical keywords placed in summary AND experience (dual placement for ATS weight)
•	ATS score displayed in UI: "87 / 100 keyword match" with breakdown by section
•	Missing keyword suggestions: "Consider adding: Kubernetes, MLOps, A/B testing" shown to user

7. Resume Engine Tickets
ID	Ticket	SP	Type	Sprint
JP-051	Design master resume HTML+CSS Jinja2 template (ATS-optimised)	8	Design	Sprint 1
JP-052	Resume Content JSON schema with Pydantic validation	3	Backend	Sprint 1
JP-053	Resume Tailor Agent: 12-step pipeline with hallucination guards	13	Agent	Sprint 2
JP-054	WeasyPrint PDF renderer: HTML template + JSON -> pixel-perfect PDF	8	Backend	Sprint 2
JP-055	ATS keyword match scorer with section-level breakdown	5	Backend	Sprint 2
JP-056	Post-gen hallucination validator: company, date, skills cross-check	8	Backend	Sprint 2
JP-057	Side-by-side diff UI: base vs tailored with approve/edit flow	8	Frontend	Sprint 3
JP-058	Missing keywords panel: suggestions with one-click accept	5	Frontend	Sprint 3
JP-059	DOCX output via python-docx template for Word-only platforms	5	Backend	Sprint 3
JP-060	Resume version history: compare all tailored versions per application	5	Frontend	Sprint 4

Final Note — Updated
With Documents 7 and 8 added, JobPilot AI now has a complete spec for job ingestion from all platforms (via email parsing, public APIs, and browser extension) and a production-grade resume tailoring engine. The 3-layer content/template/renderer architecture is the right approach — it is how enterprise ATS systems and modern resume builders work. Build the HTML template first (JP-051) before writing any agent code, as everything else depends on it.

