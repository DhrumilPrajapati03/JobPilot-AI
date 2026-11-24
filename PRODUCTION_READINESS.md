# Production readiness ? release candidate

Updated 7 November 2026. **Implementation is ready for release review; public launch
still requires live acceptance.** No final push/deployment or live migration was
performed for this release. [Setup steps](PRODUCTION_SETUP.md) ? [evidence](RELEASE_READINESS.md).

## Completed locally

- Career Desk design, preserved routes, real workflow activity and safe auth errors.
- Private recommendation feedback and opt-in impressions; experimental local ranking.
- Cited research and source-bound review drafts; working private writing templates.
- Production guards: durable worker, quotas, HTTPS/origins, JWT issuer/expiry/session.
- Dependency patches, Router 7, lockfiles, frontend CSP and non-root Docker runtime.
- Automated app/extension/browser, SQL/RLS, real worker crash recovery and synthetic
  backup/restore checks. Exact verification and limitations are in the release record.
- API and worker deploy definitions, disabled auto-deploy, pinned CI actions and rollback instructions.

## Gates still requiring verification, configuration or approval

- [ ] Finish Linux image build/smoke: downloads timed out; no complete image is verified.
- [ ] Approve/apply the new release migration after backup/history reconciliation.
  Sprints 1?6 already exist on JobPilotAI; do not replay them.
- [ ] Custom Auth SMTP/sender, redirects, two-account real sign-in/revocation,
  unused password sign-in/leaked-password protection review.
- [ ] Real provider generation/PDF acceptance on the chosen Linux host.
- [ ] Backend Composio/Gmail/Hunter configuration and explicitly approved
  recipient send/reply/reconciliation tests, or launch with these disabled.
- [ ] Chosen-host resource/capacity measurements, HTTPS CORS/SSE/WebSocket checks,
  real permitted employer forms and exact-origin extension acceptance.
- [ ] External monitoring/alert delivery, retention/deletion policy and verified
  provider backup restore. Synthetic local restore is not a JobPilotAI recovery test.
- [ ] Public privacy/terms/contact content, full keyboard/screen-reader/zoom/device
  review and both themes. Sampled contrast/fixture browser checks are not certification.
- [ ] Required remote CI/branch protection and approval of exact release revision.

The clean backend audit has four reviewed Chroma server-path exceptions, expiring
7 December 2026. The app runs Chroma only in-process. See [dependency review](DEPENDENCY_SECURITY.md).
No unaccepted package findings passed the gate; do not describe this as zero vulnerabilities.

Baseline v2 remains default. No independent labelled dataset/quality lift is established;
BGE and CrossEncoder promotion, LambdaMART/bandits/clustering are not launch claims.
