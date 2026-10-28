# Production readiness follow-ups

This is the durable reminder for work deliberately deferred while implementing the development sprints. Development completion is separate from production approval.

## Before real mailbox connections or unattended outbound actions

- Review the remaining live Auth leaked-password-protection warning. The app uses magic links, but the project accepted password sign-in for temporary Storage-test users; do not assume the password endpoint is disabled. Enable the appropriate protection or restrict unused password sign-in through Supabase Auth settings before real mailbox use. [Supabase guidance](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection).
- Configure the application's Composio developer project and callback identity verifier, then verify real per-user OAuth and an explicitly approved test send. The chat plugin connection does not configure the application's backend. Composio and Hunter keys are currently absent locally; mailbox and send flags remain disabled. See [SPRINT_4_STATUS.md](SPRINT_4_STATUS.md).

## Before public rollout

- Run real two-account browser flows, fresh-database provisioning/rerun tests, authenticated uploads, employer-form checks, and deployment CORS/SSE/WebSocket tests.
- Recheck service-role ownership filtering, credential redaction, upload sandbox/resource limits, request abuse limits, and token revocation handling on long-lived streams.
- Confirm backup/recovery, monitoring, error alerts, data retention, and supported dependency versions.
- Roll out matching API/frontend changes together and reload the exact-origin extension configuration.
- Verify running worker capacity, lease expiry/recovery, graceful shutdown, and provider idempotency behavior on the chosen host. Sleeping processes cannot execute queued work until a worker runs again.
- Apply Sprint 3's identity/matching migration before enabling its API/UI. Verify confirmation and revocation through two real accounts, choose retention for historical confirmations, warm the local MiniLM model in the intended worker image, and evaluate matching against representative labeled employer data in addition to the synthetic regression set.

## Recommendation for timing

The function-permission, search-path, and Storage-isolation preflight was completed on 28 October 2026. Finish the Auth settings review and provider acceptance checks before enabling real Gmail use. Complete the wider end-to-end and operational checks before public rollout. Development sprints can continue on `test-project` meanwhile.

## Already verified on 27 October 2026

The Sprint 1 security-guard migration was applied to `JobPilotAI` as `20261027041202_sprint_1_security_guards`. Checks found 15 restrictive public policies, one Storage guard, a private 10 MiB PDF/DOCX resume bucket, unchanged business-row counts, and successful owner/unrelated-identity read tests. The rollback-only two-account smoke test passed on `test-project`. These checks did not constitute full browser or production acceptance.

## Verified on 28 October 2026

`mailbox_security_preflight` was applied to both projects. Public/anonymous/authenticated execution of `rls_auto_enable()` was revoked without changing its trigger body or bindings. Both timestamp trigger functions now use `search_path=pg_catalog`. An authenticated, owner-folder-only Storage policy complements the existing restrictive guard.

The real Storage API test on `JobPilotAI` passed owner upload/upsert/download, stranger read/sign/overwrite/delete denial, and private public-URL denial. Both temporary users and the tiny PDF fixture were removed. Existing business counts remained 11 applications, 10 tailored resumes, 30 email drafts, and 1,101 contacts. The live security advisor now reports only leaked-password protection; the development project has no security findings.
