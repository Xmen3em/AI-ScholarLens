# Isolated hosted evaluation checkpoint

Current2026-10-14: [bounded structural diagnostic](hf-structure-diagnostic.md).
The isolated observer/one-attempt command and48 tests are implemented;835 tests
pass,zero skips,mypy96. One syntheticHTTP400 reports empty failed_generation;
root cause unresolved,no qualification/paper collection. **8/13 used,5 remain**.
All existing source/defaults/guards/runtime/data/models and prior evaluations
are retained. Next local minimal reproduction and frozen compatibility/limit
experiment; remaining5 cannot cover qualification plus paired paper case work.

Current: [explicit HF route comparison](hf-route-comparison.md). The isolated
command/profile and17 new tests are complete; full suite787 passes,zero skips.
Both scheduled routes fail synthetic relevance400/json_validate_failed; no
qualification or paper collection. **7/13 approved attempts used,6 remain**.
Existing application source/defaults/guards/runtime/data/models and all prior
evaluation files remain intact. Next prepare bounded structural diagnostics.
The earlier checkpoints below retain their historical balances and counts.

Latest: [frozen fixture revision and provider-error diagnosis](hf-qualification-v2.md).
Versioned inputs,content-free diagnostics,review bindings and shared allowance
are implemented. Trial05 and a single diagnostic report relevanceHTTP400 with
`json_validate_failed`; no paper cases sent/collected.770 tests pass,zero skips.
Total5 approved attempts used,8 remain. Preserve fixed allowance and failed trials.
The original commands/status notes below describe earlier checkpoints.

Latest live result: [retry04 report](hf-pilot04.md). RAM admission passed; two
synthetic HF/Groq calls ran. Scope passed,relevance schema passed but expected
decision failed. Qualification stopped before paper cases. Cost estimate
$0.00010515;zero unknown usage. **741 passing tests,zero skips** after three new
semantic-mismatch regressions. Source/profile/guards/runtime remain unchanged.
Only11 of the approved13 outbound attempts remain for any subsequent trial.
The earlier no-start evidence below describes the preceding checkpoint.

HF-5 is implemented. The separate hosted v1 protocol was frozen on 2026-10-13
before any hosted inference. Its manifest SHA256 is
`3b42fccb34bc542e91ccdd3df0d8acb85c0bc86f7237eebdb214e6e9dbfc37a1`.
Read the [frozen protocol](../evaluation/week7_hf/PROTOCOL.md) and
[profile](../evaluation/week7_hf/profile.json). The original local v2 protocol,
eight development/24 holdout cases, source labels and 3 GiB gate are unchanged.

## Collection and scoring

`src.commands.evaluate_hf_agent` plans offline by default. Explicit execution
checks original key/settings, mode-specific host RAM, the complete source/corpus
snapshot, exact retained model digests and public live provider metadata before
paid work. It uses a temporary uncached loopback app with no production lifespan,
database connection, local generation model load or tracing export. The existing
embedding model is used only for hybrid retrieval. It never replaces the active
API or charges its generation quota.

The registered candidates are GPT-OSS-120B through Groq and through Fireworks,
each explicitly pinned and separately qualified. Five synthetic qualification
calls exercise the canonical scope, relevance, rewrite and 1/10-ID selectors.
The 30-ID schema must reject locally with zero outbound work; its constraints
are preserved. No provider retry, failover or schema downgrade occurs. Failure
or unknown usage stops before case collection.

Development permits pilot subsets; complete development is 64 jobs. Holdout is
the complete original counterbalanced 192-job matrix and requires a locked,
semantically reviewed, accepted development run for that same pair. Generation
ceilings are unchanged: two calls per baseline job, six per agent job. Total
outbound ceilings including qualification are 261/773; the one-case BM25/JSON
pilot is 13. Test-owned quotas retain six generation requests per minute, with
61-second windows after qualification and every six scheduled jobs.

Host admission is 1024 MiB for BM25 and 1536 MiB for hybrid; keep 600 MiB free
and cancel below 384 MiB. These are separate engineering starting budgets,
not measured capacity or a relaxation of local v2. Completed/failed generation
calls and outbound attempts are recorded separately. Native structured content
is checked against original contracts without altering application output.
Persisted ledgers contain bounded usage/timing/error metadata, never prompts,
controller content, rewrites, provider error bodies, credentials or reasoning.

`src.commands.score_hf_agent` reuses the original semantic/source/work gates.
Reviews additionally bind the hosted manifest, model/provider and all records.
It rejects partial matrices, unknown usage, schema/resource/work violations,
stale bindings, incomplete preservation and outbound-count discrepancies.
Complete synthetic acceptance and regression/rejection paths are tested. Cost
reports include qualification and case known-usage estimates separately; unknown
outbound attempts remain explicit. Estimates use dated frozen rates and are not
an invoice. Empirical p95 targets remain 10s baseline/20s agent per comparison
cell. No hosted quality, latency, sustained-capacity or "best model" claim exists.

