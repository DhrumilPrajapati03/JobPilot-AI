# Sprint 4: Composio, Gmail and recruiter outreach

Implementation and automated development verification completed on 28 October 2026. Real Gmail OAuth/send acceptance is pending application credentials and user consent; deployment remains deferred. No application mailbox has been connected or used to send a recruiter email during implementation.

## Implemented workflow

1. In **Settings → Your Gmail account**, start a Composio Connect Link while signed into JobPilot.
2. Composio's callback identity verifier sends the browser back with a single-use `session_uri`. The backend redeems it against the authenticated JobPilot user, checks private account ownership, Gmail toolkit, auth config and ACTIVE status, then reads the actual Gmail address.
3. On an application's **Cold email** tab, research a company domain or enter the recipient yourself. Research returns source-backed recruiter records only after provider verification; it does not guess addresses.
4. Choose a saved generated template or a new independent draft. Edit recipient, subject and text. Optionally save the current tailored resume as a PDF snapshot, then review/download that exact snapshot.
5. Approve the saved version. The approval includes the exact sender address/account, recipient, subject, text and optional attachment. Editing, refreshing the PDF, revoking approval or changing connections requires a fresh approval.
6. Click the separate **Send approved email from Gmail** action. The server atomically reserves one durable send job; a worker sends from the connected private account.
7. Inspect Gmail acceptance receipts and synchronize tracked conversations. Reply categories are local suggestions that users can correct/confirm; replies never authorize another send.

Drafts remain in JobPilot until sent; they are not exported to Gmail's Drafts folder. Generated template editors and the legacy manual activity log remain available, with manual marks labeled explicitly. The Gmail snapshots are independent of later template/base-resume edits. Existing applications with email audit history should be archived rather than deleted.

## What “sent” means

| State | Meaning |
| --- | --- |
| `draft` | Saved copy, not approved or sent |
| `approved` | Current immutable version approved, not sent |
| `queued` | Durable send reserved; Gmail acceptance not confirmed |
| `sending` | One dispatch attempt reserved before the provider call |
| `sent` | Gmail returned a usable message receipt, or reconciliation verified the sent copy |
| `send_unknown` | Outcome is uncertain; only read/reconciliation is allowed |
| `failed` | Known rejection or pre-dispatch encoding failure; edit/return to review before another attempt |

Gmail acceptance does not prove recipient delivery or reading. The UI leaves these unknown. A correlated bounce can be displayed as **bounce notice observed**, not a generalized delivery guarantee. Missing search results do not prove a message was never sent.

Unknown outcomes cannot be automatically resent or edited into another attempt. A deliberately new independent message has a new identity; check Gmail Sent before taking that action. A crash after reserving `sending` but before the network request can also become unknown. This intentionally favors avoiding duplicate mail over automatically retrying every potentially lost attempt.

## Architecture and security

- `mail_connections` binds a private provider account to the verified app user and actual Gmail address. Composio retains OAuth tokens; JobPilot stores connection references, not provider credentials.
- `outreach_messages` stores independent content/PDF snapshots, revisions, approval, sender, durable run, dispatch attempt, RFC Message-ID, Gmail receipt and delivery observation. A linked application cannot be deleted while this audit exists; account deletion can still cascade its private data within one transaction.
- `mail_replies` stores correlated message IDs, safe text excerpts, timestamps and reviewable classification suggestions. Repeated sync preserves user corrections.
- `recruiter_leads` records owner/application, address, name, role, domain, provider status and source dates.
- All four tables have owner-only SELECT RLS and no authenticated client write grants. Mutations use server-side ownership checks and restricted `SECURITY INVOKER` RPCs with explicit search paths.
- Draft edits reset approval. Queueing and dispatch are transactions with row locks. Duplicate send requests reuse the reserved run; cancellation is accepted only before dispatch. Sender changes after approval fail the dispatch check.
- Worker commits are fenced by the Sprint 2 lease token. After a lost provider/database acknowledgment, a replacement worker can reconcile but cannot call send again for the same reserved attempt.
- Reconciliation uses the exact RFC Message-ID, SENT label, frozen sender and recipient. It never treats an unrelated inbox message as proof of sending.
- The broker specifies both authenticated user ID and connected-account ID, checks account ownership/status/config, rejects shared connections, and limits operations to app-constructed Gmail endpoints. It never selects a provider default account.
- MIME headers accept a single address and a single subject line. PDF bytes are generated from owned resume content, hashed, frozen with the draft, limited to 2 MiB and served only through an authenticated download. A requested PDF render failure stops preparation; the attachment is not silently omitted.
- List responses query attachment metadata rather than loading every PDF. Worker sync uses metadata projections and pages 50 tracked outgoing messages per run; child pages are durable. Provider read failures are bounded and surfaced.
- The assistant receives owner-scoped Gmail receipt metadata and instructions distinguishing provider acceptance from legacy manual flags. It has no direct send tool; chat edit approval cannot authorize sending. Reply body text is not supplied to the assistant.
- Settings ignore unrelated `.env` keys and suppress input values in validation messages, preventing configuration errors from printing secret values. App booleans still require valid values.

