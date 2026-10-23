# Sprint 1 — Security foundation

Scope confirmed by the user: Sprint 1 from the supplied roadmap. The landing-page work is preserved. Durable queues, graph checkpoints, matching v2, Gmail, and recruiter research remain later sprints.

## Implemented

- Generation streams require a Supabase JWT in the first WebSocket frame within 10 seconds. Run ownership is checked before replay. Invalid/expired credentials close with 4401; another account's known run closes with 4403. Finished runs are pruned before subscribing. Credentials never enter URL query strings.
- All pipeline entry points register the owner. The browser obtains the current session on every connection/reconnection. Four reconnect attempts are bounded rather than reset on every socket opening.
- Chat history uses `jobpilot-chat:<Supabase UUID>`. Sign-out/account changes reset visible chat/workspace state and abort active chat requests. Legacy `jobpilot-chat` history is retained on disk but never automatically assigned to an account because its owner is unknown.
- Each account boundary gets a fresh React Query client, not merely an emptied cache. Late mutation callbacks keep the old client. React remounts the application boundary on user changes. Same-user token refresh preserves the cache and chat history. Standalone active-run session-storage keys are also user-scoped.
- JD URLs accept only HTTP/HTTPS on the corresponding standard port, without embedded credentials. Every DNS answer must be public. Each redirect is revalidated. The actual socket destination is the approved IP, with the original Host/TLS hostname preserved; environment proxies and cross-hop cookie/connection reuse are disabled. Limits: four redirects, 25-second total deadline, 10-second network timeouts, 2 MiB response, HTML/text only. Compressed responses are rejected to bound decompression work. Users can paste JD text when a site is incompatible.
- Resume files are limited to 10 MiB, PDF signatures are checked, and DOCX ZIP structure, encryption, entry count, and expanded size are checked before parsing. PDF extraction is limited to 50 pages. Invalid document parsing produces a client error. Upload request bodies are bounded before multipart parsing, including chunked requests; resume multipart allowance is 11 MiB and network import allowance is 201 MiB. Spools above 1 MiB use temporary disk storage.
- Extension policy uses exact configured frontend/API origins, validates top-frame connection messages and sender identity, restricts credentialed calls to explicit extension endpoints, and refuses raw-settings reads by content scripts. Wildcard Render origins were removed. Manually captured answers default to sensitive so they cannot silently become ordinary model context; users can deliberately adjust sensitivity in their answer bank.
- Placeholder contact and general email routes now require normal user authentication. They remain placeholders; no outreach is sent.
- JWT signature algorithms have an explicit HS256/ES256/RS256 allowlist.
- A new base-schema migration precedes existing incremental migrations and includes core ownership policies and a private resume storage bucket. An ordered SQL bundle generator and rollback-only cross-account database smoke test are included.
- `20261023_security_guards.sql` adds restrictive owner/parent guards so older permissive policies cannot grant cross-account access on the covered business tables. It also explicitly grants the intended authenticated/service-role access on feature tables. Apply this migration to existing deployments after their earlier migrations; it has not been executed against a hosted database here.

## Database setup and acceptance check

For a **fresh Supabase project**, from `backend`:

```powershell
.\.venv\Scripts\python.exe scripts/database_bundle.py --output supabase/bootstrap.generated.sql
```

Review and apply that generated file in the new project's SQL editor. It wraps all versioned migrations in one transaction. Apply it a second time to check rerun behavior, then run `supabase/tests/bootstrap_smoke.sql`. The smoke test creates two temporary users and checks core cross-account read/write isolation, rolling back all fixture data.

This baseline expects Supabase Auth, Storage schemas, and standard roles. It is not a generic standalone-PostgreSQL bootstrap. Existing installations should review the baseline before applying it: `CREATE TABLE IF NOT EXISTS` preserves existing tables and does not repair arbitrary schema drift or remove old permissive policies. Never treat this file's presence as proof that hosted RLS has been verified.

**Acceptance limitation:** The Docker engine was unavailable and no local `psql` executable was found. Fresh Supabase provisioning, rerun behavior, storage access, and SQL/RLS smoke execution could not be verified in this environment. The bundle ordering test is a local source check, not a replacement for those acceptance checks. No hosted migrations were applied.

## Extension deployment

Reload the unpacked extension after updating. Defaults allow the repository's documented example hosts, `https://jobpilot-web.onrender.com` and `https://jobpilot-api.onrender.com`, plus the existing localhost origins. These are configuration defaults, not verified deployment addresses.

For different deployment URLs, update the exact origins in **both** `extension/policy.js` and `extension/manifest.json`. Reconnect from the configured frontend. There is deliberately no broad Render wildcard fallback.

## Local verification

Latest results: **192 backend tests passed** (four dependency deprecation warnings), **four frontend account-isolation tests passed**, **four extension security tests passed**, and **TypeScript/Vite production build passed**. Extension JavaScript syntax checks and `git diff --check` passed. The existing nonfatal Supabase static/dynamic import build warning remains.

From `backend`:

```powershell
$env:DEBUG = 'false'
.\.venv\Scripts\python.exe -m pytest tests -q
```

From `frontend`:

```powershell
npm.cmd test
npm.cmd run build
```

From the repository root:

```powershell
node --test extension/tests/security.test.cjs
```

Backend tests exercise stream authentication/ownership/expiry, URL and redirect defenses, content limits, archive validation, multipart limits, and authenticated placeholder routes. Frontend tests execute the real account/chat/query stores with an offline auth stub, including account switching, logout, late cache writes, and stale stream completions. Extension tests execute the actual worker in a mocked Chrome context. They are not real-browser end-to-end tests.

## Remaining boundaries

- Generation tasks, locks, and event history remain process-local. Restarts and multiple workers still require Sprint 2 durable execution; this change does not claim recovery across workers.
- No browser, live employer form, real provider, delivery, hosted RLS, or production deployment test was performed.
- Run authorization is checked on connection, not continuously against a revoked token during an already-open socket session.
- Upload byte/archive limits reduce resource exposure; they do not replace a sandboxed document-processing worker or a shared abuse/rate limit.
- Client-readable browser storage is not encrypted storage. Account scoping prevents automatic cross-account UI hydration, not a user with direct access to the browser's storage inspector.
- Factual resume validation and full onboarding are not part of Sprint 1.
- Roll out the API and frontend together: older clients that omit the first JWT frame will no longer receive generation progress. Existing extensions also need a reload and exact-origin configuration. The storage guard makes the `resumes` bucket private; public URLs to original uploads should not be relied on after migration.

## Implementation references

The pinned-IP/Host/SNI approach uses the documented [HTTPX SNI extension](https://www.python-httpx.org/advanced/extensions/). URL and DNS checks follow the concerns described in the [OWASP SSRF prevention guidance](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html). These references support the implementation choices; they do not constitute an external security audit.
