# Week 6 staged live acceptance — 2026-10-13

The approved live verification passed using separate RAG and Langfuse phases.
The user requested another solution to low memory; no user applications were
closed. Evidence is protected in `test_output/week6-live-20261013-01/`.

## Real corpus, model and cache verification

The original PostgreSQL/OpenSearch/Ollama containers were started in place.
Airflow, Dashboards and the original API stayed stopped. A single-worker API on
loopback port 8001 used the retained image, read-only current source, checksum-
verified optional Linux wheels, the preserved key and read-only database
transactions. Its Redis was separate, volatile, password-protected and bounded.

Production revision probes passed three stable real samples in 347.57, 109.53
and 134.28 ms; authenticated readiness returned 200/healthy. Before/after full
content fingerprints matched the verified activation snapshot: 58 paper rows,
58 paper-index documents, 1,221 v1 chunks, 2,775 v2 chunks, aliases and both model
digests. All 13 installed model-volume files also match exactly.

Real evidence was prepared for the existing KBEVO regression question. The same
OpenSearch container was stopped during generation to release memory. Installed
`llama3.2:1b` produced a validated 66-word answer in 15.01 seconds with unchanged
selector/prompt/generation settings and candidate default 1. The test model was
unloaded, the same OpenSearch container restarted, and fresh identity plus every
ordered citation/source matched before the response was signed and cached.

The real HTTP API verified:

- Identical quotations, citations, locators and sources across cached ask/stream;
  deltas joined to the final answer. Client latencies were 360/265 ms. Correlated
  events prove no retrieval/generation on those hits. The staged generation time
  is not a directly comparable full-API cold latency benchmark.
- A normal cache miss/store and matching stream hit on a no-evidence request.
- Genuine HTTP disconnect after sources, correlated interruption and no cached
  entry for that interrupted request.
- Real Redis TTL expiry, with expiry shortened only for a test-owned entry, and
  distinct keys for a derived changed revision. Live corpus/index/model data was
  not mutated for invalidation; unit tests cover those mutation boundaries.
- Redis unavailable fallback, authentication before cache access, equal quota
  consumption on hits, normal window reset, 429 and readiness under exhaustion.

The initial response comparison failure was UTF-8 decoding in the Windows
harness, not a response mismatch. Explicit UTF-8 resolved exact equality; the
initial failure is retained. A diagnostic request later encountered natural TTL
expiry and used normal generation, which also validated successfully.

## Full local Langfuse backend and console

RAG services were stopped before the separate Langfuse v4 lab ran. Its pinned
official web/worker, ClickHouse 25.12.11.4, MinIO and existing PostgreSQL 16/Redis
7 images use only fresh lab volumes and private test credentials. The UI binds
to `127.0.0.1:3001`; product/Next telemetry is disabled, no model/provider
connection is configured, and the application API key is never passed to it.

Automatic approval review initially rejected storage startup with about 624 MiB
free because of host/VM disruption risk. No services started on that attempt.
Idle WSL later reclaimed memory automatically, leaving about 4.5 GiB; fresh
capacity guards allowed the lab. Later, only lab services were stopped and
Docker's documented `sync; echo 1 > /proc/sys/vm/drop_caches` reclaimed read cache.
No files were deleted, WSL configuration changed or user applications stopped.
Capacity was remeasured before retries; the rejection was not bypassed.

The web's 384/640 MiB heap failures are preserved. The accepted configuration
uses a 1.25 GiB heap inside a 1.5 GiB container; worker cap 768 MiB, ClickHouse
1 GiB (512 MiB server budget), MinIO 256 MiB, PostgreSQL 128 MiB and Redis 96 MiB.
The measured complete lab footprint was approximately 2.4–2.5 GiB. A malformed
lab Redis shell command was corrected only in that owned container.

Health and project authentication passed. The actual OTLP exporter sent only
allowlisted real acceptance metadata, explicitly marked historical replay. The
backend stored **34 observations across 15 real request IDs**, including actual
generation usage. Private questions/evidence/answers/keys were absent; costs are
null rather than invented billed estimates. The worker was then stopped to free
memory for an isolated headless Chrome test account/profile. The console rendered
all 34 observations, empty Input cells and trace names with zero uncaught errors.
External HTTPS requests were blocked; the screenshot was visually inspected.

This verifies real storage and stored-data rendering. It does not establish
sustained load, production sizing, concurrent loaded-model RAG/Langfuse operation,
or simultaneous RAG-to-console collection. Historical replay is explicit.

## Preservation and final state

All 146 source/evaluation/existing-change baseline files matched before the
authorized documentation update. All 304 key/evaluation/frozen-bundle checksums
matched. Original container IDs/images/mounts/resource settings are preserved and
initial stopped states restored, including `erp-redis`. Temporary API/Redis were
removed. New private Langfuse containers/volumes are retained stopped; no service
remains running. New images are additive; the frozen recovery bundle is unchanged.

No application-source fix was needed, so the prior 494 passing tests, mypy and
changed-file Ruff still cover unchanged source; they were not repeated solely for
documentation. Compose/diff checks pass. The preexisting full-repository Ruff
import-order issue remains. No deployment, selector tuning, ingestion, reparsing,
reindexing, model change, commit, push or merge occurred.

The original API has not been rebuilt or enabled with these opt-in features.
Continuous combined-stack activation still needs a measured memory plan. Staged
Week 6 acceptance is complete; sustained concurrency, alerts, off-machine
recovery and production operation are not claimed. Answer-quality defects remain.

Key evidence: `live-probe.json`, `data-before.json`, `data-after.json`,
`generation.json`, `warm.json`, `live-acceptance.json`, `cache-ttl-invalidation.json`,
`live-monitoring.html/json`, `langfuse-acceptance.json`, `langfuse-observations.json`,
`langfuse-browser.json`, `langfuse-console.png` and preservation reports. The
directory contains private evidence/credentials; do not publish or commit it.

Sources: [Langfuse sizing](https://langfuse.com/self-hosting/deployment/infrastructure/containers),
[ClickHouse](https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse),
[initialization](https://langfuse.com/self-hosting/administration/headless-initialization),
[public API](https://langfuse.com/docs/api-and-data-platform/features/public-api),
[WSL memory reclaim](https://learn.microsoft.com/windows/wsl/wsl-config),
[Docker page-cache reclaim](https://www.docker.com/blog/docker-desktop-wsl--2-best-practices/).
