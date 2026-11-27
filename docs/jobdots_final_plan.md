# JobDots — Final End-to-End Plan (v1.9, 27 Nov 2026)

Owner: Dhrumil. Single-user personal job-hunting assistant. Python backend, React frontend, local-first hosting on his laptop (Render with credit later), Postgres + pgvector (local; Neon in Phase B), Groq + local Ollama models, backups to his Google Drive.
Status of claims: items marked **[unverified]** come from memory or third-party sources and must be checked before relying on them.

### v1.4 changes (from the codebase audit and the 24 Nov decisions)

1. **Existing JobPilot data is preserved** (48 tracked applications on 24 Nov, 44 applied): immutable raw export plus an idempotent import into JobDots (section 5.1; Day 0 and Day 2).
2. **Google and GitHub login stay**, rebuilt on the backend with a single-owner allowlist, no Supabase (section 4.1; Day 2). The bearer token stays as break-glass, and the extension and Telegram keep their own credentials.
3. **The existing Postgres queue is the durability layer.** LangGraph is optional (Supervisor routing, Reviewer revise loop), with no Postgres checkpointer requirement (sections 4, 7.1).
4. **Per-case concurrency replaces the old one-running-job-per-user lock**, which would have serialised all experts (section 4, Day 2).
5. LangChain, Chroma, Supabase, Celery/Redis and LangSmith are removed; reuse and removals are listed in section 16 and in `jobdots_codebase_triage.md`.
6. New **Day 0** (freeze, secret scan, export, legacy snapshot) before Day 1.

### v1.8 changes (26 Nov: search provider)

1. The search API is **Brave Search API** (`BRAVE_API_KEY`). Both endpoints JobDots needs were checked live on 26 Nov: **Web Search** (`/res/v1/web/search`) and **LLM Context** (`/res/v1/llm/context`).
2. **Recon** finds LinkedIn profiles through Web Search with an inline **Goggle** that keeps only `linkedin.com` results (`$discard` then `$site=linkedin.com`) and asks for `extra_snippets`. It reads names and titles from the result title and snippets only and never opens LinkedIn pages.
3. **Researcher** may add LLM Context results as extra cited sources for a company brief. These are pre-extracted page text with URLs, so the existing citation rules apply unchanged.
4. **Hunter is optional.** Its signup refuses webmail addresses, so Recon works without it: it uses emails published on company pages, plus a recipient Dhrumil sets himself. When `HUNTER_API_KEY` is present, Hunter is used for email lookup.
5. Brave's MIT-licensed API reference skills (`brave-web-search`, `brave-llm-context`) are in `.claude/skills/` for the coding agent. The key stays in `.env` and is never put into the agent's environment.
6. **As built on Day 6:** Recon is **deterministic** (rules, no model). It accepts a person only with evidence that they work at the company now: the result title, the profile's "Experience" line, or a first-person post. It checks the company with an exact match, so "Acme Infotech" is not "Acme AI". A labelled eval (`recon_cases`) requires zero wrong-company people. The local 8B model stays an option for ambiguous titles. Supervisor runs Recon **after Researcher and before Tailor**, so Email Outreach can write to the recruiter or hiring mailbox Recon found. Searches are capped per run and per day (`recon_searches_per_run`, `recon_searches_per_day` in `policy.yaml`).

### As built on Day 12 (27 Nov: Comp Analyst)

1. **Comp Analyst** (active) runs after Researcher in the Supervisor graph and saves a `comp_report`.
   - **Searches:** the JD's own band, plus up to `comp_searches_per_run` (3) Brave searches, capped by `comp_searches_per_day` (15). Queries hold the company, the role and a country, never your own details. When the JD names no location, the country comes from your home country, as just "India".
   - **The model picks; code checks.**
     - Code splits every source into sentences and keeps those with a pay figure (`app/comp/money.py`). The model only picks sentence ids and says what each describes; it can't add or change a figure.
     - Code reads the amounts: LPA, lakhs, crore, ₹/$/€/£, k, per month, ranges with a "(25th percentile)" note. Per-hour figures and monthly restatements of the same pay are ignored.
     - Code keeps only figures stated word for word in their source. One posting syndicated to several sites counts once. Outliers are judged within one currency, never across currencies.
   - **Market band** is the middle half (25th–75th percentile) of all reported figures in your home currency.
   - **Suggested ask** runs from the band's midpoint (or your vault floor, whichever is higher) to its top. The JD's own band comes first. Figures only in another currency, such as a US band, produce a note to ask the recruiter, not a converted ask.
2. **Answerer:** pay questions keep your confirmed vault figure, always marked to check, with the Comp Analyst's band and suggested ask in the note. If your vault has no figure, the answer stays "Needs you" with the research beside it. A model never answers a pay question.
3. **Evals:** `comp_cases` requires zero invented or altered figures accepted, and every pay phrasing and quote check right; the phrasings found live were added to it. A pay card renders in the case thread.
4. **Live, on a real Lead AI Engineer case in India:** market 18.8–31.1 LPA from 3 sources (Glassdoor, Salary.com, AmbitionBox).
   - Earlier runs found and fixed: a syndicated US band counted three times; a USD band offered as an ask; per-hour and per-month restatements read as salaries; a currency-mixing outlier filter.

### As built on Day 11 (27 Nov: the outreach loop)

