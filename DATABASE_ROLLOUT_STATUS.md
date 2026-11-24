# JobPilotAI database rollout — 30 October 2026

The user chose to apply the remaining feature migrations to the existing
`JobPilotAI` project (`vgpkzekcfnogvvykfzoo`) for local UI testing. Both local
environment files already target this project and were left unchanged.
Application deployment remains deferred. Keep `test-project`
(`klhpguohtcrsidqjwbqh`) for isolated SQL fixtures and future migration trials.

## Applied migration history

The Sprint 1 security guards and Sprint 4 mailbox security preflight were already
installed and were not replayed. Eight committed migration files were applied in
dependency order after a successful transaction that trialled all eight and
rolled back. Five-second lock and sixty-second statement timeouts bounded each
application. No original baseline tables were recreated.

| Local file | JobPilotAI migration version / name |
| --- | --- |
| `20261027055731_durable_execution.sql` | `20261030065929_sprint_2_durable_execution` |
| `20261027062316_durable_execution_indexes.sql` | `20261030065941_sprint_2_durable_execution_indexes` |
| `20261027140016_matching_v2_identity_vault.sql` | `20261030065945_sprint_3_matching_v2_identity_vault` |
| `20261028043147_gmail_outreach_workflow.sql` | `20261030065950_sprint_4_gmail_outreach_workflow` |
| `20261028045823_mailbox_sender_guards.sql` | `20261030065954_sprint_4_mailbox_sender_guards` |
| `20261028113722_application_execution_evidence.sql` | `20261030065958_sprint_5_application_execution_evidence` |
| `20261028115607_application_execution_indexes.sql` | `20261030070002_sprint_5_application_execution_indexes` |
| `20261029155926_product_validation_metrics.sql` | `20261030070007_sprint_6_product_validation_metrics` |

MCP timestamps differ from local filenames and development history. Match actual
schema and this mapping before any future CLI history repair or `db push`.
Earlier sprint documents describe the rollout state at their original dates;
their statements that live lacked these migrations are superseded by this record.

## Verification

- Trial schema changes rolled back completely before the recorded applications.
- Counts and order-independent row-content checksums matched before and after
  both the trial and final rollout for all fourteen existing public tables.
  The comparison excludes only the two newly added `job_postings` columns.
- Existing records retained: 11 applications, 10 tailored resumes, 1 base resume,
  30 email drafts, 1,101 network contacts, 20 sources, 74 postings, 23 saved
  answers, 2 extension tokens, 1 profile and 1 autopilot state. Other original
  public tables remained empty. Auth user and Storage object counts were unchanged.
- The current job-feed column projection works under the existing owner's
  authenticated database role. Owner-scoped product metrics return 11 generated
  applications, zero newly recorded workflow/Gmail outcomes and null unsupported
  measures. This is a database-contract check, not a browser login test.
- Every public table has RLS enabled. Clients cannot mutate the queue, invoke
  service-only mail/health commands or select frozen PDF payloads directly.
  The reviewed feature RPCs remain invoker functions.
- Security Advisor still reports only the previously documented disabled leaked
  password protection. Performance advisories remain on original tables/policies;
  none of the thirteen missing-FK-index findings concerns a newly added table.
- No fixture accounts, worker records, application events or outbound messages
  were created by these checks. No real email or employer application was sent.

Automatic approval review rejected a proposed broad local application-data
snapshot because it would export sensitive live records beyond the migration
request. The export did not execute and no snapshot was created. The rollout used
transactional rehearsal and aggregate checksums instead. A complete backup and
restore exercise is still a production-readiness task; checksums are not backups.

## Local manual testing

Restart the local API and refresh the frontend. Test Job feed, Profile & resume,
application details and Analytics against the existing account. Changes made
through this UI now affect the existing JobPilotAI data, including test reports
and edits; use clearly identified test applications.

The backend currently uses the default `inline` execution mode. That permits the
normal generation flow, but it does not exercise durable worker persistence or
recovery. To test those features without editing `.env`, start both processes in
separate PowerShell terminals from the repository root:

```powershell
cd backend
$env:DEBUG = 'false'
$env:EXECUTION_MODE = 'durable'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

```powershell
cd backend
$env:DEBUG = 'false'
$env:EXECUTION_MODE = 'durable'
.\.venv\Scripts\python.exe -m app.workers.runner
```

Stop the previous inline API before starting durable mode. Do not mix execution
modes against the same application; drain queued work before changing back.
Mailbox and send flags remain disabled. Auth SMTP restrictions and remaining
provider, employer, worker recovery, dependency and deployment acceptance are
unchanged. See [production readiness](PRODUCTION_READINESS.md).
