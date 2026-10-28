# Sprint 5: reliable supervised application execution

Implemented on 28 October 2026. Development verification is complete; production rollout remains deferred. Sprint 4's code is implemented, but its real Gmail OAuth/send/reply and Hunter acceptance checks still need application credentials. Sprint 5 does not claim to complete those checks.

## User workflow

1. Use the development database with all Sprint 1–5 migrations, matching frontend/backend credentials, and a working PDF renderer. Reload the unpacked Chrome extension, now version 1.1.0 (Chrome 102+).
2. Open a saved application's employer form. Click the JobPilot launcher or use the extension popup. Select the correct application. An unmatched URL requires explicit company/role confirmation before linking; selecting profile-only filling creates no application evidence or PDF snapshot.
3. Start preparation. The server freezes the latest owned tailored résumé PDF/version in an application session. Retrying the same session never replaces that snapshot with a later edit.
4. Review the fields. The engine fills empty controls, preserves existing entries, checks retained values and native validity, and highlights unresolved, invalid, AI-drafted and legal fields. Dynamic questions receive up to three bounded read/fill passes. At most 150 controls are inspected; reaching that limit is displayed and recorded.
5. Review the selected PDF. Its bytes/size/hash must match the frozen snapshot, the field must accept PDF, and the browser must retain that file. An existing different attachment is preserved and flagged. File selection is not proof that the employer accepted an upload.
6. Submit yourself. The extension never calls `submit()`/`requestSubmit()` or clicks a submit button. A trusted user action followed by a native final-submit event is recorded separately from preparation. Next/Continue steps, invalid native forms, programmatic events and opening Apply pages do not count as final submission evidence.
7. If a supported provider-specific confirmation marker appears after the attempt, the extension records a **browser confirmation observed** event. It never calls that independent employer verification or automatically changes the application status.
8. Use **Report that I submitted** to update status and schedule the usual five-day follow-up. Both the extension and Apply queue record explicit user-report provenance. The application detail page presents preparation, attempts, browser observations and user reports separately.

Legacy status selectors and older records remain manual status history; no historical confirmation is inferred or backfilled. Moving an application into another status does not manufacture a provider receipt.

## Form handling

| Area | Implemented behavior |
| --- | --- |
| Labels | Explicit/implicit labels, ARIA names, legends and grouped question labels; option text is excluded from question labels |
| Native controls | Text, email, telephone, URL, number/date, textarea, single/multiple select, grouped radio/checkbox |
| Custom controls | Input/button ARIA comboboxes with linked listboxes; ARIA radio/checkbox groups |
| Option matching | A unique exact browser option is required; no prefix or global unrelated-option matching |
| Saved options | Backend yes/no and numeric ranges require an unambiguous match; partial matches such as male/female or India/Indiana are refused |
| Existing values | Preserved; an invalid value, changed proposed answer or different attachment is highlighted rather than silently overwritten |
| Validation | Required, native email/range/pattern/step rules, explicit maximum length, `aria-invalid`, read-only/disabled controls, disconnected/replaced controls |
| Dynamic controls | Up to three passes; newly exposed questions are detected; unresolved changes remain reviewable |
| Sensitive questions | Legal agreements/attestations remain manual, including questions mentioning sponsorship; AI drafts retain review flags |
| PDF | Frozen owned version, maximum 2 MiB, PDF signature/size/SHA-256 checks, accept-type check, post-change and final hash audits |

Unsupported closed shadow roots, canvas controls, unlinked custom popups, arbitrary file formats and unfamiliar widgets require manual entry. The extension does not guess a nearby option. Asynchronous employer upload failures occurring after the browser's checks are not independently detectable by this implementation.

## Evidence architecture

- `application_documents` contains immutable application-specific PDF snapshots with version, name, SHA-256 and size. The PDF is stored as bounded base64 in PostgreSQL, following the existing small-snapshot approach; direct authenticated reads grant metadata columns only.
- `application_execution_sessions` binds the owner, application, sanitized form URL, linking method, document and a 24-hour expiry. Known ATS opening identities survive apply-step URL changes. Tracking is discarded; unknown query parameters are represented by a digest so distinct custom openings are not merged while raw query secrets are not retained.
- `application_events` stores append-only observations: `form_prepared`, `submission_attempted`, `submission_confirmation_observed`, `user_reported_submitted`. It stores field keys/types/outcomes/sources and computed counts, not raw field answers, labels, page HTML or screenshots.
- `create_application_session` and `append_application_event` are service-role-only `SECURITY INVOKER` RPCs with explicit search paths and owner checks. Application row locking serializes related writes. Session/request UUIDs make replays idempotent; changed replay payloads conflict.
- A confirmation requires an attempt in the same session within 15 minutes. Preparation and browser observations never mark an application applied. Only an explicit user report atomically stamps status/date/follow-up, and replaying it cannot overwrite later progress.
- RLS allows owner-only reads. Authenticated users cannot mutate audit tables or call privileged RPCs. Applications with evidence must be archived rather than deleted; account deletion can still cascade private data.
- The web detail endpoint returns the latest 20 sessions, latest 200 associated observations and document metadata. It does not return PDF bytes. An unavailable history endpoint is shown as unknown, not as evidence of success.

## Extension isolation and recovery

The broker binds the session to the tab, frame, origin and a digest of the active API/token connection. It overwrites event URLs with the actual content-script sender URL. Another tab/frame/origin cannot borrow the binding. Raw API paths and snapshot requests are restricted; redirects are refused on credentialed JSON requests.

