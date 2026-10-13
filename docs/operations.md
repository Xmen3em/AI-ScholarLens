# Local operational controls

## Week 7 optional agent source

The [bounded-agent spec](week7-agent-spec.md) records the audited implementation.
`AGENT_ENABLED=false` remains the source default; disabled authenticated agent
requests return 503. Optional `/api/v1/agent/ask` and `/api/v1/agent/stream` use
the same global request/generation quota before work and always bypass Redis
answer caching. One request reserves one generation slot and makes at most six
generation calls plus, in hybrid mode, two query embeddings. Workflow defaults
are 90 seconds total and 30 seconds per stage, controlled by bounded
`AGENT_DEADLINE_SECONDS` and `AGENT_NODE_TIMEOUT_SECONDS` settings.

No Week 7 activation occurred. The retained one-worker Week 6 API/image/key/cache,
rollback container and all dependency resources remain in their prior state.
Do not rebuild/recreate them to try the source feature as routine setup. Agent
scope/grading/rewrite/selection and status delivery pass isolated tests; live
quality, cold/sustained resource acceptance and deployment remain future gates.
Cancelled synchronous retrieval can finish a bounded read under existing backend
timeouts; its agent worker slot remains occupied until it ends. Cancelling HTTP
does not guarantee that remote model computation terminates.

For the user's recommended next step, see the prepared
[off-machine transfer and receiving procedure](week6-off-machine-transfer.md).
The encrypted USB route and separate-machine targets are documented; no transfer
or rehearsal has occurred because the device/path and second machine are missing.

The subsequent [short observation](week6-observation.md) completed eight normal
Gradio requests with four real misses/hits, no failures and preserved runtime/data.
Cold inference briefly left 539 MiB free host memory; sustained capacity remains
unverified. The frozen recovery bundle verifies, but off-machine copy still awaits
a user-selected protected destination and separate-machine recovery is pending.

Local caching and file monitoring are now active in the healthy one-worker API.
Read [local activation and rollback](week6-local-activation.md) for the measured
memory plan, preserved original API/key, runtime controls and current evidence.
This supersedes the stopped-state and pending-activation statements below.
Langfuse, Airflow and Dashboards remain stopped during normal RAG operation.

The approved [staged live acceptance](week6-live-acceptance.md) supersedes the
pending live-probe/Langfuse checks in the earlier source-only record below.
Real revision/caching paths and a separate full Langfuse backend/console passed.
Original services and the new private lab are restored stopped. Continuous
co-running with loaded Ollama/OpenSearch remains unverified; the original API
image/key/configuration were preserved and its new feature flags remain off.

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
answers, keys and provider exception text. Opt-in local trace export and bounded
monitoring reports are now implemented below. A full Langfuse backend/UI and
automatic alerts have not been provisioned; no cloud telemetry is enabled.

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
The Gradio client reads the key through application settings, including `.env`,
and forwards it server-side. The normal launcher binds to `127.0.0.1:7861`.

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
retain their previous bindings until recreated. The local API was rebuilt and
activated on 2026-10-12, with a configured key and localhost binding. Other
services retain their previous bindings; those services were not recreated.

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

The 2026-10-08 drill verified full database restore and paper content. The
2026-10-12 isolated drill additionally verified recovery of all four volumes as
described below. Off-machine storage and machine-loss recovery remain unverified.

### Isolated volume recovery verified — 2026-10-12

Evidence is in ignored `test_output/volume-recovery-20261012-01/`. The approved
drill used the existing installed image IDs, not mutable tags or downloaded
images. `inventory.json` records the actual mounts and original container IDs.
Preflight found approximately 51 GiB free on D:, 48 GiB on C:, and 4.1 GiB available
inside the Docker VM; no image, cache or volume pruning was needed.

| Actual source volume | Verified recovery |
| --- | --- |
| `ai-scholarlens_opensearch_data` | 387 files; 58 paper-index documents, 1,221 v1 chunks, 2,775 v2 chunks; complete document contents/vectors, mappings and alias inventory matched |
| `ai-scholarlens_airflow_pdf_cache` | 323 files, including 57 PDFs and the `.repair` checkpoints |
| `ai-scholarlens_ollama_data` | 13 files; restored Ollama reports the same `llama3.2:1b` and `nomic-embed-text:latest` digests |
| `ai-scholarlens_airflow_model_cache` | 62 files; all cached Docling/Hugging Face file contents and symlinks matched |

