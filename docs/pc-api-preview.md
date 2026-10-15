# Isolated private PC API preview — 2026-10-15

The next local API is prepared at `127.0.0.1:8002`, separate from the retained
API on8000. It reuses the installed Windows environment and existing local
PostgreSQL/OpenSearch/Ollama services. No image rebuild, new model, broad Compose
restart, ingestion, reindex or original API replacement.

This first preview exposes authenticated paper browsing, detail, keyword/passage
search and optional local embedding search. All four question/stream endpoints
return503 without any HF or Ollama generation. HF/agent/cache/tracing are disabled
in an isolated settings copy; private `.env` remains unchanged. The bot remains
disabled and unconnected to the preview.

The normal production lifespan runs migrations. This preview has its own lifespan
and read-only PostgreSQL connections, with a three-connection pool and a connection
timeout. It checks `SELECT 1`; it runs no migrations. Search/embedding clients use
the same validated settings snapshot; startup/shutdown closes only owned clients,
including after partial failure or cancellation. Existing service containers,
model files and data are untouched. PostgreSQL's session read-only setting prevents
changes to persistent tables, while the original browse/search routes are reused.

The launcher permits only the existing loopback dependency ports,8002 for this
server,one worker and no access logs/WebSockets. It retains original API-key
authentication and quotas in a separate fixed ignored file:
`data/pc-app/api-quotas.sqlite3`. A single-instance lock protects that path; symlink
escape is rejected. It never changes the original API quota store or HF call ledgers.

Default/`--check` is offline: no server/network/database/state/lock writes. Run from
the project workspace:

```powershell
.venv-win/Scripts/python.exe -m src.commands.run_pc_api --check
```

Only the explicit preview command can start a server, after the retained1024MiB
host-memory admission requirement passes:

```powershell
.venv-win/Scripts/python.exe -m src.commands.run_pc_api --execute-preview
```

Do not point the bot at this preview expecting answers. Live HF qualification,
reviewed task/holdout acceptance and the qualified generation rollout are still
required. The preview prepares local integration; it does not qualify a model or
complete the user's end-to-end app goal.

The user's two new synthetic HF calls were explicitly approved. The first live
attempt stopped at543.75MiB free host RAM before provider/corpus/inference requests.
User could not free RAM; it later recovered naturally to1292.09MiB. The same
approved pair resumed in a fresh output and both cases passed with unchanged
source/corpus/models/labels and complete usage. Both calls are now used;21total,
zero remain. This diagnostic does not qualify the model or activate the app.
No preview or bot process has been started. Preserve all1024/600/384 resource gates.

**1,108 full tests pass,zero skips**,18new preview tests,mypy111,Ruff. Full suite
200.43seconds,two existing Typer/Click warnings. Source/credential/allowance audits
pass. Evidence is under `tests/test_output/pc-api-prep-20261015-01/`, including
the live-pair audit. The model remains unqualified; next prepare the full five-case
exact-schema qualification under a new explicit bounded allowance.

Official sources: [PostgreSQL read-only transactions](https://www.postgresql.org/docs/16/runtime-config-client.html#GUC-DEFAULT-TRANSACTION-READ-ONLY),
[SQLAlchemy connection arguments](https://docs.sqlalchemy.org/en/20/core/engines.html#use-the-connect-args-dictionary-parameter),
and [Uvicorn programmatic deployment](https://uvicorn.dev/deployment/).
