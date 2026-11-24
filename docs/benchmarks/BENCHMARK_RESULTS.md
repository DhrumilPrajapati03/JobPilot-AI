# Verified benchmark results

Date: **12 November 2026, Asia/Calcutta**. HEAD: `eb8c6d09a5bdfa472af8ed8ae619e952339d963a`; measurements apply to the dirty working tree in [source-manifest.json](raw/source-manifest.json), not a clean checkout. No paid APIs, live emails or real job applications were triggered. Only benchmark documentation/scripts/raw artifacts were added; production source behavior was not changed.

## Reproduced matching benchmark

Dataset: `backend/evaluations/matching_cases.json`, version 1.0; explicitly **synthetic, manually labeled regression cases**, not real employer data. There are 37 cases, 14 relevant and 23 non-relevant, using one base profile with some preference overrides. Eligibility distribution: 17 eligible, 13 ineligible, 7 review. Gold-label independence and inter-annotator agreement were not established.

| Metric | Lexical/rules | Local MiniLM + rules |
| --- | ---: | ---: |
| Eligibility accuracy (3 classes) | 37/37 = 100% | 37/37 = 100% |
| Relevance TP / FP / FN / TN | 12 / 0 / 2 / 23 | 13 / 0 / 1 / 23 |
| Relevance precision | 100% | 100% |
| Relevance recall | 85.7143% | 92.8571% |
| Relevance F1 | 92.3077% | 96.2963% |
| Binary relevance accuracy | 35/37 = 94.5946% | 36/37 = 97.2973% |
| Actual MiniLM use | 0/37 | 37/37 |
| Exact equality to checked-in report, including outcomes | Yes | Yes |

F1 was independently derived as `2TP/(2TP+FP+FN)` from raw outcomes, rather than from rounded report precision/recall. Eligibility and relevance are different labels: three eligible but unrelated jobs are correctly non-relevant. Zero false positives here is **not** a measured production false-positive rate. MiniLM adds one true positive, an absolute **7.1429 percentage-point recall difference**, with unchanged FP count on this small fixture set; no broad superiority or statistical significance is claimed.

Failure details:

- `semantic-developer-title`: lexical rejects it with title match 0, score 60; MiniLM accepts it with title match 0.59, score 82.2.
- `semantic-research-title`: both arms reject it despite gold relevance; lexical score 60 and MiniLM score 62.1, but both have title match 0. The minimum title gate remains blocking.
- Geographic/authorization ambiguity, missing experience and contradictory seniority fixtures pass their expected labels, but these short author-created examples do not establish robustness on independent full job descriptions.

Raw artifacts: [lexical outcomes](raw/matching-lexical.json), [semantic outcomes](raw/matching-semantic.json), [independent counts, confusion matrices and timings](raw/verified-metrics.json). Both arms' eligibility confusion matrices have diagonal counts 17/13/7 and no off-diagonal cases.

## Tests and build actually executed

| Check | Actual result | Scope/limitations |
| --- | --- | --- |
| Backend `tests/` | **338 passed**, 0 failed/errors/skipped, 3 warnings; pytest reported 45.77 seconds | 19 test files; synthetic/in-memory/provider mocks at external boundaries; [JUnit](raw/backend-junit.xml), [log](raw/backend-tests.log) |
| Frontend Node | **35 passed**, 0 failed/skipped, ~2.58 seconds | 7 test files; compiled component/auth/account logic and synthetic dependencies; [log](raw/frontend-tests.log) |
| Frontend TypeScript + Vite build | **PASS**, process exit 0; Vite reports 7.64 seconds for its build phase | Compile/build validation, not runtime/provider quality; [log](raw/frontend-build.log) |
| Frontend Playwright | **14 individual tests reported `ok`; overall suite completion BLOCKED** | 3 files; local synthetic auth/DB/providers and intercepted routes; stalled during shutdown, interrupted with exit 1; no successful terminal summary. [log](raw/frontend-e2e.log) |
| Extension Node | **7 passed**, 0 failed/skipped | Account, credential and event safety; [log](raw/extension-tests.log), [run metadata](raw/extension-tests-run.json) |
| Extension Chromium | **15 passed**, 21.9 seconds reported by Playwright | `extension.spec.cjs` and `forms.spec.cjs`, local forms; no real employer action. [log](raw/extension-browser.log), [run metadata](raw/extension-browser-run.json) |
| PostgreSQL/RLS/RPC/recovery/restore | **BLOCKED** | `docker image inspect postgres:17` failed: Docker engine named pipe absent; also a Docker config access warning. No SQL or database writes attempted |
| Hosted Supabase, real LLMs/HF/Hunter/Gmail/Resend/boards | **NOT MEASURED** | No live credentials loaded by offline Python entry point; no external integration calls approved |
| Linux image, security/audit gates | **NOT RUN** | Historical release/CI reports are not current measurements; not substituted for local checks |