## Commands

Use a fresh ignored output directory for each run. This holdout plan needs no
token, private settings, network, inference or model selection:

```powershell
.venv-win/Scripts/python.exe -m src.commands.evaluate_hf_agent --snapshot tests/test_output/week7-source-review-20261013-01 --split holdout --output tests/test_output/hf-holdout-plan-new
```

The bounded live pilot sends the selected public-paper question and retrieved
passages through HF to Groq. The user explicitly approved this exact one-case
pilot with a13-attempt ceiling. The command below describes the original full
allowance; after retry04 consumed two calls,do not execute it again without an
explicitly enforced remaining11-attempt cap and separately frozen qualification
revision. The failed v1 qualifier is not retried in place:

```powershell
.venv-win/Scripts/python.exe -m src.commands.evaluate_hf_agent --snapshot tests/test_output/week7-source-review-20261013-01 --split development --case-id week7-development-narrative-rubrics-literal --mode bm25 --transport json --output tests/test_output/hf-development-pilot-new --execute
```

After actual collection, export a review template, complete its semantic judgments
from source facts and save `reviews.json` inside that run. Subset pilots can be
scored but cannot establish development or holdout acceptance:

```powershell
.venv-win/Scripts/python.exe -m src.commands.score_hf_agent template --run tests/test_output/hf-development-pilot-new --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/hf-pilot-review-template-new.json
.venv-win/Scripts/python.exe -m src.commands.score_hf_agent score --run tests/test_output/hf-development-pilot-new --snapshot tests/test_output/week7-source-review-20261013-01 --reviews tests/test_output/hf-development-pilot-new/reviews.json --output tests/test_output/hf-pilot-score-new.json
```

A full accepted development run can use `lock` instead of `score`. It writes a
fresh `selection-report.json` into the run and a separate selection lock. Holdout
execution uses `--selection <lock>` and revalidates all evidence, reviews and
current source hashes. Do not change source between development selection and
holdout; rejected candidate evidence is retained rather than retried in place.

## Verified evidence and live status

**738 tests passed, zero skips**, including disposable PostgreSQL. **40 new
hosted protocol/collector/scorer tests** use synthetic HF/search responses,
ASGI and an actual test-owned TCP/SSE server. Mypy checks 88 source files;
changed-file Ruff and diff checks pass. A mutation removing the unknown-usage
acceptance gate failed its test; exact source bytes were restored before the
passing full suite. The original freeze validator reverified 64 frozen/prior
files. All 162 pre-turn protected source/evaluation/environment/dependency files
match. No prior source or selector functions were edited in this slice.

Evidence: `tests/test_output/hf-protocol-20261013-01/` (fingerprints/mutation),
`hf-protocol-focused-20261013-02/`, `hf-protocol-full-20261013-01/`, and
`hf-holdout-plan-20261013-01/` (192-job offline plan). The small development plan
is in `hf-development-pilot-20261013-01/`.

Automatic approval review initially rejected execution for lacking specific
data-transfer approval. The user subsequently answered **"Approve this bounded
HF pilot"** for this question/passages, HF/Groq destination and13-attempt ceiling.
The approved command passed that approval review but stopped at RAM admission:
`hf-development-pilot-20261013-02/` recorded932.93MiB free versus1024MiB required.
One previously documented clean WSL read-page-cache reclaim changed no files,
apps, services, models or persistent settings. Retry03 still recorded738.29MiB;
subsequent30-second samples ranged840.59–907.67MiB. The frozen host criterion
was preserved; guest available memory was not substituted.

**Zero HF requests or live qualification**, with no temporary evaluation app,
live answers, usage measurements, reviews or scores. Token/key presence was
checked without exposing values; authorization and credits remain untested.
Approval/admission/memory evidence is retained in the fresh pilot02/03 metadata
and `hf-protocol-20261013-01/approved-pilot.json`, `approved-pilot-memory.json`.
No application source changed this turn; the738-test result above remains the
last full implementation check, not a new run.

The original 15 container IDs/images/states remain retained, with five running;
the full suite's disposable database was removed. The private environment,
original API/key, corpus/indexes/models and frozen recovery bundle remain intact.
Source is uncommitted on master at a597f23; no deployment, push, merge, activation,
data/model replacement or selector tuning. Missing backup hardware does not
block source work. Next: free additional host RAM by closing unused apps/tabs,
retry this same approved pilot with a fresh output directory and unchanged
limits/source, then complete reviewed development,
then a locked same-pair holdout. Research browsing/detail/search/source inspection
and server preparation follow the existing roadmap.
