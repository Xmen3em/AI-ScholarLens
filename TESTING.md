# Testing AI-ScholarLens

This guide covers the automated tests and Docker-backed checks for the current Week 2 implementation.

## 1. Fast automated tests

These tests do not require Docker, PostgreSQL, OpenSearch, Ollama, Airflow, or internet access.

`.env.test` is loaded into the environment by pytest-dotenv (`env_files` in `pyproject.toml`).
Environment variables outrank the `.env` file in pydantic-settings, so the suite is insulated
from whatever a developer keeps locally — without it, a stray `OLLAMA_MODELS` or
`ARXIV__MAX_RESULTS` on one machine silently changes what the tests exercise.

Adding a setting to `src/config.py` means adding it to both `.env.example` and `.env.test`;
`tests/unit/test_config_and_schemas.py` derives the expected variable names from the settings
models and fails if either file drifts, in either direction — a missing setting or a name left
behind after a rename. It also loads `.env.example` through `Settings` to prove that
`cp .env.example .env` yields a config that works.

From the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The suite currently covers:

- Settings parsing and paper schemas
- arXiv XML parsing and PDF cache hits
- Ollama health, generation, and connection-error handling
- API ping and paper-list/detail endpoints
- Ingestion pipeline accounting: download/parse counters, skips, and recorded failure reasons
- The AI category allowlist and its scope predicate, including cross-listed and malformed categories
- The grouped arXiv category query, and that it stays ANDed with the submission-date window
- That non-AI papers are counted as `papers_filtered_non_ai` but never downloaded, parsed, or stored
- The `ai_scope` purge guards: dry run by default, expected-count mismatch aborts, and `--apply`
  deletes exactly the rows the audit counted
- Chunk boundaries: section splitting and overlap, bibliography and parser-artifact exclusion,
  malformed section entries, and that chunk ids stay stable across runs
- What the chunk indexer writes: exactly the mapped fields, one document per chunk through the
  alias, JSON columns reduced to string lists, and a rejected chunk failing only its own paper
- That stale-chunk cleanup is skipped when any paper failed to index — otherwise a transient
  failure would delete chunks that are still good
- The search query body: the 3x/2x/1x field boosts, `best_fields` scoring, fuzzy matching,
  the category filter, pagination, date sorting, and highlight configuration
- How an OpenSearch response becomes a `SearchResponse`, including a null score on a
  date-sorted hit, a malformed highlight, and a missing index reported as an empty result
- The paper indexer: one document per paper, unparsed papers still searchable, and the
  full document text kept out of the paper index
- The search endpoint: every option forwarded, defaults applied, invalid input rejected
  with a 422 before the backend is touched, and an unreachable backend surfaced as a 503
- The Airflow-to-metadata-fetcher method contract, and that every `xcom_pull` names a task the
  DAG actually declares

Run a focused group while developing:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m pytest tests\api -q
```

### Repository tests against a real database

`tests/integration/` exercises `PaperRepository` against a throwaway PostgreSQL 16
container started by `testcontainers`, with the schema created from the SQLAlchemy models.
Persistence is the subject there, so a mocked session would verify nothing: these tests
cover the idempotent `upsert` the ingestion DAG depends on, the unique `arxiv_id`
constraint, pagination order, and the processing-stats queries.

`tests/integration/test_database_startup.py` covers the entry point every service goes
through — `make_database()` -> `startup()` -> a usable session — including that a second
service starting against the same database is a no-op, that a database created before
migrations existed is baselined without disturbing its rows, and that asking for a session
before `startup()` fails loudly.

`tests/integration/test_migrations.py` covers the schema itself: that migrations build the
`papers` table on an empty database, that a database created by the old `create_all` is
baselined without losing rows, that reruns are idempotent, and that Airflow's tables and its
`alembic_version` row in the same database are left alone. Its last test compares the migrated
schema against `Base.metadata` column by column, so a model change with no matching migration
fails the build.

`tests/integration/test_ai_scope_command.py` covers the audit and purge command against the
same container: that the audit reports non-compliant rows without touching them, that a
dry run and a mismatched `--expected-count` both delete nothing, that an applied purge is
committed and removes only the rows it counted, that rerunning it is idempotent, and that
cross-listed AI papers survive. Purge hard-deletes, so these are the checks a mocked
session cannot stand in for.

They need Docker running and take about 20 seconds on the first run, including container
startup. When Docker is unavailable they skip, so the command above stays green without it.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration -q
```

`uv run pytest` is also supported when the local uv cache is working. The virtualenv command above avoids local uv-cache issues.

## 2. Start the application stack

Make sure Docker Desktop is running, then run:

```powershell
docker compose up --build -d
```

If host port `8080` is already occupied, choose another Airflow host port:

```powershell
$env:AIRFLOW_PORT = "8081"
docker compose up -d
```

Check containers:

```powershell
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 airflow
```

The API image must stay running without `ModuleNotFoundError`. Airflow may take one or two minutes to become healthy.

## 3. Service smoke tests

Run these from PowerShell after the containers start:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/ping
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod http://localhost:9200/_cluster/health
Invoke-RestMethod http://localhost:11434/api/version
Invoke-WebRequest http://localhost:8080/health
```

If `AIRFLOW_PORT` is set to `8081`, use `http://localhost:8081/health` instead.

Expected results:

- API ping returns `status: ok` and `message: pong`.
- API health returns HTTP 200 and reports database/Ollama status.
- OpenSearch returns cluster health JSON.
- Ollama returns a version JSON response.
- Airflow returns HTTP 200.