The browser fixture exercises genuine routes and UI behavior against synthetic boundaries. It does not verify OAuth with Google/GitHub, live model tool calling, deliverability, hosted RLS, external DOM stability or employer acceptance. Test counts are not workflow completion/recovery rates. Backend warnings concern Starlette TestClient/httpx deprecation, legacy Chroma embedding-function configuration and a synthetic JWT test's short HMAC key.

**Coverage:** backend line/branch coverage **NOT MEASURED** (`coverage` and `pytest-cov` are not installed in the audited interpreter). Frontend Node native coverage was attempted: its table has **zero source rows** while displaying an aggregate 100%. Compiled VM bundles do not produce an attributable application-source denominator here; that aggregate is rejected. Frontend, browser and extension application line/branch coverage are **NOT MEASURED**. No coverage percentage is inferred from passing tests.

## Limited offline timing and factual diagnostics

Additional paired scoring experiment: 1 initial cold-model/cache batch plus 10 warm batches per arm, each batch running all 37 cases; 407 case evaluations per arm reuse the same 37 labels. It is sequential local CPU scoring, excludes Python imports, and warm calls reuse cached vectors. It is **not end-to-end workflow latency**, nor 407 independent quality examples. Cold measurements have only one sample per arm; warm p95 uses nearest rank over 10 samples and is therefore the maximum.

| 37-case scoring batch | Lexical/rules | MiniLM + rules |
| --- | ---: | ---: |
| Initial cold-model/cache batch | 245.86 ms | 2,785.51 ms |
| Warm batch median | 220.11 ms | 227.80 ms |
| Warm batch p95 | 245.82 ms | 246.03 ms |

This single-host microbenchmark is cache-sensitive, includes profile construction/eligibility logic, and cannot establish production latency, throughput or a meaningful latency difference. Semantic mode ran after lexical mode; imports/libraries were already partly initialized, so even its cold value is not a fresh-process startup metric. See all samples in [verified-metrics.json](raw/verified-metrics.json).

Three constructed validator probes were also executed directly, without generation: unsupported Kubernetes skill **flagged**; invented 90% improvement **flagged**; unsupported company-wide leadership claim **not flagged**. These expose a semantic grounding gap; **2/3 diagnostic detections is not an estimate of factual accuracy or unsupported-claim rate**. Raw source/candidate prose and violations are retained in the same JSON. No live generated resumes were scored.

## Runtime/configuration

- Windows `10.0.26300`, AMD64 Family 25 Model 117 Stepping 2 (AuthenticAMD), **16 logical CPUs**, Python **3.11.9**, Node **v24.17.0**. CPU marketing name, physical core count and RAM were **NOT MEASURED** because CIM hardware queries were denied; no GPU benchmark. ONNX uses CPUExecutionProvider. Thread count/concurrency/load were not controlled beyond sequential scoring; timings are diagnostic.
- Installed versions: Chroma **1.5.9**, ONNX Runtime **1.27.0**, LangGraph **1.2.6**, LangChain **1.3.11**, FastAPI **0.138.0**, pytest **9.1.1**, NumPy **2.4.6**, Pydantic **2.13.4**. [Complete selected package/environment record](raw/environment.json). Existing `.venv` was reused; this is not a clean lockfile-install experiment. Optional SentenceTransformers/coverage packages absent.
- MiniLM is Chroma's cached local ONNX `all-MiniLM-L6-v2`; six required artifact hashes are recorded in [minilm-artifacts.json](raw/minilm-artifacts.json), including the 90,387,606-byte model. Upstream model revision **NOT RECORDED** by the existing cache. No model download occurred. Chat model versions and API usage are **NOT MEASURED** because chat inference was not invoked.
- Matching script overrides `MATCHING_SEMANTIC` per arm and disables developer dotenv loading. Other matching defaults are the source defaults in `config.py` and preferences frozen in the dataset. See [architecture](ARCHITECTURE_AUDIT.md) for weights/thresholds. Supplemental timing clears model/vector caches once per arm, then reuses them.
- Python checks used `offline_entry.py`, which removes inherited provider credentials, disables tracing/telemetry/auto-scan/mail, patches dotenv settings and denies non-loopback Python socket connections. The initial matching/backend runs predate its temporary-Chroma-path addition; imports may initialize the existing local Chroma collection, but no manual vector-store write diagnostic was executed. Subsequent Python checks isolate Chroma under a temporary path. The guard is not an OS firewall and is not inherited by child processes. Browser checks use reviewed local fixtures and sanitized subprocess environments.
- Host UTC run timestamps appear on 11 November in some raw metadata; this audit's user-facing date is 12 November in Asia/Calcutta. pytest's JUnit timestamp includes the local +05:30 offset.

