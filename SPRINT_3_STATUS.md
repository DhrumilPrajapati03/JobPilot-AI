# Sprint 3: job matching v2 and the identity vault

Implemented and verified in development on 27 October 2026. Deployment and live activation are deferred. The Sprint 1 follow-ups remain in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md); resolve its function-permission and search-path items before Sprint 4 connects real mailboxes.

## User workflow

1. Save your base resume in Profile.
2. Open **Profile → Review facts**, read the source facts, select those you have checked, and confirm they are accurate. Confirmation is a user declaration, not an independent credential or background check.
3. In **Profile → Preferences**, set the career target, professional experience, work authorization countries, remote preference, target roles, and existing skip rules. Existing users keep the default **Any career level** until they choose a target; experience is never guessed from dates or inferred from age.
4. Scan followed boards to apply the current preferences and confirmations to stored and new openings.
5. Expand **Why this match** in the job feed to inspect ranking components, skill evidence, eligibility decisions, and quoted source evidence.
6. Automatic drafting requires all current saved resume facts to be confirmed and no unresolved eligibility conflict. Manual preparation remains available for user review; manual generation does not label unconfirmed facts as verified.

Profile/content changes invalidate the relevant client queries. Match scores and explanations are snapshots from the last scan; saving preferences or confirming facts does not silently run another board scan. Review-required jobs are kept in the skipped tab, subject to the existing India hiring-scope visibility guard.

## Resume facts and provenance

`app/services/identity.py` derives facts from the saved base resume: identity, headline, summary, skills, employment, projects, education, and certifications. Each fact carries a source path and a deterministic ID. A SHA-256 digest covers the normalized resume content while excluding row IDs, user IDs, timestamps, and the storage version.

`identity_confirmations` stores only owner, content digest, fact ID, and confirmation time. Fact content is re-derived from the current source; clients do not submit new fact text through the confirmation API. A changed content digest makes previous confirmations inapplicable. Metadata-only changes preserve them. Old confirmation rows are retained as historical attestations; retention/cleanup remains an operational follow-up.

The API rejects unknown fact IDs and returns 409 when the submitted source digest is stale. Confirmation never happens automatically on upload, save, or AI extraction. Owners can revoke individual facts. Database grants and RLS permit owner-only reads, inserts, and deletes; clients cannot update/reassign confirmation rows or access another owner's confirmations.

| Endpoint | Behavior |
| --- | --- |
| `GET /api/v1/profile/facts` | Current source facts, confirmation states, counts, and source digest |
| `POST /api/v1/profile/facts/confirm` | Confirm selected IDs against the supplied current digest; up to 500 per batch |
| `DELETE /api/v1/profile/facts/{id}` | Revoke the current owner's confirmation for that fact ID |

## Structured eligibility

`app/services/eligibility.py` returns `eligible`, `ineligible`, or `review`, with separate checks and source evidence for location, seniority/experience, work authorization, and remote arrangement.

- The existing India-focused hiring policy remains in force. A remote or APAC label alone does not establish India eligibility; explicit exclusions and foreign authorization restrictions remain blocking.
- Explicit senior, staff, principal, lead, and numbered engineer levels are checked against the declared career target. Mandatory experience minima are checked against reported experience; ranges use their lower bound. Entry/intern targets without reported experience use a conservative two-year ceiling for rejecting clearly experienced roles.
- Preferred experience, company history, and equipment-benefit durations do not become mandatory candidate requirements. Supported written-number and numeric forms are handled locally.
- Missing experience, ambiguous seniority for a selected career target, unknown remote arrangements, or unconfirmed explicit authorization requirements produce review decisions.
- A positive similarity score cannot override an eligibility conflict. Ineligible jobs score zero; review-required jobs are capped at 60 and cannot be automatically drafted.
- Both execution modes recheck confirmation and eligibility before starting queued automatic work. Durable graph recovery also rechecks revoked confirmations, disabled automatic drafting, and source-snapshot changes before cached stages or a material commit. An old automatic snapshot whose resume changed requires a deliberate new generation, rather than silently rewriting saved checkpoints.

Eligibility is a deterministic screening aid based on declared preferences and employer text, not legal work-authorization verification. Nonstandard requirement wording can remain ambiguous; users still review the original opening.

## Ranking and explanations

The fallback score retains 40% role relevance and 60% smoothed skill coverage. With cached MiniLM available, the final score is 85% of that score plus 15% resume/job embedding cosine similarity. Title relevance also permits a conservative semantic rescue for paraphrased titles; managerial mismatches retain their exclusion guard.

Skill matches distinguish terms evidenced in the base resume from terms with user-confirmed source evidence. Unconfirmed base content can still support a visible soft ranking, but does not unlock automatic drafting. Scores are ranking heuristics, not hiring probabilities or calibrated confidence estimates.

Persisted `job_postings.matching_details` includes the algorithm version, score components and weights, semantic model/fallback state, confirmation summary, matched confirmed skills, eligibility checks, and explanation text. Source descriptions remain private backend data and are omitted from the feed response as before; short evidence excerpts are included for review.

Rescans refresh existing title, location, remote arrangement, URL, and any supplied description/date without resetting posting identity or user state. Eligibility is then recomputed for open new/skipped postings. Board responses that omit an existing description preserve its last supplied value; full employer-text freshness still depends on the board response.

