# Production readiness follow-ups

This is the durable reminder for work deliberately deferred while implementing the development sprints. Development completion is separate from production approval.

## Before public rollout

- Run real two-account browser flows, fresh-database provisioning/rerun tests, authenticated uploads, employer-form checks, and deployment CORS/SSE/WebSocket tests.
- Recheck service-role ownership filtering, credential redaction, upload sandbox/resource limits, request abuse limits, and token revocation handling on long-lived streams.
- Confirm backup/recovery, monitoring, error alerts, data retention, and supported dependency versions.
- Roll out matching API/frontend changes together and reload the exact-origin extension configuration.
- Verify running worker capacity, lease expiry/recovery, graceful shutdown, and provider idempotency behavior on the chosen host. Sleeping processes cannot execute queued work until a worker runs again.
- Apply Sprint 3's identity/matching migration before enabling its API/UI. Verify confirmation and revocation through two real accounts, choose retention for historical confirmations, warm the local MiniLM model in the intended worker image, and evaluate matching against representative labeled employer data in addition to the synthetic regression set.

## Recommendation for timing

Continue development on the test project. Complete security, real-provider acceptance and operational checks before enabling production automation or public rollout.

## Already verified on 27 October 2026

The Sprint 1 security-guard migration was applied to `JobPilotAI` as `20261027041202_sprint_1_security_guards`. Checks found 15 restrictive public policies, one Storage guard, a private 10 MiB PDF/DOCX resume bucket, unchanged business-row counts, and successful owner/unrelated-identity read tests. The rollback-only two-account smoke test passed on `test-project`. These checks did not constitute full browser or production acceptance.