1. **DM Outreach** (active), the second half of the LinkedIn loop: invite (Connector) → you send it → accepted (Inbox reads LinkedIn's email) → wait `min_hours_accept_to_dm` → message (DM Outreach) → you send it from the queue.
   - **Routine `after_accept`** (daily 11:00): one message to each person who accepted long enough ago and hasn't had one.
   - **On a case** (a Supervisor route after Connector, producing `dm_set`, migration 0009): referral asks (`referral_request`) to people Recon found who are already your connections there, within `max_people_per_company`.
   - Reviewer checks every message, and only those it passes become actions. All of them go through the side panel's LinkedIn queue and Telegram.
2. **Caps:** DMs and referral asks share `linkedin_dms_per_day`, counted together in Courier's gate. A DM never goes out without a recorded acceptance and the wait. The cooldown still applies to referral asks, but not to the thank-you after an acceptance you asked for.
3. **End-to-end dry run** (`tests/integration/test_outreach_loop_db.py`): a fictional case runs through every step, with the model and Gmail faked:
   - Recon's list → Connector invitations → approve, open, send → a third invitation refused by the daily cap;
   - LinkedIn acceptance email → Inbox → no DM before 24 hours → one DM after;
   - the shared message cap holds back the referral ask;
   - contact stages and `contact_touch` rows are checked at every step.
4. The `connector_notes` eval now includes DMs and referral asks.

### As built on Day 10 (27 Nov: Inbox and Calendar)

1. **Inbox** (active) runs as two routines. Interval routines are new (`{"kind": "every", "minutes": 30}`), as is routine kind `expert` with a `task` (migration 0008).
   - `poll` every 30 minutes: Gmail read-only searches limited to the people and company domains you emailed through JobDots, plus LinkedIn's "accepted your invitation" notifications. Other mail is never fetched, and bodies are never stored (`inbox_message` keeps a snippet).
   - Messages are matched to a case by Gmail thread (Courier now saves `action.thread_id`), then by sender, then by company domain (webmail never counts as a company).
   - Rules classify each message (`app/inbox/classify.py`); only the new part of a reply counts, not the quoted history:
     - reply: the case moves to Replied and the contact to replied;
     - interview: the case moves to Interviewing; the model reads a specific time, if there is one, and a `create_calendar_event` is proposed for approval;
     - rejection: a note only; the case stays open;
     - auto-reply: noted;
     - accepted: `contact.accepted_at` is set and the contact becomes `accepted`, which is what DMs wait for.
   - A reply withdraws pending follow-ups to that email.
   - `follow_up` daily at 10:00: one templated follow-up in the same Gmail thread (`threadId`, `In-Reply-To`), after `follow_up_after_days` (default 5) without a reply. Reviewer checks it and it needs your approval.
2. **Follow-ups are policed in Courier's gate, not just in Inbox.** A payload with `follow_up_of` may skip the 14-day cooldown only when the original is a sent email to the same address and no follow-up to it has gone out. Anything else is refused, so an agent can't use "follow-up" to dodge the cooldown.
3. **Calendar executor** (Courier): approved events go on your primary Google Calendar with no attendees. The event id is derived from the action, so retries and crash recovery never create a second event.
   - It needs the `calendar.events` scope: reconnect with `python scripts/connect_google.py connect`, with the Google Calendar API enabled in the same Google Cloud project.
   - Until then, approved events wait with "Not added yet: …" on the case.
4. Telegram and the web show calendar cards ("Approve and add").

### As built on Day 9 (27 Nov: command center and dashboards)

1. **Web app is now JobDots-first.** The left rail is the **expert roster**: live `ExpertAvatar` and one line of what each expert last did. Below it: Command, Cases, Approvals (with a count), Contacts, Answer bank and Dashboard. The JobPilot pages stay under "More".
2. **Command** (`/`): paste a JD to hand it to Supervisor (`/experts/cases/quick`). It also shows a deck of what needs you, grouped by kind, cases in motion, and the experts' latest steps.
3. **Case thread** (`/cases/:id`): one timeline of events and typed cards:
   - brief with sources, people, resume diff (approve/reject, open the PDF), email draft, invitations, answers;
   - approval cards pinned at the top;
   - a recipient form when the email has no address;
   - "ask an expert again" buttons, including Propose LinkedIn invitations.
4. **Approvals** (`/approvals`): the same approval cards stacked by kind, plus "check these first" for send results that are unknown and a Blocked group.
5. **Editing a draft from the web** goes back through the Reviewer (`app/experts/rereview.py`). Before this, an edit left it at `proposed`, where it could never be approved.
6. **Contacts**, **Answer bank** (search, versions, delete), the **expert page** (spec, routines in words, recent steps), and the **Dashboard** (`GET /api/v1/dashboard`):
   - Pipeline this week and all time; imported applications count only in all time;
   - Live Ops: kill switch, quiet hours, what's running, failures from the last day with credentials scrubbed, sends against caps, model spend against the budget.
7. **Deviations:**
   - The approval deck is CSS (stacked edges), not React Bits `Stack`; numbers are plain, not `CountUp`. That's one less dependency, and nothing animates without a reason.
   - There is no expert-browser preview or takeover yet, because no expert drives a browser: Researcher and Recon use APIs, and Applicant runs in your Chrome.

### As built on Day 8 (27 Nov: Applicant, Connector, LinkedIn queue)

1. **Applicant** fills the open form from the side panel (**Fill the form**), through the existing form engine: exact options only, consents never ticked, no submit path.
   - It attaches the case's latest tailored resume PDF that you haven't rejected. The PDF is hash-checked on the server and again in the browser.
   - The Answerer gives the resume file field the value `__resume__`. A field labelled resume/CV gets it; when no field says resume, the first file field gets it as a guess and is flagged for you to check. Cover letters, portfolios and other files are left for you.
   - Each fill is one `form_filled` event on the case timeline: what was filled and what to check.
   - Earlier the same day, the panel gained **Fill the form** (it had only copied answers) and **marks a case applied** when it sees the employer's confirmation page. It also has an "I submitted it" button and an undo. `applied_at` is stamped on the first move to applied.
   - Coverage: locally authored Greenhouse, Lever and Ashby forms (`tests/browser/ats-fill.spec.cjs`), including Ashby's hidden upload input.
2. **Connector** (now active) runs after Email Outreach in the Supervisor graph and saves an `invite_set` artifact (migration 0007).
   - It drafts a note for each person Recon suggested who is reached on LinkedIn: not reachable by email, not already a connection, not blocked.
   - It stays within `max_people_per_company`, counting people already contacted and invitations still pending.
   - Notes stay under LinkedIn's 200-character limit for a free account. Over-long notes get one shortening pass from the model, then code drops trailing sentences.
   - Reviewer's new `check_linkedin` applies the email claim checks plus a real profile URL, the note length and the cooldown. Only notes it passes become `send_linkedin_invite` actions; blocked ones are reported on the card, so drafting mistakes never trip the refused-actions circuit.
   - The new `connector_notes` eval requires zero bad notes passing.
3. **LinkedIn queue** in the side panel. Every action goes through Courier's gate (`start_execution`) and is recorded on the contact and the case.
   - You approve (the `extension` channel, bound to the exact text you saw), reject, or edit (the Reviewer checks the edited text again).
   - **Open profile and copy note** checks the caps, quiet hours, cooldown and kill switch first, counts against today's cap, then opens the profile with the note on the clipboard.
   - You send it on LinkedIn yourself and click **I sent it** or **I didn't send it**.
   - Telegram shows LinkedIn cards with "Approve and queue". `POST /experts/cases/{id}/connect` runs Connector manually.
4. **Structured output** retries once with `reasoning_effort: low` when a Groq gpt-oss model spends its whole budget reasoning and returns no JSON. This was seen live on Connector, and the fix covers every expert.
5. **Deviations from the plan:**
   - The extension never clicks anything on LinkedIn. "One click" opens the profile with the note copied; you press Connect and Send yourself. Automating LinkedIn's own buttons would break its terms of use and the `scrape_behind_login: never` rule.
   - DMs use the same queue, but they need an accepted invitation (`min_hours_accept_to_dm`), which arrives with Inbox's acceptance watcher on Day 10. DM drafting stays on Day 11.
   - The panel stays plain JavaScript; the queue didn't need Vite + TS.

### As built on Day 7 (26 Nov: extension side panel + Answerer)

1. **Answerer** decides each form answer by question kind (rules, checked by the `answerer_cases` eval):
   - **From the fact vault:** profile facts. Pay, visa and work-authorization answers are always marked to confirm.
   - **From the answer bank:** reused at ≥ 0.9 similarity (pgvector, local `embeddinggemma`; word overlap if Ollama is down), adapted at 0.75–0.9, otherwise drafted by the model from vault facts, the brief and the JD.
   - **Company-specific answers** are never reused verbatim.
   - **Never answered:** legal agreements, consents and files are always handed to you. Self-identification is answered only from your saved answer; otherwise it is handed to you, with "decline" suggested when the form offers it.
2. **Answer bank:** approving answers in the side panel saves new and edited ones as new versions. `GET/DELETE /api/v1/answer-bank` serves the Day 9 sheet.
3. **Extension:**
   - a Chrome **side panel** (capture JD, read questions, review answers with worded badges, approve)
   - side panel routes `/extension/page|capture|questions|answer-set|answer-set/approve`, callable only from the panel
   - page access is an optional `https://*/*` permission you grant once
4. **Deviations from the plan:**
   - The side panel is plain MV3 JavaScript, like the existing extension, not a Vite + TypeScript build. This avoids a build step for "load unpacked". The move to Vite + TS can come with Day 8's send queue if it earns its keep.
   - The panel shows the Answerer's status as a worded step line instead of the `ExpertAvatar`, because bot-avatars needs React and a bundler.

### v1.7 changes (26 Nov: React Bits)

1. **React Bits** (reactbits.dev, MIT + Commons Clause: free inside JobDots, never resold or redistributed on its own) is a source registry for three Day 9 patterns: **Stack** for the approval deck, **CountUp** for Pipeline dashboard numbers, **AnimatedList** for the activity stream. Components are copied in through the shadcn registry `@react-bits` (`frontend/components.json`), carry a notice header, are adapted to our tokens and Lucide icons, and are wrapped. Its backgrounds, 3D and glitch effects and Pro tier are not used.
2. The **shadcn MCP server** (`.mcp.json`, pinned `shadcn@4.23.0`, run from `frontend/`) lets the coding agent search and add registry components. Rules are in the `jobdots-agentic-ui` skill, section 9.

### v1.6 changes (26 Nov: expert avatars)

1. Expert avatars use **`bot-avatars`** (Libraries.dev, MIT licence, `npm install bot-avatars`, pinned 0.2.2, no runtime dependencies, React 18+): lit, rounded canvas bodies that look around, hop and sleep. It replaces the plan for an in-house inline SVG kit, and bloub is no longer a reference (its licence was never confirmed).
2. Each expert gets its own body shape (and a few an accessory); the library's three motion states (`default`, `working`, `sleeping`) carry idle, working and paused, and a small worded badge carries the other states (section 6.2).
3. Other **Libraries.dev** components (MIT npm packages only) have narrow, named jobs: `thinking-orbs` for the one "composing" moment in a thread, `border-beam` on the single approval card waiting for him, `distortion-waves` for the sign-in → workspace transition. Its Models and Pro content are not used (paid licence for commercial use). Rules and the motion budget are in the `jobdots-agentic-ui` skill, section 9.

### v1.5 changes (25 Nov: agentic UI)

1. The UI is organised around a **roster of persistent experts**, not a chat history. The sidebar lists Supervisor and the experts with live avatars (section 6).
2. **Animated expert avatars carry state** (idle, working, waiting for approval, needs hand-off, blocked, done, paused); hover shows the current step. No spinners for agent activity (section 6.2).
3. The expert's browser has three levels: **status, preview, takeover**. Takeover is the `hand off` tier (section 6.2).
4. Threads are **heterogeneous**: messages, grouped activity, system events, typed cards and approval cards on one timeline. Routines live in the expert's panel.
5. Every frontend task uses two project skills: `frontend-design` (visual identity) and `jobdots-agentic-ui` (agent patterns), both in `.claude/skills/`.

---

## 0. Product in one paragraph

JobDots does what Dhrumil does by hand: take a job description, tailor the resume, apply, answer the extra questions, find the people at the company (recruiter, hiring manager, CEO, CTO), ask for referrals, send cold email and DMs. Each task has an expert agent. Every outward action (email, DM, form submit, referral request) is proposed by an agent, checked in code, and executed only after Dhrumil approves. The spine of the product is the **job case**.

---

## 1. What was proposed vs. what we chose

| Topic | Original proposal | Final choice | Why |
|---|---|---|---|
| Product shape | JobPilot as a multi-user SaaS | JobDots: single-user personal assistant | He does the hunt himself; SaaS hardening (multi-tenant, onboarding, landing page) is frozen. |
| Agent structure | One pipeline of 8 stages | Supervisor + expert agents passing typed artifacts | One expert per task, predictable handoffs, easier to test. |
| Safety | Prompt rules ("verify before sending") | **Code-enforced** policy engine + Courier | OpenBots and dots both show prompt rules are not enforcement; prompt injection is unsolved. |
| Sending | Agent calls send tools | Agents only *propose*; **Courier** (deterministic code) executes approved, frozen payloads | Separates thinking from side effects. |
| Resume | Dual renderers (HTML/WeasyPrint + LaTeX) | Master `.tex` → structured edits → Tectonic → diff approval. HTML renderer kept as fallback | He edits in Overleaf; Overleaf has no free API, so he opens the same `.tex` there manually. |
| DB | Supabase | **Neon** + pgvector | His choice; pgvector holds the answer bank. |
| LLM | Claude Sonnet (costing) | **Groq, gpt-oss-120b**, per-agent model config; local model later | His choice; LLM cost becomes negligible. |
| Platform access | Desktop apps / cloud browser / Daytona | **Dedicated Chrome profile + own extension** for LinkedIn/X/Reddit; cloud browser only for public pages | Sessions stay on his machine; no new-device logins; no passwords near the model. |
| Integrations | Composio for everything | **Hybrid**: direct Gmail, Calendar, Hunter, search; Composio optional for long-tail with minimal payloads | Spike: Composio's Calendar tool needs broader scopes than the raw API; free-plan logs keep payloads up to a year. |
| LinkedIn rules | Prompt knowledge of policy | Prompt policy file **and** `policy.yaml` limits enforced by Courier | Prompts help drafting; only code enforces. |
| Autonomy | Auto-apply | Approve first; autonomy loosens per proven action kind | A wrong send cannot be unsent. |
| UI | OpenClaw/OpenBots-style | OpenBots layout plus **persistent-agent patterns** (expert roster, animated avatars as status, status/preview/takeover, typed cards), **reimplemented** | OpenBots repo has no LICENSE file → don't copy code. Patterns learned from the Grok Bot design write-up; avatars from the MIT-licensed `bot-avatars` package (v1.6). |
| Timeline | 14 weeks | 10 days core + 4 days hardening/custom agents | Coding agents; he has build time. |
| Background engine | Trigger.dev-style | Existing Postgres durable queue (leases, checkpoints, idempotency) | Already built; better than restart-from-scratch runs. |
| Durability layer | LangGraph with a Postgres checkpointer | **The queue's per-stage checkpoints with lease fencing**; LangGraph only where branching helps | The audit showed the queue already survives crashes at stage level; two checkpoint systems would be redundant. |
| Login | Bearer token only | **Google and GitHub login** (backend OAuth, single-owner allowlist) + bearer token as break-glass | His request; also the part that carries over if JobDots later gets real users. No Supabase. |
| Existing data | Not addressed | **Keep all JobPilot data**: raw export (as is) + imported copy in the new schema; delete the old store only after verification | 44 applications already sent; history, drafts and PDFs must not be lost. |
| Memory | Key/value notes | Facts and answers with **provenance**, viewable and deletable | dots lesson. |
| Outreach | One "Networker" agent | **Connector** (invites) + **Email Outreach** + **DM Outreach**, with an acceptance watcher in Inbox; sending stays in Courier executors | Separate prompts per channel; every send still needs approval. |
| Pay questions | Part of Answerer | Separate **Comp Analyst** | Pay research changes per JD, is sensitive, and needs sources and confidence. |
| Interview prep | Not planned | **Interview Buddy** | Prep pack per interview from JD, company brief and the submitted application. |
| Hosting | Render for everything | **Local-first**: Docker Compose on his laptop now (free, zero travel risk); Render (credit) later for 24/7 | Same images run in both. The remote 100 km desktop option was cancelled. |
| Models | Groq for every agent | **Per-agent brains**: small local models for classifiers and embeddings, Groq for quality-critical writing | See 2.2. |
| Tracking | Not specified | Two dashboards: **Pipeline** (applications, outreach funnel) and **Live Ops** (agents, queue, approvals, budgets) | See section 6.1. |

---

## 2. Agents

### 2.1 Roster (12 experts + supervisor + checker + courier executors)

| # | Agent | Job | Hard limits |
|---|---|---|---|
| 1 | **Scout** | Finds fresh jobs daily (routine) and scores them: feeds, alerts, Reddit hiring threads, pasted JDs. | Read-only. |
| 2 | **Researcher** | Company brief (product, stage, news, stack, fit). Feeds Tailor, Answerer, outreach, Interview Buddy. | Public web, read-only. |
| 3 | **Comp Analyst** *(new)* | Pay range per JD: posted range if any, public market data, location/remote basis, his floor from the vault. Output: range, rationale, confidence, sources. | Never sends. Salary form fields are never auto-filled; he confirms the number first. Never invents his current pay. |
| 4 | **Tailor** | Edits master `.tex` per JD, compiles PDF, validates facts. | No web, no send. Validator rejects claims not in the fact vault. |
| 5 | **Answerer** | Application questions from the answer bank; adapts or generates; source badge. For pay fields it uses the Comp Analyst artifact plus his confirmed number. | No legal/EEO/consent answers (hand-off). |
| 6 | **Applicant** | Maps fields and fills forms via the extension; builds the review panel. | Never submits. |
| 7 | **Recon** | Finds recruiters/HR, hiring managers, CEO, CTO, and employees (peers). Assigns `role_class`. LinkedIn URL (Brave search with a LinkedIn-only Goggle), email (public pages; Hunter if configured), X handle. | Read-only public sources; no logged-in scraping. |
| 8 | **Connector** *(new)* | Chooses who to invite next, drafts the connection note within channel limits, paces by caps in `policy.yaml`. Output: invite proposals. | Proposals only. |
| 9 | **Email Outreach** *(split from Networker)* | Cold email to HR/CEO/CTO: subject, personalization, follow-up sequence. | Drafts only. |
| 10 | **DM Outreach** *(split from Networker)* | After acceptance: cold DM for HR/CEO/CTO, referral ask for employees. Later X/Reddit. | Drafts only. |
| 11 | **Inbox** | Classifies Gmail replies; **connection-accepted watcher**; follow-ups; detects interview invites. | Read-only mail token; drafts only. |
| 12 | **Interview Buddy** *(new)* | Prep pack per interview from JD, company brief, the submitted application, and Comp Analyst notes. | Read-only; no sends. |
| — | **Supervisor** | Routes a case between experts; enforces budgets. Mostly deterministic graph. | No external tools. |
| — | **Reviewer** | Checks every draft before you see it: claims vs fact vault, recipient identity, recent-contact status, channel policy. | Read-only; can block or annotate. |

**Courier executors (code, not agents):** Gmail sender (cold email), LinkedIn queue (connection request, DM; one click in your Chrome), Calendar creator, optional X/Reddit/Composio adapters. Every executor runs only approved, frozen payloads.

**Why the senders are not agents.** Sending needs no judgment, and an LLM that can send is exactly what a prompt-injected JD or reply would try to hijack. Outreach agents *draft*; Courier executors *send* after you approve in Telegram or the web app.

**Build waves (so the roster doesn't slow the MVP):**
- Wave 1: Scout, Researcher, Tailor, Recon, Email Outreach.
- Wave 2: Answerer, Applicant, Connector, DM Outreach, Inbox (with the acceptance watcher).
- Wave 3: Comp Analyst, Interview Buddy, then custom agents.

### 2.2 Models per agent ("personal brain", config not code)

Each `agent_spec` has `model` and `fallback_model`. Two endpoint types, both OpenAI-compatible, so one thin client with a different `base_url`: **Groq** (hosted, strong: `gpt-oss-120b`) and **Ollama / llama.cpp** (local, small).

**His hardware**
- Laptop (Ryzen 7 250, 16 GB RAM, 1 TB SSD, RTX 5060 with 8 GB VRAM, Windows 11): runs models in roughly the 4–8B class at 4-bit comfortably. `gpt-oss-20b` may run with partial CPU offload but is tight on 16 GB RAM **[verify]**. `gpt-oss-120b` will not run locally.
- Desktop (32 GB RAM, Quadro P2000): **not used**; that option was cancelled.

**Which brain for which agent**

| Agent | Brain |
|---|---|
| Scout | Local 8B for the first-pass filter and scoring; Groq strong model only for shortlisted roles (after eval) |
| Researcher | Groq strong (synthesis) |
| Comp Analyst | Groq strong |
| Tailor | Groq strong (quality-critical) |
| Answerer | Local small model for question-type detection and retrieval; Groq strong for adapted and company-specific answers |
| Applicant | Local small model for field mapping |
| Recon | Rules only (Day 6): titles and company evidence from search results; a local 8B model only if the eval shows the rules miss too much |
| Connector, Email Outreach, DM Outreach | Groq strong |
| Inbox | Local small classifier (reply type, interview invite); acceptance emails by rules first |
| Interview Buddy | Groq strong |
| Reviewer | Groq strong; a different model family from the writer if available |
| Supervisor | Deterministic graph |
| Embeddings (answer bank) | Local small embedding model via Ollama (free) |

Model examples for the local class: 4–8B instruct models from the Qwen, Gemma or Llama families; pick by testing in Nov 2026, not by name.

**Rules**
1. Day 1: everything on `groq/gpt-oss-120b`. Move an agent to a local model only after it matches the Groq baseline on the eval set.
2. If the local model is unreachable (laptop asleep, Ollama down), the agent falls back to Groq automatically, and the run is marked.
3. Local models are a privacy and cost win for classification only; drafts that people will read stay on the strong model.

### 2.3 Risk tiers (per action kind, in `policy.yaml`)

| Mode | Examples |
|---|---|
| **act** | read public web, save artifacts, compile resume |
| **act with preview** | fill (not submit) form |
| **ask first** | send email, send DM (via extension), submit application, referral request, calendar event |
| **hand off** | CAPTCHA, passwords, 2FA, legal attestations |
| **never** | bulk sends, fake identity, scraping behind a login, anything on the never-list |

Autonomy graduates per action kind (e.g. email auto-send after ~15 approvals with no edits, capped), never globally. Global **kill switch** pauses all Courier executors.

### 2.4 Outreach pipeline (connection → accept → DM or referral)

Per contact, state machine:
`discovered → classified (role_class) → invite_proposed → invite_approved → invite_sent → accepted → message_proposed → message_approved → message_sent → replied | no_reply → follow_up → closed`

- **Who gets what:** HR/recruiter, CEO, CTO → cold DM (and cold email in parallel if Hunter has a verified address). Employee/peer → referral ask.
- **Approval:** Connector and DM Outreach drafts go to Reviewer, then Telegram/web approval. After approval the extension shows a **send queue**; he clicks Send on each item in his own Chrome. No auto-click.
- **Acceptance watcher (Inbox):** parse LinkedIn "accepted your invitation" notification emails from Gmail (read-only), match to the contact, move to `accepted`, trigger DM Outreach. Depends on LinkedIn notification emails being enabled **[verify in his settings]**. Fallback: the extension reads his "Sent invitations"/connections page only when he opens it himself.
- **Caps in `policy.yaml` (he sets the values):** invites/day, invites/week, DMs/day, max people per company, minimum delay between acceptance and DM, no message if a recent touch exists, quiet hours. Connector enforces the connection-note length limit in code **[confirm current limit]**. Start low and raise gradually.
- **No generic spam:** every note and DM must cite something specific from the company brief or the contact's role; Reviewer blocks template-looking drafts.
- **Risk:** LinkedIn's rules restrict automated invitations and messaging. The human-click design lowers, but does not remove, the chance of account restrictions. This is his call; keep volume low and watch for warnings.

---

## 3. Custom agents (new capability)

**Current state:** the six/eight built-ins are fixed. OpenBots lets users create agents; JobDots must too, but safely.

**Design: agents are data.** Every agent, built-in or custom, is an `agent_spec` row:

```
agent_spec:
  id, name, description, owner (builtin|user)
  instructions        (system prompt, markdown)
  policy_notes        (short do/don't file, e.g. linkedin.md rules)
  model               (provider/model + fallback)
  tools               (allowlist from the tool registry)
  inputs / outputs    (typed artifact schemas)
  triggers            (manual | slash command | routine | event)
  action_kinds        (which proposals it may make)
  budgets             (max steps, max tokens, max seconds, per-run and monthly)
  autonomy            (per action kind; capped by global policy)
  status              (active | paused | draft)
```

**Rules for custom agents**
1. They cannot add new action kinds or relax `policy.yaml`. Policy is global and code-enforced.
2. Tools come only from the registry; default is **read-only** tools. Write tools are available only as *proposals* routed through Courier.
3. Every new/edited spec must pass validation (schema + tool allowlist + budget caps) and a **dry-run** (actions recorded but not executed) before activation.
4. Custom MCP tools: **phase 2**, off by default, each gets a per-tool risk tier.
5. Same Reviewer and activity stream apply.

**UI:** Experts page → "New expert" → choose a template (clone a built-in or start blank) → fields above → "Policy preview" (what it can and can never do) → "Test run (dry)" → Activate. Example custom agents: Referral Hunter, Interview Prep Coach, LinkedIn Post Writer, Salary Research.

**Build:** specs are data from Day 3, so the custom-agent UI and validator are Days 11–12.

---

## 4. System architecture

```
                 Browser (React 19 command center)      Telegram (approvals)      Chrome extension (own profile)
                              |  login / bearer token        |  webhook secret          |  extension token
                              v                              v                          v
      +-----------------------------------------------------------------------------------------------+
      |                          FastAPI gateway (Render web service, Docker)                          |
      |   auth • typed events • SSE stream • idempotency keys • rate limits • typed UI cards (JSON)    |
      +---------------------------------------------+-------------------------------------------------+
                                                    |
                                  Supervisor (LangGraph for routing only; durability = Postgres queue checkpoints)
                                                    |
      +-------+--------+--------+--------+---------+--------+--------+--------+
      Scout Researcher CompAnalyst Tailor Answerer Applicant Recon Connector EmailOutreach DMOutreach Inbox InterviewBuddy (+ custom)
                          |  proposals (typed artifacts / action requests)
                          v
                +-------------------------+      +---------------------------+
                |  Reviewer (checker)     | ---> |  Policy engine + budgets  |  policy.yaml, channel policies
                +-------------------------+      +-------------+-------------+
                                                               | approved only
                                                               v
                                                     Approval inbox (web / Telegram)
                                                               | user approves
                                                               v
                                          Courier (deterministic executors)
                          Gmail sender • LinkedIn queue (invite, DM; one click in extension) • Calendar • (X/Reddit, Composio adapter optional)
                                                               |
      Tools layer: Hunter (optional) • Brave Search API • public-web fetch/Playwright (public only) • Tectonic • embeddings
      Data: Neon Postgres (+pgvector) • Render disk/object store for PDFs
      Worker (Render background worker, same image): durable queue, leases, checkpoints, routines
```

**Trust boundaries (dots lessons)**
- Agents never hold tokens. A **token broker** inside the Courier layer holds Gmail/Calendar/Hunter tokens; background Scout/Recon/Inbox get read-only tools enforced in code.
- LinkedIn/X/Reddit sessions live in his dedicated Chrome profile. The extension acts only on frozen, approved payloads. Passwords never reach the model.
- JD text, scraped pages and recruiter replies are **untrusted input**; the lethal trifecta (private data + untrusted text + a send) is broken by requiring approval for every send.
- A sleeping workflow costs nothing while waiting for approval: pending approvals are persisted in Postgres, not polled in memory.

**Action state machine:** `proposed → reviewed → approved → executing → provider_accepted → delivered | failed | cancelled`. Idempotency key on every side effect. Provider-accepted is not delivered.

**Durability:** checkpoint after every step; a crash costs one step. The existing queue (leases with fencing tokens, per-stage checkpoints, retries with backoff, idempotency keys) is the durability layer; LangGraph is not required to persist state. **Concurrency:** the old "one running job per user" lock is replaced by per-case (and per-kind) limits so Scout, Tailor and Inbox can run side by side. **Schedules:** the worker records the last successful run per routine and runs missed ones on start (catch-up-on-wake); Live Ops warns when a routine is stale.

**Budgets:** per-case caps (steps, tokens, seconds), refused-action circuit breaker (stop tasks whose actions keep being refused), monthly LLM spend limit.

### 4.1 Authentication (single owner, Google and GitHub login)

- **Providers:** Google (OpenID Connect) and GitHub (OAuth), implemented in the FastAPI backend (Authlib or equivalent). No Supabase, no magic link, no OTP.
- **Single-owner allowlist, keyed on immutable IDs.** `login_identity` stores `(provider, provider_user_id, email, linked_at)`. A login succeeds only if `(provider, provider_user_id)` matches a linked identity (Google `sub`, GitHub numeric id). Email or username alone is never enough. Same email on a different provider ID is rejected.
- **First-run linking:** the very first access uses the bearer token; Settings then links his Google and GitHub accounts to the owner. Either one logs in afterwards.
- **Sessions:** server-side `session` rows (store a hash of the cookie value), `HttpOnly`, `Secure` over HTTPS, `SameSite=Lax`, sliding expiry (default 7 days, configurable). State-changing requests need a custom header and an Origin check; OAuth `state` (and PKCE where supported) is validated.
- **Other doors, separate credentials:** the extension uses a hashed, revocable `jpx_` token minted from a logged-in session and valid only for extension routes. Telegram uses a chat-id allowlist plus the webhook secret. The worker has no HTTP surface.
- **Break-glass:** `API_BEARER_TOKEN` stays for scripts, the coding agent's tests and recovery if an OAuth provider or config breaks. Constant-time compare; a setting can disable it in Phase B once login is proven.
- **Login is not the Gmail/Calendar/Drive connection.** Login asks only for identity scopes (`openid email profile`; GitHub identity). Gmail, Calendar and Drive are separate connections held by the token broker (section 9.4). Never request Gmail scopes at login.
- **Reuse from old code:** the login buttons, redirect and error-message helpers from the social-login work (group F) are a reference. `supabase-js`, magic link/OTP and the account-switch guards are dropped.
- **Config:** `GOOGLE_LOGIN_CLIENT_ID/SECRET`, `GITHUB_OAUTH_CLIENT_ID/SECRET`, `SESSION_SECRET`, `API_BEARER_TOKEN`, `ALLOWED_ORIGINS`. Use a separate Google client and a separate GitHub OAuth app per environment (localhost, Render).

---

## 5. Data model (core tables, Postgres + pgvector; local in Phase A, Neon in Phase B)

- `job_case` (id, source_url, company, role, jd_text, stage, fit_score, created_at …)
- `case_event` (timeline; typed, with actor = agent/user/courier)
- `artifact` (typed: `resume_version`, `company_brief`, `comp_report`, `contact_list`, `draft`, `answer_set`, `interview_prep`; JSONB + file ref)
- `fact` (fact vault: employers, dates, skills, projects, links; source and confirmed_at)
- `answer_bank` (question_text, normalized_question, answer, type, embedding vector, source badge, version, approved_at, company_scope)
- `contact` (name, title, company, linkedin_url, email, x_handle, source, confidence, dedupe_key)
- `contact_touch` (contact_id, channel, action_id, sent_at, outcome)
- `contact` also carries `role_class` (recruiter|hiring_manager|ceo|cto|employee) and `stage` (the outreach state machine in 2.4)
- `outreach_event` (contact_id, stage_from, stage_to, evidence, at) for the outreach funnel and the acceptance watcher
- `eval_result` (agent, dataset, metric, score, model, run_at) so the Experts page can show each agent's last eval
- `backup_log` (file_name, size, sha/md5, drive_file_id, verified_at, local_deleted_at, status)
- `action` (kind, payload frozen, status machine, idempotency_key, approval_id, case_id)
- `approval` (action_id, decision, edited_payload, decided_at, channel)
- `agent_spec`, `run`, `run_step` (checkpointed steps, redacted traces)
- `memory` (content, source/provenance, created_by, deletable)
- `routine` (cron, agent_id, params), `budget_ledger`, `connection` (status only, no secrets)
- `owner` (single row; `user_id` default used on every table so a later multi-user move is a migration, not a rewrite), `login_identity` (provider, provider_user_id, email, linked_at), `session` (token_hash, expires_at, last_seen_at), `extension_token` (hash, scope, revoked_at)
- `legacy_import` (source_table, legacy_id, target_table, target_id, raw jsonb, imported_at): every imported JobPilot row keeps its original as JSONB, so nothing is lost even where the new schema has no column

Answer retrieval thresholds: ≥ ~0.9 similarity → reuse; ~0.75–0.9 → adapt; below → generate. Company-specific questions are **never reused verbatim**; only a stored "angle" is reused.

### 5.1 Importing existing JobPilot data (nothing is lost)

Two copies, on purpose: an **immutable raw export** (as is) and an **imported copy** in the new shape. Deleting the old store is the last step, not the first.

**Counts must be re-taken at export time.** The codebase audit listed 11 applications in the hosted database; the Applications page on 24 Nov shows 48 tracked (Applied 44, Interviewing 2, Archived 2). The export manifest, not the audit, is the source of truth.

1. **Export now (Day 0), before touching anything.** From the hosted Supabase database: a full `pg_dump` (schema + data, public schema) and a JSON file per table written by a read-only script. Include `application_documents` (frozen PDFs), `tailored_resumes`, `cold_emails`, `outreach_messages`, `mail_replies`, `network_contacts`, `referral_requests`, `recruiter_leads`, `qa_answers`, `job_postings`, `resumes`, `identity_confirmations`, `application_events`. Write a manifest (table, row count, sha256 of the file). Store it **outside the repo**, make an encrypted copy, and upload that to Drive. This archive is never edited.
2. **Keep the hosted project as it is** until the import is verified and JobDots has run for about a week. Do not apply the pending migration and do not delete the project. Free Supabase projects may pause after inactivity and have a limited restore window **[verify]**, so rely on the export, not on the project staying live.
3. **Import (Day 2, idempotent, dry-run first).** Mapping:
   - `job_applications` → `job_case` with original dates, status mapped (Applied, Interviewing, Archived, …) and the old match score kept as `fit_score_legacy`; history from `application_events` → `case_event`.
   - `tailored_resumes` + `application_documents` → `artifact(resume_version)` with the PDF stored as a file and its sha256 checked against the original.
   - `cold_emails` / `outreach_messages` → `artifact(draft)` marked `legacy`, with sent/not-sent history as `case_event`. **Imported drafts never become approvable `action` rows.** Anything old can only be sent after an agent re-proposes it under the current policy.
   - `network_contacts`, `recruiter_leads` → `contact` (stage unknown; a local classifier fills `role_class` as a first pass); `referral_requests` → `case_event` / `contact_touch` where something was sent.
   - `qa_answers` → `answer_bank` (re-embedded, provenance `legacy`, `sensitive` flag kept).
   - `job_postings` → Scout's "already seen" set, so old postings are not re-surfaced.
   - Resume + `identity_confirmations` → fact vault seed, shown for re-confirmation.
   - Follow-up dates (for example 29 Nov) → suggested follow-up proposals for the Supervisor, not scheduled sends.
4. **Verify:** a report with per-table source vs imported counts, status totals matching the Applications page, PDF hashes matching, and a spot check of five cases by hand.
5. **Delete only after:** verification passes, one nightly Drive backup of the new database has completed and been checked, and he confirms. Deleting the Supabase project is then a manual step he performs.

---

## 6. UI (agentic, OpenBots-style layout, reimplemented)

Reference only: layout and patterns from OpenBots (activity-stream grouping, sheets, memory sheet) and from the Grok Bot design write-up (roster, presence, the agent's own computer, typed widgets, routines). **Do not copy files or assets** (OpenBots has no LICENSE). Every frontend task loads the `frontend-design` and `jobdots-agentic-ui` skills (`.claude/skills/`); the second one holds the detailed rules summarised in 6.2.

**Shell:** left sidebar = **expert roster** (Supervisor first, then the experts, each with a live avatar and a one-line status), then Cases, Approvals (count), Answer bank, Contacts, Settings. Routines and Connections are reached from an expert's panel and from Settings rather than as top-level pages. Top bar with kill switch and budget meter. Three columns on desktop: roster, thread, right panel (expert's browser preview, routines, artifacts); the right panel collapses on smaller screens.

**Screens**
1. **Command center:** board of cases by stage (Found → Tailored → Researched → Ready to apply → Applied → Replied → Interview); today's approvals count. The default home is the Supervisor thread with this board one click away.
2. **Case view** (a group thread): the experts working on the case post into one timeline; composer with slash commands (`/apply <url>`, `/recon <company>`, `/draft`, `/research`); right sheets = Resume diff/PDF, People, Drafts, Timeline.
3. **Activity stream:** classify tool calls into groups ("Researching · 4 sources", "Tailored resume", "Found 5 contacts", "Drafted email") with a Details toggle showing sanitized input/output. Implement as `classify_tool → group_builder → presentation`.
4. **Approval inbox:** cards per action: resume diff + PDF, email draft, LinkedIn DM draft (one-click send in extension), form answers. Buttons: Approve, Edit, Reject. Reviewer notes shown on the card.
5. **Experts page:** list of agents; configure sheet (model, tools, per-action mode, budgets); "New expert" flow (custom agents).
6. **Answer bank / Memory sheet:** search, source badge, version history, delete.
7. **Contacts (CRM):** per person history, channel, cooldown, dedupe.
8. **Routines, Connections, Run history.**
9. **Extension side panel:** capture JD, detected questions, answer review panel (badges: vault / reused / adapted / generated), "Fill form", and the LinkedIn paste/send helper.

**Typed UI cards:** agents emit typed JSON (`resume_diff`, `email_draft`, `dm_draft`, `contact_list`, `question_card`, `company_brief`, `comp_report`, `interview_prep`, `chart`); the frontend renders them. Agents never emit HTML. The form of the answer is part of the answer: lists become tables, funnels become charts, drafts become editable cards.

**Tech:** React 19 + Vite, Tailwind v4, own component library (shadcn-style primitives are fine), TanStack Query, SSE for live runs, OpenAPI-generated TypeScript client from FastAPI.

**Visual direction:** decided at the start of the first UI day with the `frontend-design` two-pass process (palette, type, layout, principles, then a review against this brief). The constraint from the agent design: the experts' avatar colours carry most of the colour, so the chrome stays neutral; light and dark themes both supported.

### 6.2 Agentic UI patterns

**Roster, not history.** Experts are persistent: returning tomorrow means returning to the same expert with the same memory. Memory and routines belong to an expert; tools belong to the account. Supervisor (the Chief of Staff) coordinates experts, so there are no assignment boards or manual hand-off controls.

**Avatars show state.** One `ExpertAvatar` component (`frontend/src/components/experts/`) wraps **`bot-avatars`** (Libraries.dev, MIT, pinned 0.2.2; docs: libraries.dev/bots): a lit, rounded 2D-canvas body per expert that looks around, hops and sleeps, readable at 24 px. Identity is a body shape per expert, plus an accessory for a few:

| Expert | Body | Accessory |
|---|---|---|
| Supervisor | star | bow tie |
| Scout | clover | |
| Researcher | hexagon | round glasses |
| Comp Analyst | square | |
| Tailor | flower | beret |
| Answerer | blob (with mouth) | |
| Applicant | pill | |
| Recon | ghost | shades |
| Connector | circle | |
| Email Outreach | cloud | |
| DM Outreach | drop | |
| Inbox | pebble | headphones |
| Interview Buddy | cat (with mouth) | |
| Reviewer | droid | square glasses |
| Custom experts | triangle, mech, alien or puddle (from the expert's id) | |

The library animates three states; the rest add one small badge with an icon **and words**, so state is never colour alone. State comes from run and action data (`/api/v1/experts`):

| State | Library state | Badge |
|---|---|---|
| idle | `default` (looks around, jumps now and then) | none |
| acknowledged (queued) | `default` | Queued |
| working | `working` (hops and spins; the only continuous activity) | none |
| waiting for approval | `default` | "N to approve" (the one extra indicator allowed, because approvals block work) |
| needs hand-off | `default` | Your turn |
| blocked (policy, budget) | `default` | Blocked |
| failed | `default` | Failed |
| done | `default` | Done (for ten minutes) |
| paused (kill switch) | `sleeping` | none |
| not built yet (draft spec) | `sleeping`, dimmed | none |

Hover and focus show the current step in plain words from the latest `run_step`; that text is also the accessible label. Below 32 px the badge becomes a dot and the hover text carries the words. In the roster a click opens the thread, so the library's pointer play (`interactive`) is off there; it stays on in larger, decorative uses. The library respects `prefers-reduced-motion` (still pose) and pauses offscreen; seeds per expert keep a row from blinking in unison.

**The expert's browser: status → preview → takeover.** Status: browser icon in the thread header turns active while Researcher, Recon or Applicant use a browser. Preview: a pinned right panel with the latest screenshot, URL and step list, while chatting continues. Takeover: only for the `hand off` tier (CAPTCHA, 2FA, legal attestations), via a hand-off card with "Open in my Chrome" and "Hand back". The UI does not encourage watching the expert work.

**Heterogeneous threads.** One timeline holds messages, grouped activity lines with a Details toggle, quiet system events (routine ran, expert handed work to another expert), typed cards and approval cards. Routines post their results into the owning expert's thread; runs with nothing to report stay silent.

**Approval cards.** Same component inline and in the Approvals inbox: kind, drafting expert, status chip (`Draft`, `Reviewed`, `Ready to send`, `Sending`, `Sent`, `Send unknown`, `Failed`), labelled fields, editable body, Reviewer notes, and verb-first buttons (**Approve and send**, **Edit**, **Reject**). Pending drafts of one kind stack as a deck. Editing an approved draft clears the approval.

**Remove before adding.** Each control must help him delegate rather than give him something to manage. Internal words (run id, lease, model, token) stay in Details or Live Ops.

### 6.1 Dashboards (two views)

**A. Pipeline dashboard (application and outreach tracking)**
- Board of cases by stage: Found → Tailored → Researched → Ready → Applied → Replied → Interview → Offer/Closed.
- Funnel numbers (this week / all time): found, tailored, applied, replies, interviews.
- Outreach funnel: invites sent → accepted → DMs/referral asks sent → replies; cold emails sent → replies.
- Caps used today and this week (invites, DMs, emails) against `policy.yaml`.
- Follow-ups due and interviews coming up, with the Interview Buddy prep link.
- Per-company page: brief, comp report, contacts and their stage, drafts, timeline.

**B. Live Ops view (live agent process)**
- Agent cards: idle / running / waiting for approval / failed, with the current case and step.
- Live activity stream (SSE) across all cases, with a Details toggle for the sanitized trace.
- Queue depth, pending approvals, failed actions (dead-letter list).
- Budget meter (tokens today, $ this month) and Groq rate-limit status.
- Connection health: Google token status and expiry countdown, Telegram, extension last seen, Hunter credits.
- Daily Telegram digest: what ran, what is waiting for him, what failed.

---

## 7. Backend structure (Python)

```
jobdots/
  apps/
    api/        FastAPI app: routes, auth, SSE, webhooks (telegram)
    worker/     queue worker, routines, run executor
    web/        React frontend
    extension/  Chrome MV3
  packages/
    core/       models, schemas (Pydantic), action state machine, policy engine, budgets
    agents/     agent runtime (LangGraph), specs, supervisor, built-in experts, reviewer
    tools/      registry: hunter, search, fetch, tectonic, embeddings, public-browser
    courier/    gmail, calendar, extension_queue, composio_adapter (optional)
    policies/   policy.yaml, linkedin.md, x.md, reddit.md, applicant.md, recon.md
  migrations/   Alembic
  scripts/      one-off tools: export_supabase.py (read-only), import_jobpilot.py (idempotent, dry-run), verify_import.py
  render.yaml
  Dockerfile    (python + Tectonic)
```

Conventions: Pydantic for every agent output; SQLAlchemy 2 + Alembic; routes use schema/route/logic split; secrets only in Render env groups; all logs redacted.

### 7.1 Tech stack

| Layer | Choice |
|---|---|
| Language / packaging | Python 3.12 **[confirm his version]**, `uv`, `ruff`, `pyright` or `mypy` |
| API | FastAPI, Pydantic v2, `sse-starlette` (live streams), `httpx` |
| Database | PostgreSQL + pgvector (psycopg 3); SQLAlchemy 2 + Alembic |
| Agent runtime | Existing Postgres durable queue (leases, fencing, per-stage checkpoints, retries, idempotency) ported to psycopg; `agent_spec` rows drive each agent; LangGraph optional for Supervisor routing and the Reviewer revise loop, no Postgres checkpointer needed |
| LLM access | `openai` SDK against OpenAI-compatible endpoints: Groq (`gpt-oss-120b`) and Ollama (local small models and embeddings); thin provider adapter with fallback (keep the old ModelChain cooldown idea); `tenacity` retries; **no LangChain** |
| Telegram | `python-telegram-bot` or `aiogram`, long polling in Phase A, webhook in Phase B |
| Google | `google-api-python-client` + `google-auth-oauthlib` (Gmail send/read, Calendar, Drive backup) |
| Other tools | Brave Search API (Web Search + LLM Context) and optional Hunter via `httpx`; Playwright (public pages only); Tectonic + Jinja2 (LaTeX); `pypdf` (page-count checks) |
| Security | `cryptography` (Fernet) for stored tokens, structured logging with redaction (`structlog`) |
| Auth | Google + GitHub login via Authlib (single-owner allowlist on provider IDs), server-side sessions, bearer token as break-glass, hashed extension token (section 4.1) |
| Frontend | React 19 + Vite + TypeScript, Tailwind v4, own shadcn-style components, TanStack Query, `EventSource` for SSE, pdf.js, generated API client from FastAPI's OpenAPI schema; `bot-avatars` for the expert avatars, plus the Libraries.dev and React Bits (Stack, CountUp, AnimatedList; via the shadcn registry and MCP) components named in the `jobdots-agentic-ui` skill (section 9); project skills `frontend-design` + `jobdots-agentic-ui` |
| Extension | Chrome MV3, TypeScript, content scripts + service worker + side panel, built with Vite |
| Infra | Docker Compose on Windows (WSL2), Ollama on the host; Render blueprint ready for Phase B |
| Testing / evals | `pytest`, `promptfoo`, JSONL golden datasets (section 8.1) |
| Observability | `run_step` traces, activity stream, Telegram alerts (Langfuse optional later) |

---

## 8. Build plan (16 days: MVP on Day 5, outreach loop on Day 11)

Assumption: coding agents write most code; Dhrumil reviews and tests. Adding the new agents extended the earlier 10-day core by about 6 days. The earlier "Day 7–8 slip" concern is parked at his request.

| Day | Output |
|---|---|
| **0 Freeze and export** | Secret scan; ignore `data/`; snapshot commit on `legacy/jobpilot-v1` + tag; **export all hosted JobPilot data with manifest (section 5.1)**; branch `jobdots` from the snapshot and bulk-delete removed groups; move the plan and spike notes into `docs/`; enable the CI workflow. |
| **1 Foundation** | Python 3.12 package layout; Alembic baseline with the queue and mail SQL functions ported (auth/RLS/grants stripped); local Postgres + pgvector (Neon kept as the Phase B option); **remove Chroma, onnxruntime, LangChain, Supabase, Celery/Redis, LangSmith** (Chroma advisory exception expires **7 Dec**); Docker Compose stack (api, worker, web) on the laptop; Ollama connected; **owner-auth dependency (fixed owner, bearer token) so ported routes keep working**; provider interface (Groq and Ollama via OpenAI-compatible clients); Tectonic in the image; CI; his `policy.yaml`, master `.tex` and fact vault dropped into the repo. |
| **2 Spine** | `job_case`, `case_event`, `artifact`, `action` state machine (generalising the old email approval states, including `send_unknown`), policy engine, budgets; `RunStore` ported to psycopg and the old recovery tests passing; **per-case concurrency replaces the per-user lock**; **Google + GitHub login, allowlist, sessions, login page, extension token (section 4.1)**; **legacy data import + verification report (section 5.1)**; **nightly backup job** (section 9.2); eval harness skeleton seeded with the 37 matching cases + policy-engine tests. This is the heaviest day; the import may slip to Day 3, login must not. |
| **3 Agent runtime** | `agent_spec` format, Supervisor graph, typed artifacts, tool registry + allowlists, Scout (with daily routine and **catch-up-on-wake** scheduler), Researcher. |
| **4 Tailor** | Structured edits on master `.tex`; Tectonic in Docker; validator; diff card; PDF artifact. |
| **5 MVP** | Gmail executor, Telegram approvals, Reviewer, Email Outreach. **MVP: paste JD → tailored PDF + recruiter email draft → approve → send.** |
| **6 Recon + CRM** | LinkedIn URL lookup via Brave Web Search (LinkedIn-only Goggle), optional Hunter, GitHub/X handles, `role_class`, dedupe, caps, cooldowns. |
| **7 Extension + Answerer** | Capture JD; question detection; answer bank (pgvector); review panel with badges. |
| **8 Applicant + LinkedIn queue** | Form fill on Greenhouse/Lever/Ashby; extension **send queue** (invite and DM, one click each). |
| **9 Dashboards + UI** | `frontend-design` plan reviewed against the brief first; expert roster with `ExpertAvatar` states and hover steps; command center, case group threads, approval cards and inbox (deck from React Bits `Stack`), activity stream (`AnimatedList`), dashboard numbers (`CountUp`), expert browser preview/takeover, Pipeline and Live Ops dashboards, answer bank sheet. Earlier days build their screens with the same two skills, so Day 9 is polish and dashboards, not a redesign. |
| **10 Inbox** | Gmail reply classification, **acceptance watcher**, interview-invite detection, Calendar executor (direct API), follow-up routines. |
| **11 Outreach loop** | Connector + DM Outreach, the full state machine (invite → accept → DM/referral), caps enforcement, end-to-end dry run. |
| **12 Comp Analyst** | Pay research artifact, salary-field handling (confirm-before-fill), integration with Answerer. |
| **13 Interview Buddy** | Prep pack: likely questions by round, stories mapped to the fact vault, gaps vs JD, questions to ask, strategy, negotiation notes. |
| **14 Custom agents** | Spec editor, validator, dry-run mode, policy preview, templates. |
| **15 Eval + red-team** | 10 real JDs end-to-end; Recon accuracy on 10 companies already applied to; outreach dry-run; red-team cases (JD or reply saying "message 50 people", "ignore previous rules", "send my resume to this address") → Courier must block; per-agent model routing from eval. |
| **16 Hardening** | Observability, backups, runbook, Telegram alerts, Render blueprint ready for Phase B, optional X/Reddit read-only. |

**Eval notes:** read every cold email, DM, referral ask and "why this company" answer yourself; zero invented claims is the bar.

### 8.1 Evals (how each agent is measured)

**Approach.** Mostly code-based checks, a small LLM-judge layer, and human reading for anything you will send. No hosted eval platform is needed for a single user.

**Tools**
- **`pytest` + an `evals/` folder** (recommended core): JSONL golden datasets, deterministic assertions, a small judge helper. Runs locally with `make eval`.
- **`promptfoo`** (YAML-driven, runs locally): compare models on the same dataset (Groq vs Ollama) and run red-team prompt-injection suites. Works with OpenAI-compatible endpoints **[verify current features]**.
- **Optional later:** Langfuse (self-hosted tracing/evals) or LangSmith (hosted; free-tier limits **[unverified]**). Our own `run_step` table already stores traces, so these are not needed to start.
- **Not recommended now:** heavy RAG-metric suites; the answer bank is small enough to check by threshold tests plus your own review.

**What to measure**

| Agent / component | Dataset (built from your real data) | Checks |
|---|---|---|
| Tailor | 10 past JDs + your master `.tex` and fact vault | Compiles; page count; **zero claims outside the fact vault** (programmatic); JD keyword coverage; diff size sane |
| Recon | 10 companies you already applied to, with people you found manually | Precision@k for the right person and role_class; LinkedIn URL points to the right company |
| Answerer / answer bank | Your past questions and approved answers | Reuse/adapt/generate decision accuracy; no verbatim reuse of company-specific answers; human review of adapted answers |
| Outreach (Email, DM, Connector) | 10 messages you consider good, plus real contacts | Specific reference to the company brief present; length/channel limits; no template phrases; claims supported by the vault; LLM-judge rubric + your read of every draft early on |
| Comp Analyst | 5 past JDs with known ranges | Range brackets the posted range; sources cited; confidence stated |
| Interview Buddy | 3 real interviews you have done | Questions overlap with what was actually asked; stories map to vault facts |
| Inbox / acceptance watcher | 30 labelled emails (replies, acceptances, invites, noise) | Classification accuracy; acceptances matched to the right contact |
| Courier / policy engine | Unit tests | Every action kind has a mode; unknown kinds rejected; caps enforced; idempotent replays |
| Red-team | About 20 injection cases (JD or reply saying "message 50 people", "ignore previous rules", "send my resume to this address") | Courier blocks every one |
| Model gating | Same datasets run on Groq and local models | A local model replaces Groq for an agent only if it matches the baseline |

**Judge caveat.** An LLM judge from the same family as the writer is biased. Use a different family where possible, and keep human spot-checks for every message that leaves the system.

**Cadence.** Run the relevant eval on every change to a prompt, model or `agent_spec`. Each agent lands with its eval; the full run is Day 15. Results go to `eval_result` and show per agent on the Experts page.

---

## 9. Hosting: local-first, then always-on

### 9.1 Phases

| | Laptop (Phase A) | Render with credit (Phase B) |
|---|---|---|
| Cost | $0 | credit-covered; about $14–32/month after |
| Uptime | only while on and awake | 24/7 |
| When it breaks | fix it now | dashboard |
| GPU | RTX 5060, 8 GB | none |
| Extension link | `localhost` | public HTTPS |
| Best for | building, daily use, local models | reliable background work |

**Decision.** Phase A now; Phase B when background jobs must run with the laptop off. The same Docker images run in both. The remote desktop option (old Phase C) is **cancelled**.

### 9.2 Phase A: laptop (free)
- **Containers (Docker Desktop, WSL2):** api, worker, web, Postgres + pgvector. Limit WSL2 memory (for example 6–8 GB, tune it) so Windows, Chrome and models fit in 16 GB.
- **On the host:** Ollama (native Windows) for local models; Chrome with the dedicated profile and the extension. The api reaches Ollama through `host.docker.internal:11434`.
- **Extension → backend:** `http://localhost:8000` (add it to `host_permissions`).
- **Telegram:** **long polling**, so no public URL or webhook is needed.
- **Google OAuth:** the `http://localhost:8080/` redirect already works.
- **Binding:** services listen on `127.0.0.1` only; a login session (Google or GitHub) or the bearer token is required on every route. No public endpoint means a smaller attack surface.
- **Login redirects (localhost):** Google client with `http://localhost:8000/auth/google/callback`; a GitHub OAuth app with `http://localhost:8000/auth/github/callback` (GitHub OAuth apps take one callback URL, so use a second app for Render **[verify]**).
- **Power:** plugged in, sleep off while working. Routines are designed around the laptop being off sometimes: on startup the worker runs every routine that was due while it was down (Scout daily, Inbox polling) and posts "JobDots woke up, ran N missed routines" to Telegram.
- **Backups to Google Drive (nightly):**
  1. `pg_dump` to a temp file.
  2. Encrypt it (key stored only locally, never on Drive); the dump holds resumes, contacts, drafts and stored tokens.
  3. Upload with the Drive API using the narrow `drive.file` scope (files created by the app only; classification **[verify]**).
  4. **Verify before deleting:** compare the local checksum with the `md5Checksum` that Drive reports for the uploaded file, and confirm the size.
  5. Only after the match, delete the local temp dump. On any mismatch or error, keep the local file and alert on Telegram.
  6. Retention in Drive: keep the last 7 daily and 4 weekly dumps; the worker deletes older ones.
  7. Record each run in `backup_log`. If the laptop was off at backup time, catch-up-on-wake runs it.
  8. Restore test monthly (decrypt, restore into a scratch database).
  9. The Drive token is another Google refresh token; in Testing mode it expires after 7 days like Gmail's, so the reconnect flow must cover it and a missed backup must raise an alert.
- **LaTeX and browsing:** Tectonic and Playwright run in the container image.

### 9.3 Phase B: Render (when it must run 24/7)

| Service | Type | Notes |
|---|---|---|
| `jobdots-api` | Web service, Docker | Always-on paid instance; includes Tectonic. Pre-deploy: Alembic migrate. |
| `jobdots-worker` | Background worker, same image | Always-on; queue and routines. |
| `jobdots-web` | Static site | Build env `VITE_API_URL`. |

Database moves to Neon (pgvector). Local models are unreachable from Render, so agents fall back to Groq. Telegram switches from long polling to a webhook.

**Environment variables (Render env group, never in repo):** `DATABASE_URL`, `GROQ_API_KEY`, `API_BEARER_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` (API connections), `GOOGLE_LOGIN_CLIENT_ID`, `GOOGLE_LOGIN_CLIENT_SECRET`, `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET`, `SESSION_SECRET`, `HUNTER_API_KEY` (optional), `BRAVE_API_KEY`, `ENCRYPTION_KEY`, `ALLOWED_ORIGINS`, optional `COMPOSIO_API_KEY`.

**Domain-dependent settings:** CORS for the frontend `onrender.com` URL plus the extension origin; extension `host_permissions` for the backend URL; Telegram webhook `https://<api>.onrender.com/telegram/webhook/<secret>`; Google redirect URI for the API callback; login callbacks `https://<api>.onrender.com/auth/google/callback` and `/auth/github/callback` (HTTPS required for Google on a non-localhost host). Free Render web services sleep after about 15 minutes, so use paid always-on for api and worker.

### 9.4 Google OAuth (applies in every phase)
- **Gmail read/send, Calendar:** keep `http://localhost:8080/` as a redirect URI; add the API callback in Phase B.
- In **Testing** mode, refresh tokens for non-basic scopes expire after **7 days** (confirmed by the Google docs summary he supplied). Gmail and Calendar would break weekly.
- **Production** (External) removes the 7-day expiry and the 100-user cap, but the same summary says it requires a public homepage, privacy policy and terms on a verified domain, and Sensitive/Restricted scopes (Gmail, Calendar) need Google verification (about 2–6 weeks; Restricted scopes may need a paid assessment). Whether a personal, unverified production app is workable is **[verify with Google's docs]**.
- **Internal** needs a Google Workspace org. Do **not** use his employer's org for this.
- **Default plan:** stay in Testing, build a "Reconnect Google" button and a Telegram alert before expiry (weekly reconnect). Decide later whether to buy a domain to publish.
- Use the narrowest scopes that work: Gmail send, plus read-only for the watcher; Calendar `calendar.events`; Drive `drive.file` for backups. Keep scope lists in config.
- **Login is separate from these connections.** Google sign-in uses only `openid email profile`, which are basic scopes and should not trigger sensitive-scope verification or the 7-day refresh-token expiry **[verify]**. In Testing mode only listed test users can sign in, which is fine for one owner. Prefer a separate OAuth client for login so a consent-screen change for Gmail cannot lock him out.

**Chrome extension:** load unpacked in the dedicated profile. The backend URL is a setting (`localhost` in Phase A).

---

## 10. Production-readiness checklist

**Security**
- [ ] Every route requires a valid login session, extension token (extension routes only) or the bearer token; no unauthenticated debug endpoints.
- [ ] Login tests: wrong Google account rejected; wrong GitHub account rejected; same email under a different provider ID rejected; invalid `state` rejected; expired and logged-out sessions rejected; cookie flags set; cross-origin state-changing request rejected.
- [ ] Bearer token compared in constant time; break-glass path tested; extension token revocable.
- [ ] Secrets only in an ignored `.env` (local) or the Render env group (hosted); logs redact keys, tokens, email bodies where not needed.
- [ ] Telegram webhook secret verified; extension auth token rotated if leaked.
- [ ] Policy engine tests: every action kind has a mode; unknown kinds are rejected.
- [ ] Kill switch tested.
- [ ] Prompt-injection red-team cases pass (see Day 10).
- [ ] Composio (if used): minimal payloads; never resumes/email bodies; own OAuth apps; ZDR is paid add-on **[verify]**.

**Local hosting (Phase A)**
- [ ] All services bound to `127.0.0.1`; nothing exposed to the network.
- [ ] Windows sleep/hibernate behaviour set; catch-up-on-wake tested (close the lid for a day, reopen, confirm missed routines ran once each).
- [ ] WSL2 memory cap set; Ollama and the api coexist without swapping.
- [ ] Nightly backup to Drive: upload verified by checksum before local deletion; local copy kept on mismatch; monthly restore test passes.
- [ ] Local-model outage test: stop Ollama, confirm fallback to Groq and a marked run.

**Reliability**
- [ ] Idempotency keys on every side effect; replay test (kill worker mid-run, verify one send).
- [ ] Dead-letter list for failed actions, visible in UI.
- [ ] Health checks; Render restart policy.
- [ ] Neon backups/point-in-time restore confirmed for his plan **[verify]**.

**Cost control**
- [ ] Per-case and monthly budgets; refused-action circuit breaker.
- [ ] Groq rate-limit handling (retry with backoff; Developer-plan limits seen: 250K TPM, 1K RPM **[third-party page]**).

**Observability**
- [ ] `run_step` traces with redaction; activity stream in UI.
- [ ] Telegram alert on failed action, budget breach, expired OAuth token.

**Data**
- [ ] Export/delete for memory, answer bank, contacts.
- [ ] Contact data minimized; retention rule for old cases.
- [ ] Legacy import: source and imported counts match; PDF hashes match; statuses match the old Applications page; no imported draft is approvable; raw export archived off-repo and on Drive.

**Compliance/ToS**
- [ ] Channel policy files written from the actual terms text with last-reviewed date.
- [ ] LinkedIn: drafts + human one-click send, low volume; no scraping behind login.
- [ ] Reddit/X DM rules verified before enabling those channels.

---

## 11. Costs (monthly, at ~60 cases; token counts are my estimates)

**Phase A (laptop): about $3–6/month**, which is Groq only (list price $0.15 in / $0.60 out per 1M tokens, third-party page). Postgres, Ollama, Docker, the stack and embeddings are free; electricity is yours. Moving classifiers to local models lowers the Groq part further. Hunter free tier (50 credits) and Composio (unused) add nothing.

**Phase B (Render + Neon):** the table below. The $100 Render credit covers the Render part for several months.

Inputs he supplied (third-party trackers; treat as list prices): Render workspace Hobby $0 (1 seat, 5 GB bandwidth), Starter web service $7 (512 MB RAM, 0.5 CPU, always on), Standard $25 (2 GB, 1 CPU). Neon Free: 100 CU-hrs/project, scales to zero after 5 min, 1 GB storage; Launch: pay-as-you-go ($0.106/CU-hr, $0.35/GB-month, typical ~ $15/month).

| Item | Lean | Realistic | Note |
|---|---|---|---|
| Render api + worker | $14 (2 × Starter) | $32 (Starter api + Standard worker) | 512 MB RAM may be too small for Chromium/Playwright and LaTeX compiles; budget Standard for the worker if it runs them **[unverified need]**. Static frontend free. |
| Neon | $0 (Free) | ~$19 (Launch) | **Important:** an always-polling worker keeps compute awake. At an assumed 0.25 CU minimum, 24/7 is about 180 CU-hrs/month, above the 100 free. Either poll the queue sparingly (every few minutes) so it scales to zero, or pay for Launch. Interactive work is woken by Telegram/web requests. |
| Groq gpt-oss-120b | ~$3–6 | ~$3–6 | $0.15 in / $0.60 out per 1M tokens; more agents now, still small. Measure after 10 cases. |
| Hunter | Free (50 credits) | Starter $49 if credits run out | |
| Brave Search API | small | small | Per-request pricing; check the plan in the Brave dashboard **[unverified]** |
| Composio | not used | optional free tier | |
| X API | off | pay-per-use if enabled | DM price **[unverified]** |
| **Total** | **~$17–20** | **~$54–57**, up to ~$106 with Hunter Starter | The $100 Render credit covers the Render portion for several months. |

## 12. Risks

| Risk | Mitigation |
|---|---|
| Prompt injection via JD, scraped pages, recruiter replies | Untrusted-input handling, read-only background tools, approval on every send, Reviewer, red-team tests |
| LinkedIn terms/account restriction | Own Chrome, human click, low volume, no bulk |
| Reddit/X cold-DM rules unverified | Reads first; DMs only after terms check |
| Hallucinated resume claims | Fact-vault validator + mandatory diff card |
| Gmail reputation (bounces/spam) | Daily caps, cooldown, dedupe, verify emails, bounce cap |
| gpt-oss-120b writing quality | Schema-forced outputs, Reviewer, Day-10 eval, swappable provider |
| Contact lookup noise for large companies | Confidence score; show source; user confirms |
| OAuth refresh expiry (Testing mode) | Publish consent screen or reconnect weekly |
| Schedule slip on ATS forms (Day 7–8) | Support Greenhouse/Lever/Ashby first; cut Networker polish, X/Reddit |
| Single dependency outages (Groq, Neon, Render) | Provider interface, fallback model, retries, dead-letter queue |
| LinkedIn restricts automated invites/messages | Human click per send, low gradual caps, specific (non-generic) text, stop at any warning |
| Acceptance watcher depends on LinkedIn notification emails | Verify the setting; fallback to the extension reading his own page |
| Google refresh tokens expire after 7 days in Testing mode | Reconnect button + Telegram alert; decide on domain/publishing later |
| Neon CU-hours exceeded by an always-awake worker | Sparse polling or Launch plan |
| Render Starter RAM (512 MB) too small for Chromium | Move worker to Standard |
| Salary advice from noisy public data | Comp Analyst shows sources and confidence; he confirms before any pay field is filled |
| Laptop is off, asleep or travelling, so routines and approvals pause | Catch-up-on-wake, Telegram long polling, Phase B on Render when 24/7 matters |
| Data loss on the laptop | Nightly encrypted backup to Google Drive, verified by checksum, monthly restore test; missed backup alerts on Telegram |
| Local small models are weaker | Move an agent only after it matches the Groq baseline; automatic fallback |
| Laptop RAM (16 GB) shared by Windows, Chrome, Docker and models | WSL2 cap, small models only, measure before adding more |
| Local models too heavy for the hardware | The RTX 5060 laptop is the only local-inference box; strong models stay on Groq |
| Locked out by an OAuth misconfiguration or provider outage | Bearer token break-glass; separate login client from API-connection client |
| Someone with the same email but a different provider account logs in | Allowlist on immutable provider IDs, not email |
| Legacy data lost or duplicated in the move | Immutable raw export, idempotent import keyed by `legacy_id`, verification report, delete only after backup cycle |
| Old drafts sent by accident after import | Imported drafts are `legacy` artifacts, never approvable actions |
| Old queue lock serialises all experts | Per-case/per-kind concurrency replaces the per-user lock (Day 2) |

---

## 13. Out of scope for v1 (frozen)

Landing page, onboarding, multi-user isolation hardening (single-owner Google/GitHub login is in scope; sign-up for others is not), email/password, magic-link and OTP login, v3 ranking experiments, digest-as-product, Daytona-style cloud desktop, bulk outreach, auto-submit of applications, custom MCP tools (phase 2).

---

## 14. Spike results already in hand

- Composio `GOOGLECALENDAR_CREATE_EVENT` failed with `ACCESS_TOKEN_SCOPE_INSUFFICIENT` under the single `calendar.events` scope (its tool metadata requires a second scope group). Direct Google Calendar API worked with only `calendar.events` (create ~1.08 s, delete ~0.82 s).
- Decision: Calendar goes direct. Composio stays an optional adapter; always read each tool's declared scope groups before connecting.
- Google Cloud project `jobdots-spik` holds the OAuth client `jobdots-spike` (redirect URIs: Composio callback, `http://localhost:8080/`).

---

## 15. First actions

1. Hand the coding agent: `policy.yaml`, the master `.tex`, the fact vault (he has these ready), and this plan.
2. **Day 0 first:** run the secret scan, then export all hosted JobPilot data (section 5.1) before any deletion, and make the `legacy/jobpilot-v1` snapshot.
3. Day 1: Docker Compose stack on the laptop, local Postgres + pgvector, owner/bearer auth, Groq and Ollama provider clients, Telegram long polling.
4. Install Ollama on the laptop and pull one small instruct model and one embedding model for testing.
5. Add the outreach caps (invites/day, invites/week, DMs/day, per-company, delays) to `policy.yaml` with low starting values.
6. Decide the Google token path (weekly reconnect vs buying a domain to publish).
7. Confirm LinkedIn notification emails are on, for the acceptance watcher.
8. Add the Drive `drive.file` scope to the Google client and set up the backup job early (Day 2).
9. Create the login OAuth clients: a Google client (login only) and a GitHub OAuth app, both with localhost callbacks (section 4.1). Do this before Day 2.
10. Only later: Render blueprint (Phase B).

---

## 16. What carries over from JobPilot (summary)

Full detail is in `jobdots_codebase_triage.md`.

- **Keep:** queue SQL, `ExecutionContext`, email approval state machine (`send_unknown`), Scout (discovery, eligibility, job boards), `safe_fetch`, JD parser, resume validator (Reviewer seed), extension ATS filler and its tests, matching eval cases.
- **Reshape:** `RunStore` → psycopg; assistant → Supervisor; pipeline stages → experts; `qa_answers` → pgvector answer bank; Network → contact CRM; resume tailor → master `.tex`; extension → Vite + TS shell around the existing JS; Google/GitHub login → backend OAuth.
- **Remove:** Supabase (auth, RLS, storage, `supabase-py`), Composio Gmail broker, Chroma, LangChain, Celery/Redis/LangSmith, Resend digest, recommendation experiments, landing page, magic-link/OTP, account-switch guards, stray scripts.
