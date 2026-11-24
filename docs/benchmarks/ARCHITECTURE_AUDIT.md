# JobPilot AI technical architecture audit

Audit date: **12 November 2026, Asia/Calcutta**. Base Git SHA: `eb8c6d09a5bdfa472af8ed8ae619e952339d963a`.

This evaluates the **current dirty working tree**, including untracked recommendation/research code, rather than attributing all functionality to that commit. See [Git status](raw/git-status.txt), [307-file SHA-256 manifest](raw/source-manifest.json), and [242-module static inventory](raw/source-inventory.json). The inventory covers application, test, script, frontend and extension source; Python definitions were parsed with AST. Source inspection, focused execution-path review and offline checks establish implementation evidence, not deployment acceptance or a formal security certification. Ignored files, credentials, binary user data, dependencies and generated artifacts were excluded from the source manifest. No developer `.env` values were inspected.

## Implemented architecture

| Layer | Actual implementation and evidence | Verification boundary |
| --- | --- | --- |
| Web client | React 19, TypeScript, Vite, React Router, TanStack Query, Zustand; `frontend/src/App.tsx`, `frontend/src/lib/api.ts`, hooks, stores and pages | Production build and 35 offline component/auth/account tests passed; browser run qualification below |
| API | FastAPI routes in `backend/app/api/v1/`, mounted by `router.py` and `main.py`; bearer authentication and owner filtering | In-process TestClient tests; no live Supabase verification |
| Chat assistant | `agents/assistant.py`: custom LangChain tool-calling loop; maximum 6 steps, 2 malformed-tool-call retries, 5,000-character model-visible tool results; tools read account data, scan/draft jobs and propose edits | **Not a LangGraph chat agent**; synthetic tool/provider tests |
| Application generation | `agents/orchestrator.py`: sequential inline pipeline; `workflows/application.py`: **11-node linear LangGraph StateGraph** | Both paths implemented; default setting is `EXECUTION_MODE=inline`; durable mode requires migrations and worker |
| Durable execution | `services/runs.py`, `workflows/context.py`, `workers/runner.py`; PostgreSQL queue, lease tokens, separate heartbeat thread, checkpoint reuse, bounded exponential retry and transactional material-saving RPC | Fake-store recovery regressions passed; actual PostgreSQL recovery was not rerun |
| Canonical database/auth/storage | Supabase PostgreSQL, Auth, Storage; `services/supabase.py`, `services/auth.py`, `frontend/src/lib/supabase.ts`, `backend/supabase/migrations/` | 19 migrations and 7 SQL test files found; local SQL execution blocked by unavailable Docker daemon |
| Resume retrieval | Persistent local Chroma, user metadata filters, bullet/summary/project/skill chunks, deterministic source digest; `services/vector_store.py` | Distinct from job-ranking similarity; no claim of measured retrieval quality |
| Job discovery | `services/job_boards.py`, `services/discovery.py`: Greenhouse, Lever, Ashby, SmartRecruiters, Himalayas, Remotive; bounded fetching, normalization, local fit scoring, rescoring and auto-draft guards | HTTP MockTransport fixtures; no live crawl in this audit |
| Identity evidence | `services/identity.py`: fact IDs, source paths, content hashes and revocable user confirmations | User attestation, not independent verification of credentials |
| Application preparation | `services/form_answers.py`, `application_execution.py`, `autopilot.py`, extension background/content scripts | Frozen PDF/evidence, supervised filling, event replay and account guards; synthetic browser forms only |
| Outreach | Cover-letter/email/DM drafting, referral CSV matching, Hunter research, Composio Gmail broker/mailbox, Resend digest | Implemented integrations; no real provider calls, emails or employer submissions executed |
| Observability | `services/observability.py`, `workflows/context.py`, product-metrics SQL migration and operations routes | Per-process route histogram and stage-duration instrumentation exist; task cost and full workflow evaluation absent |

