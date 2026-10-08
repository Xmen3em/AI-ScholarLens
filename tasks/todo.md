# Week 6 local verification

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

Before any separately approved deployment: rehearse cold-volume/machine-loss
recovery, provision off-machine backups, choose multi-replica limits if needed,
and replace development-only infrastructure configuration. These were documented
and not silently counted as verified deployment controls.