The application uses HTTPX against the documented Composio REST APIs: v3 Connect Links/account retrieval/proxy, plus v3.1 `complete_auth`. This avoids the retired managed-OAuth `initiate()` flow and does not depend on guessed Gmail tool slugs. The proxy calls Google's Gmail v1 REST API directly with MIME/base64url messages.

References: [Composio connection identity verification](https://docs.composio.dev/reference/v3/api-reference/connected-accounts), [complete auth](https://docs.composio.dev/reference/api-reference/connected-accounts/postConnectedAccountsCompleteAuth), [proxy API](https://docs.composio.dev/reference/v3/api-reference/tools/postToolsExecuteProxy), [Gmail sending](https://developers.google.com/workspace/gmail/api/guides/sending), [message search](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list).

## Recruiter research and replies

Hunter research is invoked by a user action for an owned application. The provider organization must match the target company. The workflow checks up to 10 domain records and verifies at most five candidate addresses. It excludes guessed/no-source addresses, non-recruiter roles, other domains, catch-all/disposable results, mismatched verifier addresses, and missing or older-than-31-day verification dates. Provider keys are sent in headers.

Only provider-valid addresses with source records are saved. Email deliverability verification is distinct from independent confirmation of someone's current employment or role; the UI exposes the source dates and asks the user to review those facts. No Apollo integration or LinkedIn scraping is claimed. Without a Hunter key, research reports unavailable rather than inventing results. [Hunter API reference](https://hunter.io/api-documentation/v2).

Synchronization reads only tracked outgoing messages/threads for the connected owner. It correlates replies using References/In-Reply-To, excludes outgoing/draft messages and old/unrelated content, strips quoted sections, and renders plain escaped text. Categories are `positive`, `negative`, `interview`, `out_of_office`, `unsubscribe`, `bounce` and `other`. These are deterministic suggestions, not authoritative intent classification. No automatic follow-up sequence is sent. Metadata/Reference limitations can leave some real replies or separate-thread bounce notices uncorrelated; users can always inspect Gmail itself.

With a running durable worker, automatic sync is scheduled approximately every ten minutes. Manual sync is also available. Sleeping/stopped workers cannot process queued sends or sync; a queued message is not shown as accepted. A failed worker before dispatch is surfaced with a cancel/review recovery path. Disconnect stops future/queued sends; an already in-flight send may complete.

## Local setup before real mailbox acceptance

1. Review the remaining live Supabase Auth password-protection warning in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md). Keep mailbox/send feature flags off until the auth and provider setup is accepted.
2. Use a development Supabase project with the baseline and all Sprint 1–4 migrations. Configure matching frontend/backend Supabase project keys. The local `.env` still points to the live project, which intentionally does not have the development feature migrations; switch development runtime configuration before testing these features there. Do not put a service-role key in Vite variables.
3. Create/use your own Composio developer project and Gmail auth config. The plugin connection in this chat does not supply `COMPOSIO_API_KEY` or `COMPOSIO_GMAIL_AUTH_CONFIG_ID` to JobPilot.
4. Configure Gmail send and read-only access, along with the identity scopes required by Composio. Register the project's **callback identity verifier** at `https://<your-frontend>/settings`. Setting only a normal `callback_url` is insufficient. The verifier requires public HTTPS; local development needs appropriate HTTPS tunnels for the frontend and API, matching `FRONTEND_URL`, Vite API/WS URLs and CORS.
5. Complete consent in the same signed-in browser session. The opaque verifier URI is removed from the address bar and redeemed once; expired/failed callbacks require a new connection flow. Unconfirmed connections are never bound by trusting a callback-supplied account ID.
6. Start matching API and worker processes with `EXECUTION_MODE=durable`. Confirm sender/account and profile access before enabling sending. Both API and worker need the backend keys and flags.

```dotenv
# Backend only; fill these locally. Never paste secrets into chat or source control.
COMPOSIO_API_KEY=
COMPOSIO_GMAIL_AUTH_CONFIG_ID=
MAILBOX_ENABLED=false
MAIL_SEND_ENABLED=false
MAIL_SYNC_ENABLED=true
EXECUTION_MODE=durable
DEBUG=false
```

Set `MAILBOX_ENABLED=true` only after configuring the verifier/auth project. Set `MAIL_SEND_ENABLED=true` when ready to test an explicitly approved email to a chosen recipient. `HUNTER_API_KEY` enables recruiter research separately. Defaults remain disabled, and no existing `.env` credentials or runtime flags were changed by this sprint.