The durable graph executes `jd_parsing → profile_loading → resume_tailoring → pdf_rendering → cover_draft → email_drafts → dm_drafts → outreach_generation → database_saving → referral_check → form_preparation`. State carries the run ID; outputs live in the custom execution context/checkpoints. Recovery reconstructs the graph and skips checkpointed work. This is an explicitly ordered workflow, not autonomous multi-agent planning. The inline orchestrator uses multiple specialized agent classes but is not itself a LangGraph graph.

## LLMs and embedding models

`backend/app/services/llm.py` implements three chat providers through `ChatAnthropic`, `ChatOpenAI` and `ChatGroq`. Automatic selection chooses the first configured provider in **Anthropic → OpenAI → Groq** order; it does not implement cross-provider runtime failover. `LLM_PROVIDER` and `AGENT_PROVIDER`/`AGENT_MODEL` can override selection. Source defaults are:

| Provider | Source model identifiers | Behavior |
| --- | --- | --- |
| Anthropic | `claude-sonnet-5-5` | Default string in code; availability and output quality **NOT VERIFIED** |
| OpenAI | `gpt-4o` | Configurable default; no live call |
| Groq | `openai/gpt-oss-120b`; fallbacks `openai/gpt-oss-20b`, `qwen/qwen3.8-27b` | Light tasks start with `openai/gpt-oss-20b`; ModelChain handles quota/capacity/unavailable errors with cooldowns; no fallback after streaming output begins |

These are implemented configuration identifiers, **not evidence of which model a deployed account uses**. Real runtime selection, key validity and provider model availability are BLOCKED from verification without an approved integration run. No model quality claims follow from a client wrapper existing. Generation defaults to temperature 0; HTTP timeout is 60 seconds. Groq chain clients use one SDK retry per model. Structured output uses Pydantic schemas; Groq JSON mode receives explicit schema instructions, OpenAI uses function calling, and Anthropic uses its structured-output adapter.

Embedding paths in `services/llm.py`:

- **Default local**: Chroma's ONNX `all-MiniLM-L6-v2`, CPUExecutionProvider, 384-dimensional model. `matching_semantics.py` refuses runtime downloads and returns an explicit unavailable/disabled status; vectors use a bounded owner-scoped 512-entry cache and lock. The cached model ran on all 37 semantic benchmark cases. Exact local artifact hashes are in [minilm-artifacts.json](raw/minilm-artifacts.json); upstream revision is not recorded in this cache, so no revision is invented.
- **Hugging Face API**: `sentence-transformers/all-MiniLM-L6-v2` through HF inference; falls back to local MiniLM after a failure. Not invoked here.
- **OpenAI embeddings**: `text-embedding-3-small`, separately named Chroma collection. Not invoked here. Different model vector spaces are isolated.
- **Experimental reranker**: optional local CPU SentenceTransformers CrossEncoder, max length 512; prepared safetensors/config/hash manifest required. No concrete reranker model path is enabled by default. `evaluate_recommendations.py --bge PATH` supports a separately prepared embedding experiment; **BGE is not an implemented production default**. SentenceTransformers is absent in the audited interpreter.

The repository lists Celery and Redis dependencies and has a legacy Redis compose file, but source inspection found no active Celery task/worker execution path. The implemented durable queue is PostgreSQL. Likewise, ADZUNA settings do not demonstrate an implemented discovery adapter.

## Matching and recommendation algorithms

Evidence: `services/job_matching.py`, `eligibility.py`, `job_filters.py`, `job_identity.py`, `discovery.py`, `recommendation/ranking.py`.

