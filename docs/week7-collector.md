# Week 7 isolated collector and no-start pilot

2026-10-13, Africa/Cairo. The frozen [evaluation protocol](../evaluation/week7_agent/PROTOCOL.md)
and v2 labels remain unchanged. This step implements collection tooling; no agent
quality acceptance or activation occurred.

## Runner

`src.commands.evaluate_agent` defaults to an offline plan. It validates pinned
manifest `58b099eead49d8fd22d96be7a7ceba3142de9524ce6f80846e2e8ddee884b0db`,
source snapshot, frozen labels and all 60 prior evaluation fingerprints. Full
holdout plans contain 192 unique counterbalanced jobs. Holdout subsets/reordering
and duplicate modes/transports are refused; a development subset permits a small
pilot. Every output must be a new directory under local ignored test output.

`--execute` first makes read-only corpus/model probes and samples actual RAM. It
requires unchanged candidate default one, original API key and six-generation
quota, loopback resource origins, exact retained local model digests, identical
corpus/index alias identity and at least 3,072 MiB available host memory. Failed
admission writes metadata with `inference_started=false` and creates no server or
model clients. No secret values enter saved configuration or stdout.

After admission only, a test-owned one-worker HTTP app binds an ephemeral loopback
port, with no production lifespan/database/migrations, Redis or tracing backend.
Both RAG paths are uncached, preserve selector options and use the same quotas in
a separate SQLite file. Existing API/key/quota files, runtime and rollback are
untouched. Counters instrument generation attempts (including failures), retrievals
and query embeddings. All model/search behavior is inherited without tuning.

The client has an overall 150-second cap and no retries. It validates status-aware
SSE ordering, terminal source identity, exact deltas, citations against both indexed
and stored source text, original query/model identity and reported versus measured
budgets. Response-bound raw records remain ignored and semantic judgments remain
separate; valid attribution is not relevance/coverage acceptance. A 429 is retained
as a failed attempt; bounded Retry-After delays the next distinct job. Quota windows
are paced without increasing limits.

RAM is sampled every 100 ms. Below 384 MiB, or if monitoring fails, the client work
is cancelled and the run stops; a request dipping below the 600 MiB acceptance
margin also stops before further requests. Client timeout stops further work while
in-flight remote execution is uncertain. The temporary server/client/search resources
close on exit. Python thread abandonment and HTTP cancellation do not guarantee
remote model termination; existing service limits/worker occupancy still apply.
No container stop/restart, model download/unload, app closing or memory-setting
change is performed by this runner. The present pilot did not pass admission
and loaded no model.

## Evidence and verification

The offline full-holdout plan passed:
`tests/test_output/week7-holdout-plan-20261013-01/metadata.json`, 192 jobs.
Guarded development pilot planned one literal case, BM25/JSON, baseline then agent:
`tests/test_output/week7-development-pilot-20261013-01/metadata.json`.

Actual result: **not started, insufficient memory**. Free RAM at admission was
**1,638.32 MiB**, below **3,072 MiB**. Zero inference requests, no temporary
evaluation server, no response records and no semantic results. All current
corpus digests/aliases and installed model digests matched; no model was loaded
before or after. Do not describe this as a failed answer-quality trial or a passed
live pilot. No protocol threshold was lowered to proceed.

**589 tests passed, zero skips**, including disposable PostgreSQL tests; mypy
checks 79 source files. Final collector checks: **19 passed**, including an actual
loopback server with mocked model/search boundaries: one baseline and three agent
generation calls, validated equal evidence, no caching and orderly cleanup. A
memory-admission bypass mutation was detected and exact source restored. Changed-
file Ruff/diff checks passed. Two existing dependency deprecations remain; unused
WebSocket support is disabled in the HTTP-only temporary server.

## Commands and next step

Offline planning makes no network or inference calls:

```powershell
.venv-win/Scripts/python.exe -m src.commands.evaluate_agent --snapshot tests/test_output/week7-source-review-20261013-01 --split holdout --output tests/test_output/week7-holdout-plan-NEXT
```

For a later guarded pilot, use a new output directory:

```powershell
.venv-win/Scripts/python.exe -m src.commands.evaluate_agent --snapshot tests/test_output/week7-source-review-20261013-01 --split development --case-id week7-development-narrative-rubrics-literal --mode bm25 --transport json --output tests/test_output/week7-development-pilot-NEXT --execute
```

Next retry the development pilot only when actual headroom meets the unchanged
protocol, then review its outputs before the complete holdout matrix. Do not
enable the feature, replace models or use holdout outputs for tuning. Sustained
load, deployment and server sizing remain future gates. Missing backup hardware
still does not block source implementation.
