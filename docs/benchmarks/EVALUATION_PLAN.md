# Reproducible quality and reliability evaluation plan

Date: 12 November 2026. Baseline: working tree at `eb8c6d09a5bdfa472af8ed8ae619e952339d963a`, identified by [source hashes](raw/source-manifest.json). **This is a proposed experiment, not completed measurements.** No production behavior changes, live job applications, emails, downloads or paid API calls are authorized by this plan.

## Dataset and independent labels

Collect **150 actual public postings**, frozen with source URL, fetch timestamp, requisition ID, employer, full text, content SHA-256 and permission/retention notes. Target AI, GenAI and agentic engineering roles plus nearby negative roles, across the six implemented boards. Keep sensitive candidate data private. Do not manufacture 150 labels by copying the existing 37 synthetic cases, using model output as truth, or treating user clicks as relevance labels.

Use **six fixed candidate profiles** with explicit source facts, skills, professional experience and preferences: (1) 1-year Python/API/RAG engineer; (2) 1-year ML/data engineer; (3) 2-year TypeScript/LLM application engineer; (4) 3-year backend engineer entering GenAI with no evidenced model training; (5) new graduate with project-only evidence; (6) 5-year MLOps engineer. Mark each fact as professional/project evidence or unknown. Include different remote preferences, authorized countries and sponsorship needs. These are benchmark profiles, not claims about the user's experience. Primary application scope remains India-focused; non-India acceptance is a policy-generalization stress test and must be reported separately.

Label all **900 profile–posting pairs** for eligibility and graded relevance. This is 150 postings and six profiles, not 900 independent postings. Freeze approximately 30 pilot, 30 validation and 90 held-out postings with seed `20261112`, assigning entire employer/requisition/duplicate clusters to one partition. Persist the resulting split manifest so a seed alone is not relied on for reproduction. Tune thresholds only on pilot/validation. Report held-out results first; any all-corpus descriptive result must identify the tuning overlap.

Ensure overlapping challenge tags cover: at least 20 ambiguous/conflicting requirements; 20 unsupported or missing must-have skills; 25 geographic/authorization/sponsorship restrictions; 15 seniority/experience contradictions; 10 malformed/missing fields or hostile instructions; and at least 10 duplicate clusters with observed cross-board copies. Include positive paraphrases, preferred-versus-required experience, company-age distractors, generic titles, expired roles and identical titles for distinct requisitions. These quotas are proposed collection requirements, not evidence the data already exists. Publish challenge-set and natural-sample results separately, since quotas distort prevalence.