The four uncompressed PAX tar archives total 2,405,140,480 bytes (2.24 GiB).
Every source, archive and restored entry matched on SHA-256/file size, type,
ownership, permissions, nanosecond modification time and symlink target.
`report.json` records archive checksums and the recovery results; the individual
`*.source-files.json`, `*.archive-files.json` and `*.restored-files.json` manifests
retain the complete comparisons. Access times are not compared.

`final-archive-and-source-check.json` also confirms that all archive checksums
still match and that the three original cache/model volumes remain unchanged
after their owning processes resumed.

Airflow was already running but unhealthy before this drill. Its processes were
paused for about 53 seconds while its two caches were read, then unpaused without
rerunning startup or changing its existing unhealthy state. OpenSearch was
gracefully stopped, archived with a read-only source mount, and the same container
restarted after 7.69 seconds (stop exit 143). Ollama used the same procedure and
restarted after 107.62 seconds (exit 0). These timings measure stop request to
restart, not dependency readiness; authenticated readiness was checked afterward.
The original API, PostgreSQL and Dashboards containers and Gradio process kept
running. Service restoration was in a `finally` path.

The command actually run from the repository root was:

```powershell
.venv-win/Scripts/python.exe test_output/volume-recovery-20261012-01/drill.py
```

This is preserved drill evidence, not an installed application command. The
script refuses an output directory containing `inventory.json`. For another
authorized drill, copy only `drill.py`, `files.py` and `probe.py` into a new
directory directly under `test_output`, inspect current resources, and run that
new copy. Do not copy archives, reports or an old inventory into the new directory.

`commands.jsonl` preserves the exact Docker argument arrays. Helpers used
`--pull=never`, the installed API image as their Python/tar tool image,
`--network none`, `--read-only`, and a source mount of the form
`type=volume,src=<actual-source>,dst=/data,readonly,volume-nocopy`.
Archiving used `tar --format=pax --numeric-owner -cpf /evidence/<volume>.tar
-C /data .`. Extraction used `tar --same-owner --numeric-owner -xpf
/evidence/<volume>.tar -C /data`, with `/data` bound only to a newly created,
empty scratch volume and `/evidence` read-only. No live mount was switched.

The run owned only resources labeled
`scholarlens.recovery=sl-recovery-2ea30617ff42`; names and ownership are saved in
`ownership.json`. Its network was created with `--internal`. Scratch OpenSearch
and Ollama published no ports, mounted only their respective restored volumes,
and used the exact installed source image IDs. They ran sequentially with memory
limits of 1,536 MiB and 384 MiB; helpers were limited to 512 MiB. Probes compared
all application search documents/vectors and mappings, the entire alias inventory,
and Ollama's installed-model digests through the isolated services. All scratch
resources were removed after label verification; `cleanup.json` and
`post-cleanup.json` confirm removal.

`preservation.json` verifies the full paper fingerprint/schema revision, original
search contents/mappings/aliases, model digests, prior evaluation/test artifacts,
workspace files, ignored `.env`, original container IDs/images/mounts and running/
paused states. Final API liveness/readiness and Gradio page/config returned 200.
The workspace comparison preceded the authorized operations/todo/handoff updates;
runtime source and all preexisting evaluation/test artifacts remain unchanged.
`source-parity.json` confirms 72 active source files still match, the key remains
configured, and candidate count remains 1. PostgreSQL restore was not repeated:
its prior full-database restore passed and the current paper/schema fingerprint
still matches that evidence.

This verifies same-version local volume recovery, not application failover,
machine-loss recovery, cross-version portability or a new quality evaluation.
Docling was not run against the restored cache and Ollama inference was not run;
their cache files/model inventory were verified without parsing or generation.
Archives remain on this workstation; protected off-machine backups and recovery
of source/configuration/credentials in a replacement environment remain open.
No ingestion, reparsing, reindexing, model download/replacement, deployment or
selector tuning was performed.

### Recovery bundle and replacement rehearsal — 2026-10-12

After the volume drill, the user approved preparing off-machine backups,
rehearsing a replacement environment, and diagnosing the existing Airflow failure.
Evidence is in `test_output/replacement-recovery-20261012-01/`. The complete local
bundle is in its `bundle/` directory (approximately 8.35 GiB). It contains a fresh
full PostgreSQL custom archive, the four previously verified volume archives,
current source/working-tree files, Git history, private `.env` configuration, the
six installed Docker images, recovery instructions/tools and verification evidence.
Its directory ACL permits the current account, SYSTEM and administrators.
Credentials remain ignored and are never printed or placed in tracked artifacts.