From `backend`, start the API and `python -m app.workers.runner` separately, or use `docker-compose.durable.yml`. The resume renderer also needs its normal fonts/system dependencies. A PDF preparation failure is visible; plain-text sending remains an explicit user choice.

## API surface

| Endpoint | Behavior |
| --- | --- |
| `GET/POST/DELETE /api/v1/email/connection` | Connection status, start consent, disconnect locally/remotely |
| `POST /api/v1/email/connection/complete` | Redeem callback identity session against authenticated user |
| `POST /api/v1/email/messages` | Save a draft snapshot; optional owned PDF; idempotent import of a generated template |
| `PATCH /api/v1/email/messages/{id}` | Save a new revision and invalidate approval |
| `POST /api/v1/email/messages/{id}/approve` | Approve current revision and frozen sender |
| `POST /api/v1/email/messages/{id}/send` | Atomically queue approved send; requires enabled durable mode |
| `POST /api/v1/email/messages/{id}/cancel` | Cancel queued work/revoke approval before dispatch |
| `GET /api/v1/email/history?application_id=…` | Owner-only status/receipt history; latest 100 records |
| `GET /api/v1/email/messages/{id}/attachment` | Download exact saved PDF snapshot |
| `POST /api/v1/email/sync` | Queue synchronization of tracked conversations |
| `GET /api/v1/email/messages/{id}/replies` | Owner-only observed replies; latest 100 |
| `PATCH /api/v1/email/replies/{id}` | Confirm/correct a classification |
| `POST /api/v1/contacts/research` | Provider-verified, source-backed recruiter lookup |
| `GET /api/v1/contacts/?application_id=…` | Saved owner-only research records |

The old `/email/send` stub now returns a review-required conflict instead of pretending to send. Legacy manual email flags remain manual records and do not manufacture provider receipts.

## Verification and database rollout

- Backend regression suite: **260 tests passed**; provider calls stubbed for Gmail send/OAuth/read scenarios. Tests include lost provider/database acknowledgments before and after commit, at-most-once dispatch recovery, private/shared-account validation, identity callback redemption, ambiguous receipts, MIME/PDF integrity, tenant isolation, safe configuration errors, recruiter filtering and reply correlation.
- Frontend: **18 tests passed**, including review/send separation, immutable sender presentation, uncertain-outcome recovery, escaped content and honest delivery labeling. Production build passes; a pre-existing mixed static/dynamic Supabase import warning remains non-blocking.
- Hosted `test-project` rollback-only `supabase/tests/gmail_outreach.sql` passed: ownership, stale revisions, approval invalidation, frozen sender, duplicate queue/dispatch prevention, lease fencing, unknown-send reconciliation states, immutable sent records, human reply correction preservation, and owner-only reads. No fixture mail records/connections/users remain.
- Real `JobPilotAI` Storage API test passed with two temporary confirmed users and a tiny PDF: owner upload/upsert/download, stranger read/sign/overwrite/delete denial and public-URL denial. Fixtures were removed. Reproduce explicitly using `python scripts/check_storage_access.py --project <matching-project-ref>` with locally configured project credentials; this is not part of the offline suite.
- Live business counts remain 11 applications, 10 tailored resumes, 30 generated email drafts and 1,101 contacts.

| Local migration | Test-project history | Live history |
| --- | --- | --- |
| `20261028043146_mailbox_security_preflight.sql` | `20261028043457` | `20261028043504` |
| `20261028043147_gmail_outreach_workflow.sql` | `20261028044359` | Deferred |
| `20261028045823_mailbox_sender_guards.sql` | `20261028045847` | Deferred |

The preflight revokes public execution of the privileged event-trigger helper, fixes the timestamp-function search paths, and adds owner-folder-only authenticated Storage permissions. Function bodies/trigger bindings are preserved. The development project has no security advisor findings. The live advisor now reports only [leaked-password protection](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection), which needs a dashboard configuration review. Newly unused indexes are expected on the empty development schema; no new missing-FK-index warnings were introduced.

MCP/local CLI migration timestamps differ; reconcile against the actual schema before adopting `db push`. The live project has only Sprint 1 guards plus the security preflight, while the development project contains feature migrations through Sprint 4. No app deployment, provider connection, real Gmail send, live Hunter research or live OAuth browser acceptance was performed.

Still required before release: configured-provider browser acceptance, Google consent/distribution review, callback/reconnect/revocation scenarios, real receipt/reply/PDF verification, rate/abuse controls, retention and backup decisions for mail/PDF snapshots, monitoring, host resource/capacity checks, and the remaining production checklist. A stale OAuth flow may need restarting/removal in the provider dashboard; the app never bypasses identity verification to recover a connection.
