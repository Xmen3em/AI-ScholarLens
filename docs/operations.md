# Local operational controls

Week 6 audit, course comparison and quality backlog: [plan](../tasks/plan.md).
These controls are for local verification. No external deployment is approved.

## Requests and diagnostics

Every response carries a server-generated `X-Request-ID`; client-provided IDs
are ignored. `src.operations` emits JSON with `event`, `entry_point=api` and
`request_id`. `http_request_completed` records method, route template, status,
total response duration in milliseconds and outcome. Duration includes the SSE
body, not just response headers. Unknown/rejected routes use `unmatched` so raw
paths/query strings are not logged. Uvicorn access logging is disabled by the
Docker command and `python -m src.main`; use `--no-access-log` with custom launchers.

Filter the same ID across `rag_retrieval`, `rag_generation`,
`rag_selection_validation_failed`, `rag_answer_validation_failed`,
`rag_selector_retry` and `rag_stream_error`. Token counts and generation timings
remain available. SSE failures have HTTP 200 after headers start, so inspect
`outcome=stream_error` and the terminal error event rather than status alone.
Never retain deltas after an SSE error. Diagnostics omit queries, evidence,
answers, keys and provider exception text. Latency percentiles and failure rates
can be calculated from completion events; no dashboard, external telemetry,
distributed traces or automatic alerts have been provisioned.

When a selector fails, inspect the bounded reason and request ID. A malformed
selection retries once; a rejected retry fails closed. Do not repair, sort or
deduplicate model output. When dependency readiness fails, inspect
`readiness_failed.dependency` and check that service's local health/model/alias
state. Do not ingest or reindex merely to make a probe green.

## Access and rate limits

Set `API_KEY` to a random secret of at least 32 characters; send it as `X-API-Key`.
The key is optional only when `ENVIRONMENT` is exactly `development` or `test`.
All other environments refuse startup without it. With a key configured, every
route including docs and readiness requires it except `/api/v1/ping`.
The Gradio client forwards its server-side `API_KEY` environment variable.

Defaults are **60 requests per minute**, plus **6 generation requests per minute**
shared by `/api/v1/ask` and `/api/v1/stream`. These are global instance budgets,
not per-user quotas. Unauthorized requests spend neither budget; a generation
rejection also spends neither. A rejection returns 429 and `Retry-After` seconds.
Liveness/readiness spend no budget; readiness still requires the key. Missing or
locked budget storage fails closed with 503 for ordinary traffic.

SQLite serializes reservations across all workers using `API_RATE_LIMIT_PATH`.
Compose uses `/tmp/scholarlens-rate-limits.sqlite3`, shared by its four workers;
host runs default to `./data/rate_limits.sqlite3`. Counters reset on container
replacement, and a fixed window permits bursts across its boundary. Multiple
containers/replicas require an external shared limiter and separate validation.
Neither forwarded IP headers nor a spoofable request ID determine identity.

The Compose file publishes all service ports on `127.0.0.1`. It still uses
development PostgreSQL credentials, disabled OpenSearch security, and local HTTP;
it is not a production deployment configuration. Existing running containers
retain their previous bindings until recreated. This pass verified a temporary
loopback-only API and left the existing stack untouched. Non-API port binding
changes were validated as configuration, not applied to running services.

## Liveness and readiness

`/api/v1/ping` is process liveness. `/api/v1/health` checks PostgreSQL `SELECT 1`,
Ollama's required/optional models, OpenSearch cluster status and both read aliases
(`arxiv-papers`, `paper-chunks`). Missing required dependencies/aliases, red cluster
health or probe timeouts produce 503. Yellow single-node OpenSearch is usable.
Optional missing Ollama models retain the existing 200/degraded behavior.
Each dependency has a two-second response deadline; blocking probes run off the
event loop. The container probe supplies `API_KEY` from its environment.

## Database backup and restore

Run from the repository root. Use a new directory for each backup:

```powershell
.venv-win/Scripts/python.exe -m src.commands.backup create test_output/backups/2026-10-08 --wsl Ubuntu
.venv-win/Scripts/python.exe -m src.commands.backup drill test_output/backups/2026-10-08 --wsl Ubuntu
```