`bundle/manifest.json` records complete file checksums; `bundle/RECOVERY.md`
documents receiving-copy verification and recovery. Off-machine transfer is
**pending a destination**. C:, D: and E: were inspected and are all internal NVMe
partitions, not removable backup destinations. A removable drive with at least
64 GB free is recommended for retention/headroom. Protect the receiving storage;
on compatible Windows installations, [BitLocker To Go encrypts removable drives](https://learn.microsoft.com/en-us/windows/security/book/operating-system-security-encryption-and-data-protection).
No drive was formatted, encrypted, overwritten or silently counted as off-machine.

The image export used binary-safe Docker stdout streamed through gzip. All six
OCI descriptor identities, all 73 content-addressed blobs and the gzip CRC passed.
Docker loaded the archive successfully, and every preexisting image reference was
preserved. The archive contains no repository tags. Docker Desktop 4.87.0 / Engine
29.7.2 with its containerd image store (`linux/amd64`) was verified; its image IDs
are OCI indexes/manifest lists rather than image configuration hashes.
`image-load-verification.json` and `bundle/image-export-verification.json` retain
the results. The initial incorrect configuration-hash comparison and first
rehearsal evidence are preserved rather than overwritten.

The first replacement rehearsal recovered all four volume file manifests and a
fresh PostgreSQL cluster, but stopped at host-port verification. A minimal Docker
reproduction confirmed that this engine's internal networks do not allocate
published host ports. The successful `rehearsal2/` and packaged-script
`portable-rehearsal/` runs kept all traffic inside new internal networks with no
published ports. Both restored from the bundle into five new volumes and verified
all 58 paper rows/schema revision, full search contents/vectors/mappings/aliases,
installed model digests, authenticated API readiness and all paper records,
Gradio page/config and its client-to-API validation flow. An invalid request tested
the client boundary without generation. No inference, parser execution, ingestion
or reindexing was run. Airflow/Dashboards images are archived; their startup is
outside this replacement application rehearsal.

The packaged command was verified from the repository root:

```powershell
.venv-win/Scripts/python.exe -B test_output/replacement-recovery-20261012-01/bundle/recovery-tools/recovery_rehearsal.py test_output/replacement-recovery-20261012-01/bundle test_output/replacement-recovery-20261012-01/portable-rehearsal
```

Use a new evidence directory for every later run. The packaged tool needs only
Python's standard library and Docker CLI; it never switches live connections.
Runtime credential files and owned scratch resources were removed in the cleanup
path. Ownership, isolation, logs and results remain beside each report. The
successful rehearsal used previously loaded matching images; archive loadability
was independently verified through Docker. A different host/architecture/image
store, receiving-copy checksums, actual machine-loss recovery and cutover remain
unverified. Historical ignored test outputs, Airflow logs and host virtual
environments are excluded from this bundle and remain on the source workstation.

`preservation.json` confirms complete original paper/index/model fingerprints,
all mount attributes, original container IDs/images/running/paused/health states,
the key, 72 active source files, candidate default 1, healthy API/Gradio and all
8,828 prior artifacts/frozen evaluations. Mount comparisons use unique destination
keys because Docker inspection can reorder the same mount entries. Documentation
updates followed this preservation comparison. No original service was restarted
or replaced during this continuation, and no deployment or selector tuning occurred.

### Airflow diagnosis — no live repair applied

`airflow-diagnosis.json` and the isolated reproduction identify the existing
webserver failure. A stale `/opt/airflow/airflow-webserver-monitor.pid` contained
PID 29. The installed Airflow 2.10.3 daemon guard checks whether that PID exists,
not whether it is the same webserver process; PID reuse at restart caused the
"already running" error. The entrypoint removes `airflow-webserver.pid` and
`airflow-scheduler.pid` but leaves the monitor PID file. It also invokes `pkill`,
which is absent from the installed image. A temporary PID file naming the current
process reproduced the guard's rejection in a container with no live mounts.

Port 8080 is closed while the scheduler/log server is running. Both existing DAGs
are paused, with zero active runs/tasks. No stale file or live process was removed,
and no scheduler/DAG/configuration change was applied. The source Airflow remains
in its preexisting unhealthy state. A targeted entrypoint repair and isolated
startup/regression verification remain separate work; restarting the normal
entrypoint casually can run database initialization and a scheduler.

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

On 2026-10-12, the user approved local activation. Only the API was rebuilt and
recreated, with its previous image retained as `scholarlens-api:pre-week6-activation`.
A generated key was saved in the ignored `.env` file. Gradio's dotenv key handling
was fixed with a regression test, and its launcher was bound to localhost.
All 476 tests passed, including Docker integration tests; Ruff and mypy passed.
Active-container acceptance evidence is under `test_output/week6-activation/`.
The normal Gradio UI rendered a complete answer and source links in isolated
Chrome, with zero uncaught browser errors. The activated API rejects missing or
wrong keys, enforces both budgets, preserves readiness during quota exhaustion
and resumes ordinary traffic after the window reset. Source parity matched 72
files, and dependency container IDs/corpus/index/model/evaluation fingerprints
were preserved. A new empty-alias OpenSearch query-telemetry inventory entry was
recorded separately; all existing alias entries and actual targets were unchanged.
Deployment, full-volume recovery and answer-quality tuning remain outside this
activation pass; the previously measured answer-quality defects remain open.

Preservation checks matched all 58 full paper rows, 58 paper-index documents,
1,221 v1 chunks, 2,775 v2 chunks including embeddings, all alias targets,
both installed model digests and every evaluation file. Candidate default
remains 1; no selector prompts, grammar or evidence policies were tuned.

## Opt-in local tracing, answer caching and monitoring — 2026-10-13

The [audit and resource plan](week6-monitoring-plan.md) records the decision to
defer the full Langfuse backend. All six application containers were already
stopped; Windows had about 710 MiB free and Docker has an 8 GiB VM. Their original
IDs, images, mounts, stopped state and configured API key are retained. No API
rebuild, stack activation, deployment, selector tuning or model execution occurred.
The source changes below are verified locally but are not in the activated image.

Install the optional runtime dependencies for a host run:

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.venv-win'
uv sync --locked --inexact --extra week6
```

The optional `week6` extra locks OpenTelemetry SDK/OTLP HTTP 1.45.1 and Redis
client 7.4.1; all preexisting locked package versions are unchanged. Dev installs
include these dependencies for tests. The Dockerfile also accepts the build
argument `WEEK6_EXTRAS=--extra week6`; its default still installs the base runtime.
Setting environment flags alone does not update the current API image. Do not
run an unrelated full-stack Compose rebuild as setup.

### Tracing

`LOCAL_TRACING_ENABLED=false` is the default. To opt in on a separately prepared
local runtime, set it to `true`, set `LOCAL_TRACING_URL` to a local Langfuse HTTP
origin, and supply that project's `LOCAL_TRACING_PUBLIC_KEY` and
`LOCAL_TRACING_SECRET_KEY`. These are separate from the preserved application
API key. Host default: `http://127.0.0.1:3000`; container host access can use
`http://host.docker.internal:3000`, or `http://langfuse-web:3000` on the relevant
local Docker network. Cloud origins, URL credentials, paths, queries and
fragments are rejected. No backend/project credentials were provisioned here.

Native Langfuse OTLP ingestion uses `/api/public/otel/v1/traces`, Basic auth and
`x-langfuse-ingestion-version: 4`. The provider is isolated; it does not register
global HTTP/database/model instrumentation or inherit an external exporter URL.
Only server IDs and allowlisted operational metadata reach it. HTTP roots span
the full ASGI response; retrieval and generation/validation phases are nested.
Each generation includes actual Ollama timings/token counts, with retries and
bounded validation reasons. Stream completion, failure and interruption are
correlated. No question, citation/evidence text, prompt, answer, exception text,
key, input/output attribute or cost estimate is exported.

The exporter queues at most 256 spans per worker, sends batches of at most 32,
and attempts each HTTP export once with a 0.5-second transport timeout. It uses
neither proxies nor redirects and never reads an unbounded response body.
Exporter failure drops telemetry and logs a fixed warning; request handling does
not flush or wait for network export. Shutdown drains the finite queue off the
event loop. Queue overflow can drop spans; this is best-effort diagnostics.

Current [self-hosting guidance](https://langfuse.com/self-hosting/deployment/docker-compose)
describes web/worker, PostgreSQL, ClickHouse, Redis and object storage, and
recommends 16 GiB for a VM. Do not use the course's old single-service/legacy
Langfuse configuration to bypass this capacity check. Full Langfuse ingestion,
storage, project authentication and UI acceptance remain pending resources.
The actual protobuf transport was verified against a loopback receiver, including
trace IDs, parentage, nonnegative timings and absence of private content.

### Redis exact-match answers

`ANSWER_CACHE_ENABLED=false` is the default. The `week6-cache` Compose profile
defines a separate volatile Redis service using the already installed immutable
image digest, 128 MiB container memory, 64 MiB cache capacity, LRU eviction and
loopback host port 6380. It has no application/recovery volume mount and is not
the unrelated `erp-redis` service. Supply a separate random
`REDIS_CACHE_PASSWORD`; the profile refuses startup if it is empty. Configure
`ANSWER_CACHE_URL` with that password, for example
`redis://:<password>@127.0.0.1:6380/0` for host tooling or
`redis://:<password>@redis-cache:6379/0` inside the local network. Do not print the
URL or put credentials in git. Local Redis origins are enforced.

Authentication and both SQLite budgets precede cache access; hits still consume
the same generation quota. Keys are HMACs of the exact effective request, model,
retrieval settings and code/prompt/schema policy digest, plus fresh corpus/index/
model identity. Revision probes read all PostgreSQL paper fields and migration
revision, read aliases/mappings/settings, primary shard sequence numbers and
searchable segment generations, and installed generation/embedding model
digests. Hits and writes recheck this identity. This is deliberately conservative
and adds read-only probe overhead; there is no cached/guessed identity fallback.

Redis values include the full server response and a signature bound to its key,
using domain-separated HMAC with the existing API key. Reads check the signature,
schema, request/model/mode, citation count, exact excerpt grounding and word
limit before serving. Only complete validated responses are stored. Hybrid
fallback is bypassed so a degraded BM25 result cannot hide restored embeddings.
Errors, invalid output and incomplete streams are never stored. SSE writes occur
only after the ASGI response was fully delivered. Both endpoints share the same
answer/citations/sources representation. Signed Redis values contain private
question/evidence/answer data; signatures provide authenticity, not encryption.

`ANSWER_CACHE_TTL_SECONDS` defaults to 3600, bounded to 1–86400. Identity changes,
policy changes, request/settings changes, key rotation and TTL expiry invalidate
entries; old keys expire naturally. Redis/probe errors bypass the cache and keep
the normal RAG path. Client connect/read deadlines are 0.25 seconds, no retries,
four connections per worker, with two-second cache-operation cancellation scopes.
Database work is read-only with a statement deadline; cancellation can leave a
bounded probe finishing in a background thread. No Redis flush is needed.
Caching preserves the existing answer-quality limitations; it does not improve
relevance, attribution or multi-paper coverage.

The synthetic live Redis acceptance verified TTL expiry, revision invalidation,
authenticated access, ask/stream hit parity and unavailable-Redis fallback. A
separate nonempty-citation test verifies exact quotations and source locators
survive hits without a second retrieval/generation. Live revision probes against
the stopped corpus/search/model services remain unverified; mocked boundary tests
cover revisions, visibility, model changes and missing aliases. Keep caching
disabled until those checks are accepted on a resourced local runtime.

### Local monitoring views

Set `MONITORING_DIRECTORY` to an ignored, protected local directory to enable
metadata JSON event files. Empty disables them. Files are per worker PID, rotate
at 1 MiB, and retain three backups: at most 4 MiB per worker PID. Files from old
worker PIDs remain until explicitly removed, so plan retention for frequent
restarts. Disk/write failure does not change requests. No raw logs or responses
are copied into these files; the same metadata allowlist is applied.

Generate a fresh offline snapshot with a new output filename:

```powershell
.venv-win/Scripts/python.exe -m src.monitoring test_output/monitoring test_output/monitoring-report-01.html
```

The HTML and companion JSON show nearest-rank p50/p95/p99 total response latency
by route, HTTP/SSE failures, authentication/quota rejections, retries, validation
failures, actual local Ollama tokens/durations including retries, and cache
hit/miss/stored/bypass/unavailable outcomes. Hit rate excludes bypass/unavailable
lookups. `--since <Unix-seconds>` filters the event window. The view is a retained
event snapshot, not a real-time dashboard or an alert system. Cache hits add no
generation tokens, and no billed provider cost is invented.

Evidence: `test_output/week6-monitoring-20261013-01/`, including `pytest-final.xml`,
`redis-acceptance.json`, `monitoring.html`, `monitoring.json`, `mutation.json`,
`preservation.json`, `guard-preservation.json` and source parity. **494 tests pass**,
including Docker integration tests; all-source mypy, changed-file Ruff, both
Compose configurations and diff checks pass. Full-repository Ruff also found one
preexisting import-order issue in unchanged `tests/api/test_operational_health.py`;
it was retained rather than mixing unrelated formatting into this task. An
existing Windows timer-dependent test now holds its simulated stream body for a
measured 40 ms, retaining its original latency assertion.

Preservation: all 304 checksummed key/evaluation/bundle baseline files match, all
72 original image source files matched before edits, model-volume fingerprints
match the verified recovery snapshot, and selector/retrieval guard files and
candidate default 1 are unchanged. Original containers were never started or
replaced; scratch Redis and test containers were removed. Fresh live corpus/index
counts, API/Gradio health and full Langfuse UI acceptance are not claimed while
the application stack remains stopped. The frozen recovery bundle remains its
prior verified snapshot; it was not refreshed with this new source.