1. Normalize aliases and title words, strip seniority/stop words, and use six-character stems. Title similarity is maximum Dice overlap against preferred roles, with guards against generic engineer overlap and unintended management roles.
2. For low title overlap, MiniLM can rescue paraphrases when role-title cosine is at least **0.58**. Discovery's minimum title threshold is **0.50**. The reported Fit title value is rounded; title rescoring/filtering also uses the title matcher directly.
3. Recognize a fixed technology vocabulary plus resume skills. Let `m` be evidenced matched skills and `n` the recognized skills in the posting. Skill component = `min(1, ((m+1)/(n+2))/0.75)`. Lexical score = `100 × (0.40 × title + 0.60 × skills)`. When local embeddings work, blend `0.85 × lexical + 0.15 × cosine × 100`.
4. Apply deterministic eligibility: `eligible`, `ineligible`, `review`; checks cover geography, career level/experience, authorization/sponsorship and remote arrangement. Ineligible score becomes 0; review score is capped at 60 and is blocked from automatic drafting. The policy identifier is **india-v2**: it is explicitly India-focused, despite country/preference helpers. Broad APAC/remote labels alone are insufficient.
5. Apply skip rules, configured score threshold, identity confirmation and auto-draft limits. `matching_evaluation.py` tests the conjunction of eligibility, no flags, minimum title score and preference score. Its precision/recall are **binary relevance metrics**, not Precision@K/Recall@K.
6. Canonicalize URLs while retaining requisition parameters, normalize Greenhouse hosts, remove tracking parameters and hash conservative URL/content/source identity keys. Different first-party requisitions are preserved; duplicate handling is not part of the 37-case benchmark.
7. Experimental reranking operates only on up to 20 already-eligible candidates; preserves baseline scores, has deterministic ties and returns explicit baseline fallback on unavailable/invalid models. Snapshots and user feedback in `recommendation/service.py` are observations, not independent labels or learned model quality. `promotion_allowed` requires at least 100 independently labeled groups, zero eligibility errors, better nDCG, non-decreasing precision/recall and resource budgets; no candidate was promoted.

The ATS score in `resume_engine/validator.py` is normalized keyword coverage, not a commercial ATS result, hiring probability or semantic relevance metric.

## Functionality status

| Status | Capability | Evidence/qualification |
| --- | --- | --- |
| Implemented; exercised offline | Auth/account guards, profile/resume ingestion, fact confirmation, discovery matching/eligibility, application materials/editing, referral matching, form preparation and evidence | `backend/tests/`, frontend tests and extension suites; boundaries use synthetic data/mocks |
| Implemented; exercised offline | Chat tools, structured provider adapters, model fallback, durable checkpoint/recovery logic | `test_assistant.py`, `test_model_chain.py`, `test_resume_import.py`, `test_durable_execution.py`; no genuine LLM generation measured |
| Implemented, acceptance partial | PDF export through active `resume_engine/renderer.py` (Tectonic/LaTeX path with HTML/WeasyPrint alternative), rendering validation | Full Linux release image/host rendering not verified in this audit; pipeline tests can stub renderer |
| Implemented, external integration unverified | Supabase Auth/PKCE, RLS/RPCs/Storage, board adapters, Hunter, Gmail/Composio, Resend | Requires approved accounts/sandbox checks; synthetic callbacks do not verify live OAuth |
| Experimental/partial | CrossEncoder/BGE comparison, ranking promotion and label collection | Scaffolding exists; independent ranking corpus, candidate weights and measured promotion evidence missing |
| Partial safeguards | Tailoring factual consistency | Fixed facts, credentials, known skills and numbers checked; fallback restores base resume. A diagnostic unsupported leadership claim escaped detection; no semantic truth proof |
| Stub/planned | `agents/tracker.py` TrackerAgent | Methods raise NotImplementedError. Working tracker API/material persistence exists separately; calendar-agent integration is not established |
| Stub/legacy | `services/pdf.py` | Raises NotImplementedError; does not negate the active resume-engine renderer |
| Not instrumented | Per-call LLM tokens, average API cost/task, comparable human time savings | Usage limits count operations, not tokens; product-metrics SQL explicitly returns null cost |
| Not established | Autonomous employer application success, independently verified submissions, production quality or business impact | Submission attempts, browser observations and user reports are intentionally different evidence classes |

