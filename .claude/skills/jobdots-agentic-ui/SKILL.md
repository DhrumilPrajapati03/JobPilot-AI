---
name: jobdots-agentic-ui
description: JobDots interface rules for a persistent-agent product - expert roster with animated avatars that show live state, case threads with typed cards, inline approvals, the agent's browser (status, preview, takeover), and routines. Use for any JobDots frontend or extension UI work, together with the frontend-design skill.
---

# JobDots agentic UI

JobDots is not a chat app with a history list. It is a small team of persistent experts that work on Dhrumil's job cases, sometimes without being asked, and need his approval before anything leaves the system. The interface should make delegating easy and supervising cheap.

**Always load `frontend-design` too.** That skill decides the visual identity (palette, type, layout, critique pass). This skill decides the product objects and the agent-specific patterns. Where they disagree, the plan (`docs/jobdots_final_plan.md`, section 6) wins, then this skill.

Sources of these patterns: xAI's write-up on designing Grok Bot, the OpenBots layout, and bloub (animated blob avatars). Learn the patterns; **do not copy their code, assets, names or exact look.** OpenBots has no licence; bloub's licence is unverified.

## 1. The five objects (nothing else surfaces unless the user needs it)

| Object | In JobDots |
|---|---|
| Expert | A persistent agent (`agent_spec`): name, avatar, role line, memory, routines, tools. Supervisor is the Chief of Staff. |
| Thread | Conversation with one expert, or a **case thread** where several experts post about one job case. |
| Prompt | One-off instruction, saved as a slash command, or run on a schedule as a Routine. |
| Tool | Hunter, search, browser, Tectonic, Gmail. Account-level, shared by experts. Shown only as grouped activity. |
| Artifact | Resume version, company brief, comp report, contact list, draft, answer set, prep pack. Durable, opens in a side sheet. |

Words to keep beneath the UI: model, context window, run id, lease, checkpoint, token, system prompt. They belong in a Details toggle or Live Ops, never in the main view.

## 2. Roster, not history

- The left sidebar is the **expert roster**: Supervisor first, then the experts, each with avatar, name and a one-line latest status ("2 drafts ready for you", "Scanning 22 boards"). Below it: Cases, Approvals (with count), Answer bank, Contacts, Settings.
- Returning tomorrow means returning to the same expert with the same memory. There is no "New chat" as the primary action; the primary action is telling an expert (usually Supervisor) what you want.
- Memory and Routines belong to an expert. Tools and Skills belong to the account. Do not show per-expert tool toggles in the main view; they live in the expert's settings sheet.
- Coordination is the Supervisor's job. Do not build assignment boards or manual hand-off controls. Supervisor routes, and brings Dhrumil in only for a decision or an approval.

## 3. Presence: the avatar is the status indicator

One component, `<ExpertAvatar expert state size />`, carries identity and state. No separate spinner, status dot or "three dots" for agent activity.

**Identity:** same construction for all (simple soft shape + two expressive eyes), varied by shape and colour per expert, with an optional small accessory. Must be recognisable at 24 px in the sidebar.

**State → expression → motion** (one motion per state, calm by default):

| Agent state (from run/action data) | Expression | Motion |
|---|---|---|
| `idle` | neutral | slow breathing, occasional blink |
| `acknowledged` (task queued) | attentive | one small hop, then hold |
| `working` | focused | steady loop (orbit or bob); the only continuous motion |
| `waiting_approval` | curious | gentle tilt every few seconds + count badge (the one extra indicator allowed, because approvals block work) |
| `needs_hand_off` (CAPTCHA, 2FA, attestation) | surprised | single attention pulse, then still |
| `blocked` (policy refused, budget hit) | confused | still |
| `failed` | sad | still |
| `done` | happy | one settle bounce, then return to idle |
| `paused` (kill switch, routine paused) | sleepy | eyes closed, no motion |

- **Hover / focus** on an avatar shows the current step in plain words ("Reading Acme's careers page", "Waiting for your approval on 2 emails"), taken from the latest `run_step`. Click opens the thread.
- `prefers-reduced-motion`: keep the expressions, drop the motion.
- State must never be conveyed by colour alone; the expression and the hover text carry it too.
- Build the avatars as **our own inline SVG kit** (shape path + eye set + accessory), animated with CSS or the `motion` library. Use bloub only as a reference or a design-time tool, and only after its licence allows it.

