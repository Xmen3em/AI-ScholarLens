# Week 6 local verification

- [x] Review and checkpoint Week 6 source, configuration, tests and local evidence; prepare [Week 7 continuation context](../docs/week7-continuation.md) for the next session.

- [x] Prepare the recommended encrypted USB transfer, pinned receiving verifier and separate-machine instructions; verify no-copy mode, internal-drive rejection, restrictive ACL and checksum boundaries on local fixtures.

Transfer preparation: [procedure](../docs/week6-off-machine-transfer.md).
User asked for a recommendation; encrypted NTFS USB with 20 GiB free and a
separate x86-64 Docker computer with 16 GiB RAM/50 GiB free are recommended.
Device/path and second-machine access are still absent; copy/rehearsal remain open.

- [x] Observe eight sequential normal Gradio requests, cold/miss/hit latency, quotas, real token usage and memory; retain evidence and verify preservation.
- [x] Reverify all 233 frozen recovery-bundle manifest files before off-machine transfer; bundle unchanged.

Observation: [report](../docs/week6-observation.md). Cache hits 263–579 ms,
misses 7.2–16.5 s, zero API failures; minimum free memory 539 MiB during cold
inference. This controlled sample does not establish sustained capacity or quality.
Off-machine destination and separate-machine access remain missing; no copy or
new recovery rehearsal has occurred.

Latest: [local activation](../docs/week6-local-activation.md) passed on 2026-10-13.
The healthy API runs one worker with caching and file monitoring; the normal
Gradio browser check passed. Original API/key and all protected data are retained.
Langfuse, Airflow and Dashboards remain stopped; no external deployment or tuning.
Earlier stopped-state statements below describe the prior staged acceptance.

Continuation on 2026-10-13: opt-in tracing, caching and offline monitoring are
implemented in source. The six original application containers were already
stopped and remain stopped; the activated image/key and frozen recovery bundle
are preserved. See [monitoring plan](../docs/week6-monitoring-plan.md) and the
new operations section. No deployment, API rebuild or selector tuning occurred.

- [x] Audit current Langfuse SDK/self-hosting, source parity, installed images and actual host/VM capacity.
- [x] Verify metadata-only isolated Langfuse OTLP export, bounded failure, correlation and SSE lifecycle before cache work.
- [x] Implement disabled-by-default signed Redis exact-match caching after authentication and quotas.
- [x] Verify policy/settings/revision invalidation, TTL, unavailable Redis, validated nonempty citations, endpoint parity and interrupted delivery.
- [x] Add bounded per-worker event files and offline percentile/failure/quota/token/cache monitoring views.
- [x] Run 494 passing tests, all-source mypy, changed-file Ruff, Compose/diff checks and preservation audit; remove owned scratch resources.
- [x] Validate a full local Langfuse backend/project/storage and stored-data UI in a separate bounded phase after RAG services are stopped.
- [x] Verify live corpus/index/model revision probes and enabled cache behavior on the separately prepared local runtime.
- [x] Activate one-worker API, Redis and file monitoring after simultaneous real-miss memory checks; verify Gradio, auth/quotas, fallback and preservation.
- [ ] Verify simultaneous loaded-model RAG/Langfuse operation and sustained-load sizing if separately requested; the memory-safe local mode keeps Langfuse stopped.

The approved staged continuation passed: [live acceptance](../docs/week6-live-acceptance.md).
Real quoted-answer cache hits took 360/265 ms, endpoint citations matched, and
real interruption/TTL/fallback/quota checks passed. Full Langfuse stored 34
metadata observations across 15 real request IDs; its isolated console rendered
them without uncaught errors. Exported events were explicitly historical replay.
Original services are restored stopped, temporary API/Redis are removed, and the
new private Langfuse lab is retained stopped. All data/model/key/bundle checks
passed. Evidence: `test_output/week6-live-20261013-01/`; no source/selector change,
deployment, commit or push. This is staged acceptance, not combined-stack sizing.