## Existing evaluation and measurement inventory

- `backend/evaluations/matching_cases.json`: 37 short synthetic labeled cases, one base candidate (some preference overrides), 14 relevant/23 non-relevant; eligibility labels 17 eligible/13 ineligible/7 review. `scripts/evaluate_matching.py` executes `_evaluate`; checked-in lexical/semantic JSON reports exactly reproduced.
- `services/matching_evaluation.py`: eligibility accuracy, relevance precision/recall, FP/FN, model-use count and per-case outcomes. Does not compute F1; this audit independently recomputes it from counts.
- `scripts/evaluate_recommendations.py`, `recommendation/evaluation.py`: graded relevance 0–3, P@K/R@K/nDCG@K and p95 ranker call time. No independent JSONL ranking dataset found. Existing precision divides by returned length for short lists; strict P@5 would require a fixed denominator of 5. Max 20 postings/group makes recall shortlist-conditional unless all relevant items in the retrieval universe are labeled. It rejects review/ineligible inputs, so it cannot measure candidate-generation/eligibility losses.
- `backend/tests/`: 19 regression files; 338 collected tests passed. Security, parser/ingestion, pipeline, identity, matching, discovery, model chain, Gmail, execution and recovery use in-memory stores, stub agents or MockTransport where external boundaries are involved.
- `frontend/tests/`: 7 Node test files; 35 tests passed, including compiled React rendering and auth/account logic. `frontend/e2e/`: 3 files/14 tests reported individual passes, but the run stalled afterward; overall run interrupted. `extension/tests/security.test.cjs`: 7 tests passed; `extension/tests/browser/extension.spec.cjs` and `forms.spec.cjs`: 15 passed on local Chromium fixtures.
- `backend/supabase/tests/`: 7 SQL suites; `scripts/check_database.py`, `check_worker_recovery.py`: disposable PostgreSQL migrations/RLS/RPC/recovery/restore checks. Not rerun: Docker daemon unavailable. `scripts/check_image.py`: release-container smoke verification, not a quality benchmark. `check_audit.py`: dependency vulnerability gate, not a matching benchmark.
- `backend/test_supabase.py`: live admin-client diagnostic; deliberately excluded from offline pytest to avoid unintended hosted access. `backend/test_vector_store.py`: manual integration-like diagnostic with persistent sample writes and potentially configured external embeddings; excluded from preserve-data offline checks.
- `workflows/context.py` emits per-stage `duration_ms`; `services/observability.py` holds request counts/mean and bucketed p95 since process startup. SQL `20261029155926_product_validation_metrics.sql` aggregates stage timing, preparation event intervals and run outcomes. These are instrumentation paths, not measured production latency in this audit. Application-created-to-form-prepared time includes waits/user delays and is not an AI-vs-human timing comparison.
- `SPRINT_1_STATUS.md` through `SPRINT_6_STATUS.md`, `RELEASE_READINESS.md`, `PRODUCTION_READINESS.md`, `PROJECT_ANALYSIS.md`, `DATABASE_ROLLOUT_STATUS.md`, `DEPENDENCY_SECURITY.md`, release CI and operations docs contain prior status/acceptance statements. Historical counts (e.g. 27 frontend / 9 browser tests) describe older snapshots; they are not substituted for current measurements or live state. CI configuration existence does not prove a green CI run.

## Audit conclusion for resume claims

This is credible evidence of applied GenAI engineering: structured generation, retrieval, deterministic policy gates, guarded tool calling, durable workflow recovery and a reproducible synthetic model comparison. It does **not** establish production adoption, model training/fine-tuning, autonomous multi-agent planning, hallucination elimination, employer acceptance, paid-provider quality, cost savings or human time savings. See [results and supported bullets](BENCHMARK_RESULTS.md) and [evaluation/improvement plan](EVALUATION_PLAN.md).