## Commands to reproduce

From repository root, use PowerShell and the already-installed environments. Create the output directory first. No installation, runtime model download, live database test or external write is required.

```powershell
New-Item -ItemType Directory -Force docs/benchmarks/raw | Out-Null
Push-Location backend
.\.venv\Scripts\python.exe ../docs/benchmarks/offline_entry.py scripts/evaluate_matching.py --output ../docs/benchmarks/raw/matching-lexical.json
.\.venv\Scripts\python.exe ../docs/benchmarks/offline_entry.py scripts/evaluate_matching.py --semantic --output ../docs/benchmarks/raw/matching-semantic.json
.\.venv\Scripts\python.exe ../docs/benchmarks/offline_entry.py tests/run_offline.py tests -q --junitxml=../docs/benchmarks/raw/backend-junit.xml
.\.venv\Scripts\python.exe ../docs/benchmarks/offline_entry.py ../docs/benchmarks/measure_offline.py
Pop-Location
Push-Location frontend
node --test --experimental-test-coverage tests/*.test.mjs
npm.cmd run build
Pop-Location
.\backend\.venv\Scripts\python.exe docs/benchmarks/run_check.py frontend-e2e frontend node node_modules/@playwright/test/cli.js test
.\backend\.venv\Scripts\python.exe docs/benchmarks/run_check.py extension-tests extension node --test tests/security.test.cjs
.\backend\.venv\Scripts\python.exe docs/benchmarks/run_check.py extension-browser extension node node_modules/@playwright/test/cli.js test
.\backend\.venv\Scripts\python.exe docs/benchmarks/snapshot.py
docker image inspect postgres:17 --format '{{.Id}}'
```

Actual first-run logs used PowerShell `*>` redirection; frontend/browser extension commands ran through the sanitized subprocess wrapper. `run_check.py` now bounds future checks at 180 seconds; the first frontend browser attempt predated that timeout and was manually interrupted after all test-level passes. It did not produce a wrapper completion JSON; [summary.json](raw/summary.json) explicitly records the interruption. After interruption no audit-started Node/Python fixture processes remained. Do not count shutdown as successful. With Docker available and a locally cached PostgreSQL image, the reviewed next database command is `python backend/scripts/check_database.py --worker-recovery`; it creates an isolated synthetic container, so do not substitute a hosted database.

The ranking command is `python backend/scripts/evaluate_recommendations.py PATH_TO_LABELLED_GROUPS.jsonl --k 5` (and `--k 10` for nDCG@10), but it was **not executed without a qualifying dataset**. Its metric conventions differ from the proposed new protocol; see [plan](EVALUATION_PLAN.md).

## Unmeasured outcomes and next work

Independent real-posting eligibility accuracy, P@5/R@5, nDCG@10/MRR, generated-resume factual consistency/unsupported-claim rate, workflow completion/recovery rates, median/p95 end-to-end latency, token usage, average API cost/completed task and manual-vs-AI preparation time are **NOT MEASURED**. Independent labels, approved provider experiments, trace instrumentation and a comparable human study are needed. Local SQL verification and complete frontend browser shutdown are **BLOCKED** as described above. Proposed engineering work: improve role-paraphrase recall, validate claim-to-fact grounding, and instrument/batch the retrieval/workflow path; detailed paired A/B plans are in [EVALUATION_PLAN.md](EVALUATION_PLAN.md).

## Three resume bullets supported by this snapshot

Use implementation verbs only for work you personally completed; the repository audit does not verify individual authorship or duration of experience. Keep the synthetic qualifier wherever these metrics are reused.

- Built a Python/FastAPI job-matching pipeline combining ONNX MiniLM embeddings with eligibility rules; achieved **92.9% recall and 96.3% F1 with 0 false positives on 37 synthetic regression cases**, versus 85.7% recall for lexical matching.
- Implemented an **11-stage LangGraph** application-preparation workflow with PostgreSQL checkpoints, lease fencing and idempotent persistence; validated checkpoint recovery and duplicate-write safeguards within a **338-test passing offline backend suite**.
- Developed supervised application-preparation and account-isolation safeguards across React and a browser extension; verified **35 frontend tests, 7 extension unit tests and 15 Chromium fixture tests**, including document integrity and submission-evidence handling.

These bullets make no production adoption, time/cost savings, live-provider quality or actual employer-submission claim. The frontend browser suite's interrupted teardown is intentionally excluded from the successful-suite counts.