`app/services/matching_semantics.py` uses the existing Chroma ONNX `all-MiniLM-L6-v2` model on CPU. It never calls a provider or downloads a model during matching. All required model files must already be installed in Chroma's model cache. Missing, disabled, or failed inference produces an explicit role/skill fallback. A bounded, owner-keyed in-memory cache holds vectors; no new vector database collection is created. Chroma is pinned to the tested 1.5.9 API. See [Chroma's embedding documentation](https://docs.trychroma.com/docs/embeddings/embedding-functions).

`MATCHING_SEMANTIC=true` is the default. Set it to `false` to use the fallback explicitly. Install/warm the local model during development or image preparation before starting workers; this sprint did not change deployed images or download model files. Restart the process after adding a previously missing model cache. Multiple worker processes each need memory for their own model instance.

## Deduplication

`app/services/job_identity.py` replaces company/title-only identity with conservative opening identity:

- Canonical URLs remove tracking parameters/fragments, normalize the Greenhouse hostname, and retain requisition-identifying query parameters.
- Distinct first-party requisition URLs remain distinct even when titles, cities, and descriptions match.
- Without a strong first-party opening URL, sufficiently detailed identical content plus company/title/location can provide a secondary identity. Weak descriptions or missing URLs fall back to source/external ID, favoring separate rows over a false merge.
- A per-owner unique partial index protects nonempty stored dedupe keys. The existing source/external-ID uniqueness remains in place.
- A duplicate opening still present on another scanned board prevents the canonical stored row from being marked closed during that scan.

Existing postings/applications are not mass-merged, deleted, or backfilled by the migration. Legacy identity keys remain blank and their aliases are derived when scanning; previously stored duplicates can remain. Cross-board aliases are not persisted as a separate source-history table. Different aggregator URLs with rewritten descriptions can remain separate, and an unscanned alias cannot prove that a previously closed canonical posting is still open.

## Resume generation safeguards

The previous validator treated JD keywords as permission to introduce skills. They are now only employer requirements, never evidence of candidate qualifications. Validation checks employer/role/date combinations, education and certification identities, project identity/technology, unsupported numeric claims, and recognized technologies against the base resume.

If a generated resume violates these checks, the tailor falls back to the whole base content and reports a fallback warning. It no longer fixes only selected date/tag fields while retaining potentially fabricated bullets. RAG snippets and employer text are explicitly subordinate to the current base resume.

This is a bounded validator for structured facts, recognized technologies and numbers. It does not prove that every possible natural-language claim is faithful. Free prose, cover letters, messages, and form answers still require human review. Direct user edits to a tailored resume remain deliberate user edits.

## Evaluation and verification

`backend/evaluations/matching_cases.json` contains 37 manually labeled synthetic cases for entry/graduate roles, senior titles, mandatory and preferred experience, India/foreign/ambiguous geography, sponsorship, authorization, remote arrangements, unrelated occupations, and role paraphrases. These are regression cases, not an independent production benchmark or a representative job-market sample.

| Mode | Eligibility accuracy | Precision | Recall | False positives |
| --- | --- | --- | --- | --- |
| Cached MiniLM | 100% | 100% | 92.86% | 0 |
| Explicit role/skill fallback | 100% | 100% | 85.71% | 0 |

MiniLM retrieves the artificial-intelligence developer paraphrase that the fallback misses. Both modes conservatively miss the broader “Graduate Applied Scientist, NLP” example. The reports preserve these mismatches rather than changing labels to make every case pass. They are stored in `matching_semantic_report.json` and `matching_lexical_report.json` next to the dataset.

From `backend`, reproduce the evaluation without loading developer `.env` credentials:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_matching.py --semantic
.\.venv\Scripts\python.exe scripts/evaluate_matching.py
.\.venv\Scripts\python.exe tests/run_offline.py
```

The expanded backend suite passes 237 tests, including the cached-model integration test on this machine. On a machine without the installed model, that optional integration test skips explicitly while deterministic fallback tests still run. The frontend passes 12 tests covering existing account isolation/streams plus fact rendering, safe text escaping, provenance labels, revocation controls, and match explanations. The production build passes.

`backend/supabase/tests/matching_v2_identity.sql` passed on hosted `test-project`. It verifies owner-only confirmation/read/revoke, blocked foreign inserts, immutable ownership grants, duplicate confirmation behavior, per-owner opening uniqueness, distinct requisitions, and stored explanation data. Fixture users and business rows roll back; a follow-up query confirmed zero remaining test confirmations, postings, or fixture users.

## Migration and remaining release work

Apply all prior migrations before `backend/supabase/migrations/20261027140016_matching_v2_identity_vault.sql`. It was applied only to `test-project` (`klhpguohtcrsidqjwbqh`) as `20261027153031_sprint_3_matching_v2_identity_vault`. MCP and local CLI timestamps differ; reconcile migration history against the actual schema before using CLI `db push`. The live `JobPilotAI` database and local runtime configuration remain unchanged.

The security and performance advisors reported no new Sprint 3 findings. Existing warnings remain deferred, including the test project's `set_updated_at` search path ([Supabase remediation](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable)) and unrelated baseline policy/index recommendations.

Before release, validate real two-account browser flows, source import/confirmation/revocation, actual employer descriptions, representative labeled job data, model warm-up/resource use on the intended host, and migration-history reconciliation. Deployment and the carried Sprint 1 production checks remain separate release gates.