Omit `--wsl Ubuntu` when `docker` is directly available. Both commands use the
PostgreSQL 16 client inside the existing Compose service, avoiding host-version
or host-port confusion. `create` writes a full compressed custom-format dump via
a binary file handle, plus a SHA-256 manifest. Do not pipe binary archives through
PowerShell text redirection. The dump includes the full database, including paper
text, parsed sections and migration state; it does not include cluster roles.
Roles/credentials are recreated from the intended environment configuration.

`drill` first verifies the archive checksum, creates a random
`scholarlens_restore_<uuid>` database from `template0`, and restores with
`--single-transaction --exit-on-error --no-owner --no-acl`. It compares all paper
fields ordered by arXiv ID plus migration revision, writes `restore-drill.json`,
and drops only that newly created scratch database. It never accepts an existing
restore target or uses `--clean`. On failure the command returns nonzero; preserve
its artifacts and investigate before treating the backup as usable. A failed
backup has no completed manifest and cannot be drilled. Do not rerun into an
existing backup/report directory.

Recovery into an actual replacement environment follows the same empty-target
procedure: create a new database, restore the verified archive with matching
PostgreSQL tooling, verify fingerprints, then change application connection
settings only after explicit approval. The CLI intentionally performs drills
only and never switches the live application. It rejects a changing paper
fingerprint during backup; retry in a new directory after ingestion is idle.

Take a backup before any destructive corpus/schema operation and after accepted
repairs. Current backup cadence is manual; loss since the most recent verified
backup remains possible. Store a protected copy off the workstation for machine
loss recovery and retain at least the last known-good backup through acceptance
of its successor. Off-machine storage and scheduled jobs are not configured in
this pass. Dumps contain the complete database and must not enter git or logs.

## Search, PDF and model recovery

The verified database preserves repaired parsed text even if the original PDFs
cannot be downloaded again. Preserve these additional local volumes for exact
environment recovery: `opensearch_data` (both v1/v2 indexes and aliases),
`airflow_pdf_cache` (PDFs and `.repair` checkpoints), `ollama_data` (model files),
and `airflow_model_cache` (Docling cache). Save configuration, source revision,
index mappings/aliases, model digests and backup checksums beside the archives.
Airflow logs are useful diagnostics but do not replace paper data.

For an exact volume backup, use a maintenance window: pause ingestion, stop the
owning service, archive the named volume using a read-only mount, then restart
that same service. Never copy a live PostgreSQL/OpenSearch data directory and
claim it is a consistent snapshot. Restore archives into **new empty volumes**
on an isolated network using matching service versions, compare paper/chunk
fingerprints and model digests, and inspect alias targets before switching any
live configuration. Never extract over a currently mounted live volume or use
`docker compose down -v` as a recovery step.

An alternative on a new environment is to rebuild current search indexes from
restored parsed text using the existing indexers and the same model digest.
That does not reproduce a historical v1 index; exact rollback state requires
the cold search-volume archive. Keep the existing v1 and v2 volumes intact.
PDF and Docling caches can be redownloaded where sources still exist, but repair
checkpoints and withdrawn/unavailable source files should be preserved.

The local drill verifies full database restore and paper content, not cold-volume
recovery or machine-loss recovery. No volume was stopped, replaced or deleted.
Those maintenance drills remain separate operational work before any deployment.

## Local verification evidence

2026-10-08 (Africa/Cairo): 443 tests passed, 32 existing Docker-dependent skips;
Ruff, mypy, diff and Compose configuration checks passed, along with a
two-worker temporary Docker API smoke test, and the real PostgreSQL restore drill.
The temporary API verified key rejection, authenticated dependency readiness,
SSE completion, generation rejection and concurrent shared request quotas. It
was removed afterward. Fault-injection tests cover selector/SSE error correlation,
stream-body latency, storage failure and unavailable dependencies.

Artifacts are under ignored `test_output/week6/`: `runtime.json`,
`runtime-docker.log`, `database-backup/manifest.json`,
`database-backup/restore-drill.json` and `preservation.json`. The original runtime
was not rebuilt or restarted, and no production deployment occurred.

Preservation checks matched all 58 full paper rows, 58 paper-index documents,
1,221 v1 chunks, 2,775 v2 chunks including embeddings, all alias targets,
both installed model digests and every evaluation file. Candidate default
remains 1; no selector prompts, grammar or evidence policies were tuned.
