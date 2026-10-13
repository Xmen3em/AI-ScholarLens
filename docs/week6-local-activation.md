# Week 6 local activation — 2026-10-13

The user approved local activation of a single API worker, Redis caching and
file-based monitoring after the staged [live acceptance](week6-live-acceptance.md).
The normal API is healthy at `http://127.0.0.1:8000`; the existing Gradio client
works at `http://127.0.0.1:7861`. This record supersedes the earlier stopped-state
and pending API-activation statements. No external deployment or selector tuning.

## Runtime and resource evidence

Only PostgreSQL, OpenSearch, Ollama, the new API and the new Redis cache run.
Airflow, OpenSearch Dashboards, all six Langfuse lab services and unrelated
`erp-redis` remain stopped. Langfuse is retained for separate review sessions;
continuous concurrent RAG-to-Langfuse collection is still unverified.

The additive image `scholarlens-api:week6-local-20261013` is
`sha256:c91c20ebe2ed71d7f433caff393d7eb0c18b1cbb046f2c7a094eb4d2f0b20c89`.
It adds the unchanged, already tested source and verified locked optional Linux
dependencies to the exact retained API image. No base package was upgraded.
API: one worker, 384 MiB memory cap, one CPU, read-only image, bounded temporary
storage/logs. Redis: `scholarlens-week6-cache`, authenticated, loopback 6380,
128 MiB cap, 64 MiB LRU cache, no persistence and no original data mounts.
Answers have a one-hour TTL; stopping Redis clears its volatile cache.

The initial cold real cache miss hit the emergency memory floor (180 MiB
available), and the trial API/inference stopped before activation. The failure
is retained. Disposable WSL read caches were reclaimed using the documented
Docker procedure; no user applications, files or system settings changed.
The retry started with over 3 GiB available and completed with **833 MiB minimum**
available host memory and 11,897 MiB minimum commit headroom. All RAG services
remained running throughout that successful real miss. A later completed test
model was unloaded from RAM; installed model files and generation defaults stayed
unchanged. Idle reclaim subsequently restored over 4 GiB of available memory.

This is measured local acceptance, not sustained-load sizing. Host capacity
fluctuates with user applications and filesystem caches. Keep the heavy services
above stopped during normal RAG use. The acceptance harness has an emergency
384 MiB floor and requires at least 600 MiB throughout a passing inference;
it is not a permanent runtime watchdog or automatic alert service. Do not assume
the six Langfuse services fit concurrently merely because caching is now active.

## Verified behavior

- Trial: actual nonempty cache miss 14,516 ms; cached ask/stream 312/250 ms.
- Activated API: fresh miss with the normal Gradio payload 1,469 ms; hits 265/250 ms.
- Exact answer, server-owned citations, sources and concatenated SSE deltas match
  between cached endpoints. Hits avoid retrieval and generation.
- Authentication precedes caching. Hits consume the same six-generation budget;
  the seventh request returns 429 with Retry-After, while readiness remains healthy.
- The existing Gradio client renders quotations, evidence and PDF links. Native
  input/click verification in a dedicated headless browser passed in 1.69 seconds
  with zero uncaught errors. The initial harness failure was resolved by using a
  viewport containing the Ask button; no Gradio source change was needed.
- Actual Redis TTLs were positive and bounded to one hour. Stopping only the new
  Redis caused normal no-evidence RAG fallback in 485 ms; readiness stayed healthy.
  Redis was restarted, leaving its volatile cache empty for normal future misses.
- Monitoring reports contain metadata only, real latency/cache/quota outcomes and
  Ollama tokens/durations. No questions, evidence, answers or secrets are logged.
  No billed provider cost is fabricated. Reports are offline snapshots.

Earlier TTL expiry, revision invalidation, interrupted-stream/no-store and
Langfuse transport/storage/UI acceptance remain recorded in the staged report.
Answer relevance/coverage defects remain unresolved; cache correctness does not
establish answer quality.

## Preservation and local controls

The original API container is retained stopped as
`rag-api-before-week6-20261013`, including its ID, writable layer, original key,
configuration and exact image. Its image remains
`sha256:808626dff29c7bf0e222655fa9a0d6984f255b036d2ae5dddfe0bb1018514e11`,
also tagged additively `scholarlens-api:week6-retained-base-20261013`.
All original dependency container IDs/images/configurations/resource settings
and mounts are intact. The active API key matches the original and Gradio key.
The normal `.env`, source, Compose, lockfile, selector defaults/guards and earlier
uncommitted changes were preserved. Active source hashes match the workspace.

All 304 protected key/evaluation/frozen-recovery-bundle checksums match. Full
database and index/vector fingerprints and alias targets match: 58 papers,
58 paper documents, 1,221 v1 chunks and 2,775 v2 chunks. Installed model digests
and complete model-volume file fingerprints match. The frozen 8.35 GiB bundle
was not refreshed; it still captures the earlier runtime.

Private runtime configuration, Redis password, writable event/quota files and
acceptance evidence live under restricted-ACL
`test_output/week6-local-activation-20261013-01/`. Do not publish or commit it.
The active API binds only that directory's `active/` subdirectory at `/local`.
Monitoring files rotate at 1 MiB plus three backups per worker/PID; old PID files
remain retained. The global SQLite budget file persists across API restarts.

These are explicitly launched local containers; ordinary base `docker compose up`
does not describe this activated runtime and may recreate it with features off.
Do not use it as the activation control. To stop/start the same containers:

```powershell
docker stop rag-api scholarlens-week6-cache rag-ollama rag-opensearch rag-postgres
# Restart only with measured host memory headroom; retain the same containers.
docker start rag-postgres rag-opensearch rag-ollama scholarlens-week6-cache
# Wait for healthy dependency readiness, then:
docker start rag-api
```

To roll back without deleting either API container or any volume:

```powershell
docker stop rag-api
docker rename rag-api rag-api-week6-disabled-20261013
docker rename rag-api-before-week6-20261013 rag-api
docker start rag-api
docker stop scholarlens-week6-cache
```

For a fresh monitoring snapshot, use a new output filename:

```powershell
.venv-win/Scripts/python.exe -m src.monitoring test_output/week6-local-activation-20261013-01/active/events test_output/week6-local-activation-20261013-01/monitoring-next.html
```

Evidence includes `trial-acceptance-initial-resource-stop.json`,
`trial-acceptance.json`, `active-acceptance.json`, `gradio-acceptance.json`,
`gradio.png`, `fallback-acceptance.json`, `monitoring-final.html/json`,
`data-before.json`, `model-files-after.json`, `image-provenance.json` and
`preservation.json`. Source was unchanged, so the prior 494 passing tests,
type checks and changed-file lint still apply; runtime acceptance verifies the
new image. No commit, push, merge, data/model change or external deployment.