## 4. The expert's browser: status, preview, takeover

Researcher and Recon use a public browser; Applicant fills forms in Dhrumil's Chrome through the extension. It is the expert's workspace, not his, so the UI does not invite him to watch it.

1. **Status:** a small browser icon in the thread header turns to the active state while the expert's browser is in use.
2. **Preview:** clicking it opens a pinned right-side panel with the latest screenshot, current URL, and the step list. He can keep chatting.
3. **Takeover:** only for the `hand off` tier. A hand-off card in the thread explains what is needed, with one button: "Open in my Chrome" (extension) or "Open page" (public browser). When he is done, "Hand back to <expert>".

The right panel also shows the expert's **Routines** (name, schedule, last run, paused state) and its recent artifacts.

## 5. Threads are heterogeneous

A thread is one timeline that mixes:

- **Messages** (expert and Dhrumil). Prose only when prose fits.
- **Activity groups:** tool calls grouped into one line ("Researching · 4 sources", "Found 5 contacts") with a Details toggle showing sanitised input and output (`classify_tool → group_builder → presentation`).
- **System events:** Routine ran, setting changed, expert handed work to another expert ("Supervisor asked Tailor to tailor your resume"), backup done. One line, quiet.
- **Typed cards:** `resume_diff`, `email_draft`, `dm_draft`, `contact_list`, `question_card`, `company_brief`, `comp_report`, `interview_prep`, `chart`. Agents emit typed JSON; the frontend renders it. Agents never emit HTML.
- **Approval cards** (section 6).

Rule from the Grok Bot work: **the form of the answer is part of the answer.** A list of jobs is a table, a funnel is a chart, a draft is an editable card, five contacts are a contact list. Never make him restructure prose.

## 6. Approval cards

Approvals are the product's most important moment. They appear inline in the thread **and** in the Approvals inbox (same component).

Anatomy of a draft card (email shown; DM, invite, form answers, resume diff follow the same frame):
- Header: kind ("New email"), the expert that drafted it, and a status chip (`Draft`, `Reviewed`, `Ready to send`, `Sending`, `Sent`, `Send unknown`, `Failed`).
- Fields as labelled rows (From, To, Subject), body editable in place. Editing an approved draft clears the approval (the old revision-pinned rule).
- Reviewer notes, if any, directly under the body, in plain words ("Claims 5 years of Python; vault says 3").
- Actions, verb-first and specific: **Approve and send**, **Edit**, **Reject**. The resulting toast uses the same verb ("Sent", not "Done").
- Several pending drafts of the same kind stack as a deck; the top card is actionable, the count shows behind it.
- After sending, the card stays in the thread as a record with its final state. "Provider accepted" is not "Delivered"; show the difference.

## 7. Work that starts without a prompt

- Routines (Scout daily scan, Inbox polling, backups, follow-ups) post their results into the owning expert's thread, so the thread is the log of what ran.
- Catch-up-on-wake posts one summary event ("JobDots woke up and ran 3 missed routines").
- Something that ran with nothing to show stays quiet: no card for "no new jobs".

## 8. Remove before adding

Before adding a control, ask: does it help him delegate, or give him one more thing to manage? Prefer removing panel options, model pickers, run metadata and extra badges. Keep practical limits visible only when hit (for example the outreach caps from `policy.yaml`).

## 9. Checklist for every JobDots screen

- [ ] `frontend-design` loaded and its two-pass design plan done for new screens.
- [ ] Agent activity shown by `ExpertAvatar` state, not spinners; hover gives the current step.
- [ ] Structured output rendered as a typed card, not prose.
- [ ] Every outward action goes through an approval card; no send button anywhere else.
- [ ] Internal words (run, lease, token, model) kept out of the main view.
- [ ] Empty states tell him what to do next; errors say what happened and how to fix it.
- [ ] Works at 360 px wide; keyboard focus visible; reduced motion respected; light and dark themes.
- [ ] No copied code or assets from Grok Bot, OpenBots or bloub.