Two technically qualified annotators independently label without seeing model scores. A third adjudicates disagreements using quoted evidence. Record annotator IDs, original judgments, confidence, agreement (raw agreement plus Cohen's kappa/weighted kappa), adjudicated label and rationale. Missing facts remain `review`, rather than assumed eligible. Relevance grades: 0 unrelated or explicitly unqualified; 1 weak/adjacent with major gaps; 2 plausible fit with explainable gaps; 3 strong evidenced fit. Predeclare binary relevance as grade ≥2; independently store unmet mandatory requirements and eligibility status. Human labels must not be derived from the same regex/policy code being evaluated. Publish the business-policy rubric separately from legal employment eligibility.

Suggested private JSONL records:

```json
{"posting_id":"p001","duplicate_cluster":"d001","employer_cluster":"e001","split":"test","source_url":"https://example.invalid/jobs/1","captured_at":"ISO-8601","content_sha256":"...","title":"...","description":"...","location":"...","remote":null,"challenge_tags":["ambiguous_geo"]}
```

```json
{"profile_id":"c01","posting_id":"p001","annotator_id":"r01","eligibility":"review","relevance":2,"must_have_gaps":[],"evidence_spans":["..."],"rationale":"...","adjudicated":false}
```

Candidate facts and gold labels must live in separate immutable versioned files. Reject duplicate IDs, missing pair labels, invalid grades and model-derived labels. Deduplicate the main ranking universe at requisition-cluster level; score raw-copy detection separately so duplicate removal does not silently improve precision.

## Metrics and denominators

| Objective | Measurement contract | Current status |
| --- | --- | --- |
| Eligibility | Exact 3-class accuracy; confusion matrix and per-class precision/recall/F1; false eligible = gold ineligible/review predicted eligible; report abstention/review rate and per-country/experience slices | Synthetic regression only; independent corpus **BLOCKED** pending labels |
| Matching P@5 | Number of distinct, gold-eligible jobs with relevance ≥2 in the first 5 positions / **5**, including unfilled positions as misses; also report short-list rate | **NOT MEASURED** |
| Matching R@5 | Same hits / all distinct gold-eligible relevant jobs in the frozen retrieval universe for that profile; undefined when denominator is zero, exclude from macro mean with count disclosed | **NOT MEASURED** |
| Ranking | nDCG@10 using gain `2^grade−1`, log2 discount and gold-ineligible/review jobs given gain 0 for end-to-end ranking; MRR = reciprocal rank of first gold-eligible grade ≥2 job | **NOT MEASURED** |
| Tailoring truth | Atomic supported claims / all checkable output claims; unsupported-claim rate = unsupported or contradicted claims / all checkable claims. Unknown/unverifiable claims reported separately; count empty outputs and missing key facts | **NOT MEASURED** for provider outputs |
| Workflow completion | Quality-qualified completed tasks / all scheduled eligible tasks; success requires persisted correct-owner materials, valid artifact, no unsupported critical claims, honest fallback status, no unintended external action | **NOT MEASURED** as a task rate |
| Recovery | Tasks satisfying the same success criteria after injected recoverable fault / all injected recoverable tasks; also duplicate writes, stale lease commits and repeated generation/provider calls | Fake-store test cases exist; measured task-rate experiment pending |
| End-to-end latency | Submit/enqueue to review-ready package; include queue wait, provider calls, backoff, validation, rendering and persistence. Median and nearest-rank p95, normal and fault cohorts separately | **NOT MEASURED**; local scoring timings are a different metric |
| Tokens and cost | Actual per-call input/output/cache/reasoning usage by provider/model; sum retries and failures; average total API spend across all attempts / quality-qualified completed tasks | **NOT MEASURED**; no token ledger implemented |
| Human timing | Paired manual vs AI-assisted preparation of equivalent review-ready material including corrections and verification | **BLOCKED** until comparable human timing data collected |

Measure eligibility alone, oracle-eligible ranking, and full retrieval/filter/ranking separately. Never hide jobs lost before reranking. Rank ties deterministically by stable posting ID. Report macro averages across candidate queries and per-profile results, plus numerator/denominator and employer-cluster bootstrap 95% intervals (2,000 resamples, fixed seed). With only six fixed candidate profiles, do not treat profile–posting pairs as independent queries or assert broad population significance. Inspect failures even when an aggregate improves.

The current ranking utility uses `grade>0` and divides precision by returned length; these differ from this protocol. A new **evaluation-only** adapter should precompute binary labels at grade ≥2, retain grades for nDCG, use fixed denominator 5 and evaluate the full frozen universe. Do not silently reuse the utility's output under different metric names. Existing `evaluate_recommendations.py` only supports 1–20 eligible jobs/group and is suitable for bounded shortlist comparisons, not full-universe recall. Its promotion gate needs at least **100 independently labeled groups**; six candidates over one corpus do not satisfy this by inventing more group IDs. Keep experiments in shadow mode until enough independent groups are collected or a separately reviewed gate change is approved.

## Execution protocol

1. Freeze a clean source snapshot/diff digest, dataset/profile/label hashes, prompts, exact package lock, CPU/RAM/OS, model IDs and immutable weight revisions/hashes, tokenizer, ONNX provider, thread limits, temperature, random seeds, input truncation, thresholds and cache settings. Pre-register metrics, exclusions, slice tags and acceptance criteria.
2. Run paired offline arms on identical postings: **A** lexical/rules; **B** MiniLM blend with current eligibility; **C** optional verified CrossEncoder/BGE shadow candidate only after model artifacts exist. Record model-unavailable fallbacks explicitly. Report cold process/model startup separately from warm inference; avoid concurrent unrelated jobs during timing.
3. Evaluate 900 labeled pairs and ranking queries without APIs. For latency, use at least 30 fresh-process cold batches and 100 warm batches on a stable target-like host, with cache-hit rates. These repeats measure timing variability, not additional quality samples. Collect peak RSS and concurrency saturation separately.
4. Select **60 stratified profile–posting pairs** for supervised draft-only provider evaluation. After explicit approval of provider, model and maximum spend, produce three repetitions per pair at frozen configuration (180 outputs). Independently annotate raw model output and final guarded output. Report fallback frequency, utility and fact retention so unchanged-base fallback is not mistaken for successful tailoring. Human review is the gold standard; a second LLM may triage but cannot supply the only truth label.
5. Run 60 normal workflow tasks and 60 fault-injected tasks against disposable local infrastructure/stub providers first. Allocate 10 tasks each to rate limit, timeout, malformed output, crash after checkpoint, crash after material transaction and lost lease. Verify store invariants independently. Reconcile nonrecoverable, safety-blocked, warning-success, degraded fallback and timed-out outcomes. Additional approved provider trials must be labeled separately from these synthetic fault tests.
6. Token instrumentation belongs at provider invocation/callback boundaries, before structured parsing discards response metadata; use run/stage/call/attempt IDs, usage units, model revision, status and latency without logging private prompts. Mark missing provider usage **unknown**, not zero. Price with a dated archived official rate sheet at run time; include failed/retried calls and distinguish API cost from hosting, local CPU and human-review cost. Do not hardcode guessed current prices. No paid-provider run is included here.
7. Optional human study: recruit at least 8 consenting participants, 4 comparable tasks each, counterbalanced crossover with equivalent but different postings. Freeze document requirements and quality rubric; include reading, edits, verification and export in both arms; collect active time and wall time separately. Report paired differences, quality parity and uncertainty. If this cannot be collected, leave time savings **NOT MEASURED**. Database event intervals cannot substitute for manual timing.

Store per-pair predictions, ranked IDs, stage/call attempts, failure categories and artifact digests in JSONL/CSV. Use fields such as `run_id`, `snapshot_sha`, `profile_id`, `posting_id`, `arm`, `seed`, `model_digest`, `expected`, `predicted`, `fallback`, `quality_success`, `duration_ms`, `input_tokens`, `output_tokens`, `cost_usd`, `fault_type`, `recovery_success`. Add a summary JSON with commands, sample sizes and null/status/reason fields for missing values. Raw personal documents and annotated claims require restricted storage; only aggregate/redacted results belong in public docs.

## Top three engineering improvements and paired A/B plans

These are evidence-based priorities, not implemented changes or promised gains. Production code remains untouched pending approval.

### 1. Fix role-paraphrase recall while preserving eligibility precision

Evidence: MiniLM recovers `semantic-developer-title`, but `semantic-research-title` remains a false negative because title match is 0 despite eligibility being correct. Current thresholds can discard candidates before detailed scoring. The recall gain is only one case out of 14 positives, so tuning on these examples alone would overfit.

Implement a reviewed role-family alias taxonomy plus an optional bounded eligible-shortlist reranker. Preserve explicit seniority, authorization and geography gates; include wrong-domain research, sales and management hard negatives. Version the taxonomy/model and retain baseline fallback status. Tune title rescue/blend only on the validation partition.

A/B: current MiniLM baseline vs aliases/threshold candidate, then reranker separately to isolate cause. Compare held-out eligibility false-eligible count, P@5/R@5/nDCG@10, false negatives by title slice, duplicate leakage, cold/warm p95 and peak RSS. Proposed acceptance: no new false-eligible cases, no P@5 regression, improved held-out R@5 or nDCG with uncertainty disclosed, and the existing resource gate where applicable. Stay shadow if independent-group requirements are unmet.

### 2. Ground generated claims in source facts, including semantic claims

Evidence: a constructed unsupported leadership claim passes `validate_no_hallucinations`; existing checks focus on fixed identities, vocabulary and numeric differences. Source evidence confirmation is user attestation; schema-valid prose can still invent responsibility or scope.

Implement structured claim-to-fact-ID attribution in an internal generation schema, validate fact IDs against the current resume digest, preserve role/project attribution, and flag scope/leadership/customer/deployment claims without evidence. Treat JD text and research sources as requirements/context rather than candidate credentials. Escalate ambiguous claims to review or restore source text; record pre-guard violations, post-guard output and fallback. Use human-adjudicated entailment examples before considering any secondary model judge.

A/B: existing prompt+validator vs fact-linked prompt+validator on the same 60 pairs ×3 outputs/arm after budget approval. Blind reviewers score raw/final unsupported-claim rates, critical factual changes, retained facts, usefulness and fallback rate. Also measure latency/tokens/cost; a safe but unchanged resume must not receive a quality-success label automatically. Proposed acceptance: no critical fabricated claims, reduced unsupported rate without losing source facts, and explicit latency/cost tradeoff. Small samples cannot prove a zero production hallucination rate.

### 3. Add an evaluation trace and batch retrieval before optimizing concurrency

Evidence: tokens/cost are absent; stage timings omit some total overhead; tailoring performs up to five synchronous per-skill retrieval calls and may refresh production resume state repeatedly; semantic similarity serializes inference. The frontend browser suite also exposes an unresolved shutdown reliability issue. Current warm-cache scoring is not end-to-end evidence.

Implement per-run queue/start/end/quality events and provider-attempt usage accounting; batch the five skill retrieval queries or validate/rebuild the source index once per source digest per task, offloading blocking CPU/DB work from the event loop where needed. Preserve user/model cache isolation, stale-resume checks and lease fences. Keep sequential writing until quota evidence supports bounded concurrency. Separately bound local fixture-server shutdown so CI has an honest terminal result.

A/B: instrumented current path vs batched retrieval on identical local tasks, then approved draft-only providers. Hold concurrency, cache state, token budget and fault schedule constant. Compare median/p95 total latency, retrieval calls/task, cache misses, completed quality-qualified tasks, recovered-task rate, duplicate material/provider calls and observed cost/completion. Require factual and eligibility parity and no stale/cross-account retrieval. Adopt only if observed latency/cost improves or reliability is demonstrably better; do not claim an improvement from fewer calls alone.

## Work remaining

Independent corpus collection/adjudication, complete ranking adapter, provider usage instrumentation and comparable human timing remain **NOT MEASURED/BLOCKED** as specified above. Restore local Docker availability to run the existing isolated PostgreSQL suites; resolve frontend test shutdown separately. Live provider access, budget and any external writes require explicit approval. No employer submission or outreach send is needed for any draft-quality experiment.