Token storage and the pending-observation store use `TRUSTED_CONTEXTS`, so content scripts cannot read them directly. Account changes invalidate the panel and interrupt pending field operations; an old in-flight API response is discarded. The unpacked-browser tests verify both isolated-world execution and denied token reads.

An observation is saved to the broker's bounded outbox before transport. A lost acknowledgment reuses the same request UUID. Reopening flushes pending observations in order. The native attempt and linked application survive same-origin, same-frame navigation, including a full document reload. The outbox is limited to 20 entries and uses Chrome session storage: browser restart, extension reload/disable, changed frames, expiry or a different origin can require a new preparation session. It is not a replacement for the database's durable history. Only acknowledged database events are treated as saved.

## API additions

| Endpoint | Purpose |
| --- | --- |
| `POST /api/v1/extension/sessions` | Create/reuse an owned preparation session and freeze its PDF |
| `POST /api/v1/extension/document` | Private, no-store download of that session's PDF bytes/metadata |
| `POST /api/v1/extension/events` | Validate and append bounded browser observations |
| `POST /api/v1/extension/applied` | Explicit user-reported submission with optional session/request identity |
| `GET /api/v1/applications/{id}/execution` | Owner-only history and document metadata |
| `POST /api/v1/applications/{id}/report-submission` | Idempotent user report from the web Apply queue |

The existing extension fill/answer/queue endpoints remain available. The legacy by-application PDF route remains an export, but the new engine attaches only the frozen session document.

## Verification

| Check | Result |
| --- | --- |
| Backend regression suite | **283 passed** |
| Frontend component/regression tests | **21 passed** |
| Frontend TypeScript + production build | Passed |
| Extension security/broker tests | **7 passed** |
| Chromium browser cases | **15 passed**: 13 form-engine cases and two unpacked-extension workflows |
| Hosted PostgreSQL rollback smoke | Passed, including ownership, column grants, replay conflicts, expired sessions, confirmation sequencing, status separation, later-progress preservation and account-delete cleanup |
| Development security advisor | No findings |
| New missing-FK-index findings | None after the forward index migration |

Browser fixtures are authored representative patterns, not copied employer pages. The unpacked tests exercise actual extension content scripts/service worker/storage in Chromium while intercepting API/employer network boundaries. They verify no automatic submit, manual consent, native validation, final-vs-Next actions, correct event sequence, explicit reporting, same-origin navigation and denied token reads. No actual employer application was submitted.

Read-only public employer checks are recorded in [the compatibility matrix](extension/tests/browser/COMPATIBILITY.md) and its JSON artifact. Greenhouse exposed 25 controls. Ashby inspection was unavailable, SmartRecruiters did not expose its application step without interaction, and the checked Lever feed had no public postings. These observations do not certify real-employer fill or submission accuracy.

Existing non-blocking FastAPI/Chroma deprecation warnings and the frontend's mixed static/dynamic Supabase import warning remain.

## Database rollout and local setup

| Local migration | Development history | Live JobPilotAI |
| --- | --- | --- |
| `20261028113722_application_execution_evidence.sql` | `20261028115416_sprint_5_application_execution_evidence` | Deferred |
| `20261028115607_application_execution_indexes.sql` | `20261028115719_sprint_5_application_execution_indexes` | Deferred |

Both migrations were applied only to `test-project` (`klhpguohtcrsidqjwbqh`). The transactional smoke left zero sessions, events, documents or applications there. No live schema changes, app deployment, provider connections or outbound messages were performed for Sprint 5.

The local runtime configuration still needs to target development before using these features: it previously pointed to the live project, which intentionally lacks Sprint 2–5 feature migrations. No local credentials or runtime flags were edited. Match frontend/backend project keys, keep service-role keys backend-only, and reconcile MCP/CLI migration history before any future `db push`.

From `backend`: `.venv/Scripts/python.exe tests/run_offline.py`. From `frontend`: `npm test` and `npm run build`.

From `extension`, in PowerShell:

```powershell
npm ci
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Resolve-Path ..) '.tool-cache/playwright'
npx playwright install chromium
npm test
npm run test:browser
```

Test dependencies are pinned/locked. Browser binaries, profiles, reports and `node_modules` are ignored. The read-only inspection script is opt-in: `node scripts/check-live-forms.cjs input.json output.json`; it never fills, clicks, uploads or submits and stops on unavailable/blocked pages.

## Remaining acceptance work

Before release, complete real two-account extension/backend browser flows on the deployed origins and deliberately chosen employer forms, including custom AJAX-only submission, multi-step navigation, cross-origin iframes, upload server rejections and real confirmation pages. Native final-submit events are supported; arbitrary AJAX-only buttons and unfamiliar/localized final actions may require manual reporting. Provider-specific markers can change or omit valid confirmations; absence of a marker is not a failure verdict.

Select retention/quotas/backups for PDF snapshots and observation history, verify rate/resource limits and revocation behavior, and finish the wider [production readiness checklist](PRODUCTION_READINESS.md). Real Gmail/Hunter acceptance remains Sprint 4 follow-up. End-to-end product validation and operational monitoring belong to Sprint 6. The implementation provides supervised execution and honest evidence, not universal automated employer submission or independent proof of acceptance.

Implementation references: [Chrome content-script isolation](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts), [trusted extension storage](https://developer.chrome.com/docs/extensions/reference/api/storage), [Playwright extension testing](https://playwright.dev/docs/chrome-extensions), [HTML input validation/files](https://html.spec.whatwg.org/multipage/input.html), [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).