Open the API documentation at `http://localhost:8000/docs` and Airflow at the configured Airflow host port. The default Airflow credentials are `admin/admin`.

## 4. Database checks

Verify PostgreSQL is accepting connections and that the papers table exists:

```powershell
docker compose exec postgres pg_isready -U rag_user -d rag_db
docker compose exec postgres psql -U rag_user -d rag_db -c "\dt"
docker compose exec postgres psql -U rag_user -d rag_db -c "SELECT COUNT(*) FROM papers;"
```

The API paper endpoint should return an empty page before ingestion:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/papers/
```

## 5. Airflow and ingestion pipeline

Check that DAGs load without import errors:

```powershell
docker compose exec airflow airflow dags list
docker compose exec airflow airflow dags list-import-errors
```

The expected DAG is `arxiv_paper_ingestion`, with no import errors.

Trigger it from the Airflow UI or CLI:

```powershell
docker compose exec airflow airflow dags trigger arxiv_paper_ingestion
```

Inspect the task graph and logs for:

1. `setup_environment` — database connection succeeds.
2. `fetch_daily_papers` — arXiv metadata is fetched.
3. `process_failed_pdfs` — failures are reported without stopping the report path.
4. `index_to_opensearch` — paper and chunk document counts are reported.
5. `generate_daily_report` — counts and processing time are logged, including
   `Filtered as non-AI`.
6. `cleanup_temp_files` — temporary PDFs are cleaned up.

The `fetch_daily_papers` log should show the grouped category query and, when arXiv returns
anything cross-listed out of scope, a `Discarded N of M papers outside the AI scope` warning.
The batch size comes from `ARXIV__MAX_RESULTS` (10 in `compose.yml`) and is a total across all
eight categories, not a per-category quota.

After a successful run, verify that the database count increased:

```powershell
docker compose exec postgres psql -U rag_user -d rag_db -c "SELECT arxiv_id, title, pdf_processed FROM papers ORDER BY created_at DESC LIMIT 5;"
```

Then confirm nothing out of scope was stored:

```powershell
docker compose exec airflow python -m src.commands.ai_scope audit
```

A healthy run reports 0 non-compliant papers.

### Search indices

The `index_to_opensearch` task log reports, for each index, papers seen, papers indexed,
documents written, and stale documents removed. Check the indices directly:

```powershell
curl.exe "http://localhost:9200/arxiv-papers/_count"
curl.exe "http://localhost:9200/paper-chunks/_count"
curl.exe "http://localhost:9200/_alias/arxiv-papers"
curl.exe "http://localhost:9200/_alias/paper-chunks"
```

`arxiv-papers` must hold one document per row in `papers`, including the rows whose PDF never
parsed. Each alias must resolve to its `-v1` index.

Triggering the DAG a second time is the real check: both counts must stay the same and
`stale_documents_deleted` must be 0 — document ids are derived from the paper, so a rerun
overwrites rather than duplicates. A count that grows on a rerun means document identity broke.

### Search endpoint

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/search/ -ContentType application/json `
  -Body '{"query": "retrieval augmented generation", "size": 3}'
```

Check that the top hit has the query terms in its *title* rather than only its abstract — that
is the 3x title boost doing its job — and that `highlights` comes back with `<mark>` tags. A
misspelled query ("retreival augmnted generaton") must return the same papers; if it returns
nothing, fuzzy matching is not reaching the query body.

`took_ms` is OpenSearch's own timing. On this corpus the whole round trip measures 15-40ms:

```powershell
curl.exe -s -o NUL -w "%{time_total}s" -X POST http://localhost:8000/api/v1/search/ `
  -H "Content-Type: application/json" -d '{\"query\":\"reinforcement learning\"}'
```

### Corpus scope audit and cleanup

`audit` is read-only and safe to run at any time. `purge` deletes permanently, so back up
the table first and keep the dump until the cleaned corpus is accepted:

```powershell
docker compose exec postgres pg_dump -U rag_user -d rag_db -t papers > papers_backup.sql
docker compose exec airflow python -m src.commands.ai_scope audit
docker compose exec airflow python -m src.commands.ai_scope purge --expected-count N
docker compose exec airflow python -m src.commands.ai_scope purge --expected-count N --apply
docker compose exec airflow python -m src.commands.ai_scope audit
```

Take `N` from the audit output. The third command is a rehearsal that writes nothing; the
fourth performs the deletion and aborts if the count has drifted since the audit. The final
audit should report 0 non-compliant papers.

Exit codes: `0` success, `1` unexpected error, `2` command-line usage error, `3` violations
found (only with `audit --fail-on-violation`), `4` expected-count mismatch.

## 6. PDF processing check

PDF parsing is exercised inside the Airflow image because that image contains Docling and its native dependencies. Trigger the ingestion DAG with PDF processing enabled, then inspect the `fetch_daily_papers` log for download and parse counts.

For a full manual check, confirm that successful records contain:

- `pdf_processed = true`
- non-empty `raw_text`
- populated `sections` when the PDF has detectable headings
- `parser_used = docling`

Some PDFs can fail parsing; the expected behavior is for the pipeline to record the failure and continue processing other papers.

## 7. Fresh Week 2 database

Only use this when existing data can be discarded or the schema is inconsistent:

```powershell
docker compose down -v
docker compose up --build -d
```

The `-v` option deletes the PostgreSQL, OpenSearch, Ollama, and Airflow log volumes, along with the cached arXiv PDFs and Docling's downloaded model weights. It is destructive and should not be used as a routine test command: the next ingestion run has to re-download roughly 500 MB of models before it can parse anything.