Earlier source-only evidence: `test_output/week6-monitoring-20261013-01/`. Redis acceptance used only
synthetic data and an existing installed image. Original source guard files,
model-volume fingerprints and 304 key/evaluation/bundle checksums match. No fresh
live API/readiness/corpus-count verification is claimed with the stack stopped.

Local activation approved on 2026-10-12: rebuild only the API, configure a key,
and verify access, limits, logs, readiness and the normal Gradio client. See
`test_output/week6-activation/` for acceptance/preservation evidence.

- [x] Activate the API with a saved local key and localhost binding.
- [x] Verify 401/429 behavior, healthy readiness under exhausted budgets and window reset.
- [x] Verify correlated request/retrieval/generation logs and active source parity.
- [x] Verify the normal Gradio UI renders a completed answer and paper links.
- [x] Confirm corpus/index/model/evaluation preservation and unchanged dependency containers.
- [x] Verify isolated recovery of OpenSearch, PDF/checkpoint, Ollama and Docling cache volumes using matching installed images.
- [x] Compare complete file fingerprints, search contents/vectors/mappings/aliases and model digests; remove only owned scratch resources.
- [x] Prepare a protected, checksummed recovery bundle including current source/configuration, a fresh database dump and six exact installed images.
- [x] Verify image archive integrity/load and a fresh isolated replacement API/Gradio stack from the bundle; verify the packaged rehearsal script.
- [x] Diagnose Airflow's existing webserver failure without changing live processes, DAG flags or data.
- [ ] Copy the complete bundle to protected off-machine storage and verify receiving checksums (destination not yet available).
- [ ] Rehearse on a separate replacement machine; verify full machine-loss recovery before any cutover.

Continuation evidence: `test_output/replacement-recovery-20261012-01/`. The local
bundle is about 8.35 GiB and includes private credentials under a restricted ACL.
Docker image load and isolated replacement/API/Gradio checks passed; scratch
resources were removed. All 8,828 previous artifacts and source/runtime/data/key
fingerprints remained intact. Existing Airflow failure is a stale monitor PID
collision plus missing `pkill`; diagnosis is verified, no live repair applied.
All attached drives are internal; off-machine copy remains pending a destination.

Volume recovery passed on 2026-10-12; evidence is in
`test_output/volume-recovery-20261012-01/`. API/Gradio health, all existing
artifacts/workspace files, the key, corpus and models were preserved. OpenSearch
and Ollama had brief local maintenance stops; Airflow retained its preexisting
unhealthy process state after a cache-archive pause. No deployment or tuning.

Activation checks: 476 tests passed including Docker integration tests, Ruff and
mypy passed, 72 source files match the active image, and the Gradio client is
available at `http://127.0.0.1:7861`. No external deployment or selector tuning.

- [x] Audit four areas and compare the course reference before implementation.
- [x] Request IDs, total latency and safe selector/stream JSON events; verify success, HTTP failure and SSE failure.
- [x] API key and shared budgets; verify rejection before work, window reset, concurrent workers and store failure.
- [x] OpenSearch readiness and local configuration; verify missing aliases/red/unreachable dependencies.
- [x] Backup/restore procedure; verify full-content restore into an isolated empty database.
- [x] Full checks, runtime evidence, preservation audit and final documentation.

Deployment remains outside scope. Answer-quality defects and fresh-data requirements
remain open in `plan.md` and the selector report; they are not Week 6 completion gates.

Verified: 443 passed, 32 existing integration skips; Ruff/mypy/Compose/diff checks
passed. Real database restore matched all 58 paper rows/fields and schema revision.
The temporary two-worker API passed authentication, readiness, SSE and shared
quota checks. Original runtime and corpus were left intact.

Before any separately approved deployment: rehearse machine-loss recovery,
provision off-machine backups, choose multi-replica limits if needed, and replace
development-only infrastructure configuration. Cold-volume recovery is now
verified locally; the remaining items are not verified deployment controls.
