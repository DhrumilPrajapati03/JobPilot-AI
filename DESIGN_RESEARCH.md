# JobPilot: agentic Career Desk design research

Reviewed 7 November 2026. Scope: the public landing, authenticated navigation,
overview, discovery and copilot. This is desk research and implementation review,
not a usability study with job seekers. No account records were sent to research
or design services. Canvas examples use fictional data.

## The product decision

Keep Career Desk's practical layouts, but make the coordinated workflow its
organizing idea. Users need to answer: what has been found, what has been prepared,
what needs my decision, and what happened afterwards? A collection of decorative
agent avatars would not answer these questions.

JobPilot already has a tool-using copilot, a staged preparation pipeline, discovery,
reviewable changes and supervised form filling. The redesign exposes these
connections. It does not imply that every named stage is a separate autonomous
agent, or that an idle capability diagram is executing background work.

## Research and its application

| Primary source | Relevant finding | JobPilot decision |
| --- | --- | --- |
| [Microsoft: Guidelines for Human-AI Interaction](https://www.microsoft.com/en-us/research/publication/guidelines-for-human-ai-interaction/) | AI interactions need clear expectations and support across successes and failures. | Explain each stage's inputs and output; show unavailable data explicitly and retain routes to existing work. |
| [Linear: Agent Interaction Guidelines](https://linear.app/developers/aig) | Agents should be identifiable, fit existing workflows and acknowledge requests promptly. | Keep native application and job views. Distinguish actual tool activity from the capability overview; retain the existing running/error/completed activity block. |
| [Linear: Developing the Agent Interaction](https://linear.app/developers/agent-interaction) | Agent sessions distinguish work, waiting, errors and completion. | Use text and semantic color on actual events. Do not invent an “agents active” count or show an idle animation as execution. |
| [Google PAIR: Explainability + Trust](https://pair.withgoogle.com/guidebook-v2/chapter/explainability-trust/) | Explanations and control help calibrate expectations about AI. | Keep confirmed facts, match evidence and skill gaps near decisions. A fit score remains overlap guidance, not a hiring prediction. |
| [Google PAIR: Feedback + Control](https://pair.withgoogle.com/guidebook-v2/chapter/feedback-controls/) | Controls and feedback must be understandable in context. | Keep editable preferences and explicit approvals. A saved application or an opened card is not automatically treated as positive training feedback. |
| [Google PAIR: Errors + Graceful Failure](https://pair.withgoogle.com/guidebook-v2/chapter/errors-failing/) | An AI failure needs a useful way forward. | Partial overview failures show retry and preserve navigation. Sign-in errors use safe, readable messages. Existing materials remain accessible independently of the copilot. |
| [Anthropic: Building effective agents](https://www.anthropic.com/research/building-effective-agents) | Workflows and dynamic agents have different control models; complexity has costs. | Explain the coordinated work without presenting a speculative autonomous swarm. Keep existing orchestration rather than changing the backend for visual effect. |
| [Atlassian: Color foundations](https://atlassian.design/foundations/color) | A consistent color system supports coherent experiences. | Shared semantic tokens govern the app, with a deliberate dark marketing treatment using the same brand accents. |
| [W3C: Contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) and [Target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) | Text contrast and usable pointer targets are separate requirements. | Check text/surface pairs, keyboard operation and mobile controls separately. Passing a build is not an accessibility certification. |

These are design interpretations of the sources. They do not establish that the
redesign will increase application success, conversion or hiring outcomes.

## Why this direction

The first blue dashboard was visually generic and the user preferred the existing
landing. Direction 02 improved reading and information hierarchy, but the product
still looked like a conventional tracker. The refinement keeps its useful split
views and warm reading surfaces, then adds a distinct workflow diagram, a connected
overview, a focused copilot and explicit review boundaries.

Three approaches were considered:

1. A chat-only interface makes delegation easy, but hides saved work and controls.
2. A dense operations console exposes activity, but adds complexity for an
   individual job seeker and can make idle screens look unnecessarily busy.
3. Career Desk combines a calm overview, direct feature navigation and a copilot
   that can open those same views. This is the selected approach.

## Color, type and motion

The light theme uses warm off-white surfaces and dark green-charcoal text. The
sidebar stays dark, establishing a stable navigation boundary. The dark theme uses
green-charcoal surfaces with light text rather than blue-tinted panels everywhere.

| Meaning | Treatment | Constraint |
| --- | --- | --- |
| Primary action / navigation | Blue | Reserve emphasis for the next useful action. |
| AI-assisted capability / working activity | Restrained iris | Identify assistance; never imply accuracy or an active run by color alone. |
| Completed / confirmed | Muted lime or green | Pair with a label and preserve “user confirmed” versus independently verified. |
| Review / decision | Amber | Explain the decision and its consequences. |
| Failure | Red | Provide a recovery path; do not expose raw provider payloads. |

Inter remains the existing product typeface. Larger editorial headings establish
hierarchy; body text remains ordinary readable UI text. Monospace is limited to
small stage labels and technical metadata. Illustrative marketing previews must
not set the working app's font sizes.

Motion communicates an actual transition or running state. Capability diagrams
are interactive but do not simulate perpetual work. Respect reduced motion.
No video background or generated artwork is needed: the real workflow is the
product's strongest visual asset.

## User journey

1. The landing explains discovery, matching, preparation and review. A clickable
   example demonstrates their connection without using private data or real tools.
2. Magic-link sign-in explains delivery errors and supports resend cooldown.
3. The overview shows real match, draft and follow-up data. Unknown data is a dash,
   not zero; partial failures remain visible and retryable.
4. Discovery pairs a compact role list with the existing detailed match/actions.
   Filters, source management, eligibility, drafting, restore and review remain.
5. The copilot keeps conversation, tool activity and its workspace panel. A
   failure is distinct from a completed tool; a draft is distinct from a send.
6. Application materials, approvals, extension assistance and submission evidence
   retain their existing semantics. The employer submission remains the user's.

On narrow screens, opportunity selection opens the detailed view with a clear
back action. Navigation becomes a keyboard-contained drawer with Escape and focus
restoration. On desktop, saved features remain directly reachable from the sidebar.

## Feature preservation map

| Route | Behavior retained |
| --- | --- |
| `/` | Public information, interactive demonstrations, supported sources, FAQ and sign-in calls to action. |
| `/login` | Magic-link authentication and existing session handling. |
| `/workspace` | New overview using existing account-scoped briefing, analytics and résumé APIs. |
| `/chat` | Threads, streaming, stop/retry, tool activity, proposals and resizable workspace. |
| `/jobs` | Followed sources, scans, all feed buckets, filters, match evidence, draft/restore/review. |
| `/apply` | Prepared queue, extension assistance, reporting and submission evidence. |
| `/applications` | Existing list/Kanban, statuses, filtering and application navigation. |
| `/applications/new` | Job input and existing preparation execution/progress. |
| `/applications/:id` | Résumé, cover letter, outreach, approvals, history and existing material actions. |
| `/profile` | Import, personal details, experience, projects, skills, confirmations, preferences and saved answers. |
| `/network` | Existing imported contacts and referral workflows. |
| `/analytics` | Existing observed outcomes, denominators, gaps and honest measurement limits. |
| `/templates` | Existing email/cover-letter templates and editing. |
| `/settings` | Existing account/provider preferences and integration controls. |

## Validation and limits

Use the existing full browser workflow to protect import → facts → preferences →
generation → review → reporting → analytics and account isolation. Add focused
browser checks for the new public workflow preview, overview failure/retry,
discovery selection/filtering, dark/light surfaces and mobile drawer keyboard use.
Inspect desktop and mobile renders; conduct an independent source review.

Still required for a real launch: a human visual review on target devices,
screen-reader/zoom testing, live integration acceptance, production configuration
and the release gates in `PRODUCTION_READINESS.md`. This design work does not
configure SMTP, Gmail, Hunter, monitoring or deployment.
