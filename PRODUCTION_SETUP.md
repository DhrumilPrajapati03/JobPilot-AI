# JobPilot: remaining setup before launch

7 November 2026. Code/local verification and live readiness are separate.
The user chose **finish code and list setup steps** for missing credentials.
No final push, deployment, paid provisioning or live outbound messages occurred.

## Implemented

- Career Desk landing/login/workspace, real overview/activity, mobile navigation
  and split job feed; existing routes and workflows preserved.
- R?sum? extraction fix, confirmed facts and existing matching/preparation.
- Private Interested/Not relevant feedback/reasons; opt-in visible impressions.
- Optional local reranking with baseline fallback; offline BGE/CrossEncoder comparison.
- Cited research, exact source snapshot with a reviewable cover draft, explicit save,
  failed-run recovery and private writing templates used by generation.
- Durable worker release configuration, quotas, strict sessions, locked dependencies,
  CI, security headers, worker crash recovery and synthetic backup/restore checks.

## Remaining operator steps

Google and GitHub login are implemented. Both providers were disabled in the live
JobPilotAI public Auth settings on 8 November; follow [social login setup](SOCIAL_LOGIN_SETUP.md)
to configure provider credentials and exact return URLs. Email login remains available.

| Step | Action and acceptance |
| --- | --- |
| Database | Verify JobPilotAI provider backup/recovery into an isolated project; approve/apply only the new release migration, run SQL/advisors. [Deployment guide](DEPLOY.md). |
| Auth email | Configure custom SMTP/sender/domain and exact redirect URLs. Test two recipients, resend/rate-limit/expiry and logout/revocation. Review unused password sign-in/leaked-password protection. Magic links are not intentionally limited to one app user. |
| Linux image | Re-run image build and `scripts/check_image.py` on a reliable connection/CI. Package downloads timed out locally; Linux runtime/PDF/model/resource checks remain pending. |
| Runtime | Match API/worker JobPilotAI credentials and durable production settings. Run a continuous worker; `/ready` must show DB/worker ready. |
| Generation | Configure selected provider/key/model; import fictional r?sum?, confirm facts and generate materials. Check real PDF and truthful fallback states. |
| Gmail/Hunter | Set backend `COMPOSIO_API_KEY`, `COMPOSIO_GMAIL_AUTH_CONFIG_ID`, callback identity verifier and `HUNTER_API_KEY`. Chat plugin connections do not configure the application. Validate two-account OAuth ownership before enabling mailbox. |
| Mail acceptance | Sending stays off until a separately approved test to a chosen recipient. Verify revision/sender/PDF approval, acceptance/replies/disconnect, bounce/unsubscribe stops and uncertain-send reconciliation. Never blindly retry uncertain sends. |
| Digest | If enabled, configure `RESEND_API_KEY`, verified `DIGEST_FROM`, selected recipient; explicitly request/verify a digest. Worker scheduling replaces sleeping-server cron. |
| Extension | Update exact frontend/API origins in `extension/policy.js` and `manifest.json`, reload/reconnect. Review permitted real multistep/custom forms, uploads/rejections and confirmation; user submits. |
| Monitoring | External `/ready` and private `/ops/metrics` polling/alerts; optional sanitized `SENTRY_DSN`. Test alert delivery using synthetic incidents; measure host capacity. |
| Privacy/retention | Approve retention/deletion process and public privacy/terms/contact information before public onboarding. Review Gmail/audit/PDF/backup retention separately. |
| Release | Review exact changes and evidence, enable required CI/branch protection, approve final push/deploy. Release matching API/worker revision, rebuild frontend, record rollback. |

Gmail/Hunter/digest can remain disabled as optional integrations. Their live behavior
is unverified until configured and accepted. No v3 quality improvement is claimed.

## Quick local review

Stop the old backend before switching environments. Windows held DLLs in the old
`.venv`; use the clean release environment. Local `.env` files were not changed.

```powershell
cd backend
$env:DEBUG='false'
$env:EXECUTION_MODE='durable'
.venv-release/Scripts/python.exe -m uvicorn app.main:app --reload
```

Start `.venv-release/Scripts/python.exe -m app.workers.runner` in another terminal
with the same directory/environment. Run `npm ci`, `npm run dev` in frontend.
**New features require the new migration first**. Until rollout, use existing
flows or isolated fixture tests. Manual UI edits on JobPilotAI affect existing data.

UI journey: sign in ? Profile/import/confirm/preferences ? Jobs/scan/filter/feedback
? prepare ? Applications/Research/sources/draft/review/save ? Templates/save/reload
? Apply queue/extension/review ? submission report ? Analytics. Check Overview run
stages, retries, mobile drawer/focus, dark mode and a separate second account.

## Retention and experiments

After approving a retention cutoff, trusted service-only SQL may run:

```sql
select public.prune_release_telemetry(now() - interval '90 days');
```

This prunes recommendation snapshots/impressions and usage counters/receipts,
not applications, feedback, sources or emails. Minimum retention is 30 days.
No automatic cleanup schedule was enabled; configure it through approved operations.

Install `requirements-ml.txt` in a separate reviewed environment for optional ML.
Prepare models with `scripts/prepare_models.py --repository <repo> --revision
<40-hex-commit> --destination <dir>`; evaluate using
`scripts/evaluate_recommendations.py <private-labels.jsonl> --reranker <dir> --bge <dir>`.
Inference is local-only, remote code disabled, file hashes checked. Review independent
groups, Precision/Recall/NDCG, eligibility, memory and target-host latency. At least
100 independent groups and `recommendation/evaluation.py`'s gate are needed for a
promotion proposal. No automatic training/promotion. Leave `RERANKER_PATH` empty
until prepared/audited/evaluated. Baseline v2 stays default; LambdaMART/bandits/
clustering remain future scope.
