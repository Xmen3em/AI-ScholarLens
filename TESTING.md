# Testing AI-ScholarLens

This guide covers the automated tests and Docker-backed checks through the Week 5 RAG implementation.

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

### Running from both PowerShell and WSL

`.venv` cannot be shared between them. A Linux venv has `bin/python` and a `lib64`
symlink; a Windows venv has `Scripts\python.exe`. Whichever platform runs `uv` next
tries to replace the other's venv — and on Windows it fails partway with

```
error: failed to remove file `...\.venv\lib64`: Access is denied. (os error 5)
```

because deleting a symlink needs a privilege Windows does not grant by default. By then
it has already removed `bin/` and `lib/`, so the WSL venv is broken too. Recover with
`rm -rf .venv && uv sync` from WSL, where the symlink can be removed.

To use both, give Windows its own environment directory (gitignored):

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-win"    # add to your PowerShell profile to persist
uv sync
```

From the project root:

```powershell
uv run pytest -q
```

The suite currently covers:

- Settings parsing and paper schemas
- arXiv XML parsing and PDF cache hits
- Ollama model-aware readiness, configured generation timeout, validated normal responses,
  NDJSON streaming, and connection/error handling
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
- That the passage profile scores content over section heading and never the paper title,
  and that both profiles match by the same rules — only the fields differ
- Reciprocal rank fusion: agreement across both rankings outranks a single confident hit,
  only positions are used, and ties break deterministically
- Embedding reuse: an unchanged passage is never embedded twice, edited text is re-embedded
  without touching its neighbours, and an embedding failure fails the run rather than
  indexing a passage with no vector
- The alias swap: it moves onto the new index in one action, only after a clean rewrite,
  and the superseded index is left in place to roll back to
- Hybrid fallback: an unreachable embedding model returns keyword results labelled
  `mode: keyword`, and never issues a vector query
- How an OpenSearch response becomes a `SearchResponse`, including a null score on a
  date-sorted hit, a malformed highlight, and a missing index reported as an empty result
- The paper indexer: one document per paper, unparsed papers still searchable, and the
  full document text kept out of the paper index
- Both search endpoints: every option forwarded, defaults applied, invalid input rejected
  with a 422 before the backend is touched, and an unreachable backend surfaced as a 503
- Grouping by paper: a dominant paper cannot fill the page, a paper keeps the position of
  its best passage, and the keyword fallback groups and caps like the fused path
- RAG controls, grouped top-k semantics, prompt isolation, 12,000-character evidence budgeting,
  round-robin paper diversity, exact citation coordinates, invalid-marker rejection, and no-evidence behavior
- Standard answer error mappings and SSE ordering (`sources -> delta* -> done|error`)
- Gradio payloads, SSE parsing, accumulated rendering, error display, and partial-answer discard
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

Install the two configured models explicitly:

```powershell
docker compose exec ollama ollama pull llama3.2:1b
docker compose exec ollama ollama pull nomic-embed-text
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
- API health returns HTTP 200 when ready or degraded. It returns 503 when the database,
  Ollama, or the default generation model is unavailable.
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
parsed. Its alias resolves to `arxiv-papers-v1`; `paper-chunks` resolves to the vector-enabled
`paper-chunks-v2`. Preserve `paper-chunks-v1` when checking or switching the chunk alias.

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

Hybrid search fuses both rankings:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/search/hybrid -ContentType application/json `
  -Body '{"query": "how do they stop the model making things up", "size": 5}'
```

`mode` must read `hybrid`. If it reads `keyword`, `fallback_reason` says why — most often
the embedding model has not been pulled:

```powershell
docker compose exec ollama ollama pull nomic-embed-text
```

That fallback is the behaviour to check deliberately: stop Ollama, search again, and the
endpoint must still return keyword results with `mode: keyword` rather than a 503.

Hybrid `score` values sit near 1/60 and are *not* BM25 scores — they are fused ranks, so
comparing them against `/search/chunks` scores is meaningless.

Passage search is the other half:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/search/chunks -ContentType application/json `
  -Body '{"query": "how are the benchmarks constructed", "size": 4}'
```

Results are **papers, each with up to three passages**; `size` counts papers. Every passage
must carry `section_index` and `chunk_index`.

### Repairing chunkless PDFs under memory pressure

If a whole-PDF retry exits with 137, it was killed; that exit code alone does not prove
an OOM kill. Inspect the counters in the actual repair container while it still exists.
Counters from the main Airflow container do not describe a separate `compose run` container.

The explicit repair command below splits the cached PDF into one-page PDFs and starts a
fresh Docling worker for each batch. Successful batches are checkpointed under the
persistent PDF cache's `.repair` directory. Re-running the same command resumes those
checkpoints, keyed by the source PDF hash, Docling version, and batch size. The stored
paper is updated only after every batch reports a complete conversion and the combined
content produces usable chunks. The command also refuses to overwrite a row changed
by another process during parsing. Scheduled ingestion and its default limits are unchanged.

Run from the repository root in PowerShell. First stop competing services; PostgreSQL
is the only service required during this repair:

```powershell
docker compose stop api ollama opensearch-dashboards opensearch airflow
docker compose up -d postgres

try {
    docker compose run --rm --no-deps -T --name scholarlens-pdf-repair `
        -w /opt/airflow --entrypoint python `
        -e OMP_NUM_THREADS=1 -e DOCLING_NUM_THREADS=1 `
        airflow -u -m src.commands.repair_pdf `
        2608.27456v1 2608.27763v1 2608.27774v1 `
        --pages-per-batch 1 --max-pages 60 --max-file-size-mb 50 --apply

    $repairExitCode = $LASTEXITCODE
    Write-Host "Repair exit code: $repairExitCode"
}
finally {
    docker compose up -d
}
```

`src/` is mounted into the Airflow service, so this command does not require an image
rebuild. Omit `--apply` to inspect the specified stored rows without downloading,
parsing, or updating their content. Use exact versioned IDs. Papers already producing
chunks are skipped. Errors are reported per paper; the command attempts the remaining
IDs and exits nonzero if any failed.

In a second terminal, monitor the named repair container while it is running:

```powershell
docker stats --no-stream scholarlens-pdf-repair
docker exec scholarlens-pdf-repair cat /sys/fs/cgroup/memory.events
```

Look for `Completed pages ...`, followed by `REPAIRED <id>: ... chunks` for each paper
and exit code 0. If a worker fails, the error names the original page range and checkpoint
directory. Retry with the same options to resume. The command reduces the number of
pages resident in each Docling worker; a single unusually complex page may still exceed
available memory. Page batching can change section segmentation, so inspect the resulting
evidence and reindex the whole corpus after a successful repair.

`2608.30076v2` is intentionally excluded from this repair list: its
[arXiv record](https://arxiv.org/abs/2608.30076v2) marks it withdrawn with no PDF available.
Keep its metadata and document that exclusion rather than relabeling another version
as v2. For the reported 48-paper corpus, successful repair of the three IDs above leaves
47 papers producing chunks and one withdrawn paper without chunks, assuming no ingestion
has changed the corpus meanwhile. That is an acceptance exclusion, not a repaired PDF.

### Grounded RAG acceptance

Exercise both retrieval modes:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/ask -ContentType application/json `
  -Body '{"query":"how do the papers ground generated claims","top_k":3,"use_hybrid":true}'

Invoke-RestMethod -Method Post http://localhost:8000/api/v1/ask -ContentType application/json `
  -Body '{"query":"how do the papers ground generated claims","top_k":3,"use_hybrid":false}'

curl.exe -N -X POST http://localhost:8000/api/v1/stream `
  -H "Content-Type: application/json" `
  -d '{"query":"how do the papers ground generated claims","top_k":3}'
```

The standard response must contain ordered PDF `sources`, exact passage `citations`, and only
markers present in that citation catalog. The stream must order events as
`sources -> delta* -> done|error`; clients must discard deltas if an `error` arrives.

The current 1B model mixed methods and results between papers even after stronger prose
instructions. Answers therefore use constrained evidence selection: the model chooses up to
three server-owned sentence IDs, and the server renders their original text as quotations
with their original passage markers. Each excerpt must match its cited passage, allowing
only whitespace normalization. The public response fields and complete citation evidence
are unchanged. This trades fluent synthesis for directly verifiable attribution; it does
not establish that a quotation is relevant or fairly represents the surrounding discussion.

Only papers whose retrieved evidence covers at least 60% of the question's non-stopword
terms are eligible. Matching uses a small English inflection normalizer. This conservative
lexical guard rejects obvious topic-only matches, such as weather mentions without the
requested location and forecast details; it is not a semantic relevance guarantee and may
abstain on questions phrased with synonyms. From each eligible passage, the best matching
whole sentence is offered to the model, weighting terms that are rarer within that passage
more highly. This keeps the 1B model's selection catalog small.

Sentences shorter than seven or longer than 55 whitespace-separated words are omitted,
never cut. If no usable sentences exist, or the model selects none, the answer is the fixed
insufficient-evidence message. Review potential loss of coverage on long or poorly extracted
sentences and on paraphrased questions as part of acceptance.

Acceptance verified on 2026-10-08 (Africa/Cairo): all eight live cases passed after
rebuilding only the API. BM25 `/ask` and `/stream` returned 84-word answers; hybrid returned
95-word answers. Targeted KBEVO and penalty-scoring answers were 77 and 61 words, and both
weather requests abstained. Every returned citation was checked against the stored source
chunk at its section/chunk coordinates, and selected excerpts were reviewed in context.
The running Gradio app produced six updates with an answer, paper links, evidence, and
locators. Automated checks: 357 passed, 32 integration tests skipped; Ruff, mypy, and
`git diff --check` passed. Corpus remains 58 papers, 57 chunkable, 2,775 chunks; the alias
still points to v2, and v1 remains at 1,221 documents. Local detailed evidence is saved in
`test_output/week5_verified_acceptance.json` and `test_output/week5_acceptance.md`.

If `/ask` reports `Generated answer failed grounding validation`, inspect
`rag_selection_validation_failed` or `rag_answer_validation_failed` in the API logs.
Diagnostics identify invalid IDs, repeated selections, excerpt mismatches, or excess length
without logging model text. An invalid selection retries once as plain IDs against the same
retrieved evidence and model, with identical validation. A second failure remains HTTP 502;
malformed structured output also fails closed. The retry adds up to one generation call.

`/stream` buffers the internal JSON selection, then emits complete validated excerpts as
`delta` events. It does not expose model IDs or raw JSON. Updates arrive per excerpt rather
than per model token. Invalid selections end in `error`, with no `done` event.

Both endpoints enforce a maximum of 200 whitespace-separated words, including standalone
citation markers. The stream checks the accumulated answer before emitting each delta.
Overlong answers fail closed; claims and citations are never blindly truncated. Normal
answers are also bounded by three excerpts of at most 55 words each.

API source is copied into its image. After changing RAG code, rebuild and restart that service:

```powershell
docker compose up -d --build api
```

Manually compare each excerpt with its cited passage and surrounding discussion as part of
acceptance. Check relevance, source identity, background versus contributions, and ablations
versus proposed methods. A matching quotation establishes attribution, not scientific truth
or complete coverage. Include an unrelated question that must report insufficient evidence.

Launch the UI with `uv run python gradio_launcher.py`, open http://localhost:7861, and verify
the model/category controls, real-time answer rendering, ordered paper links, and exact evidence locations.

Search for something one paper repeats constantly — `RAG` on this corpus — and check that
the page still spans several papers, that no paper returns more than three passages, and
that `matching_passages` exceeds the number returned for the dominant one. If a single
paper fills the page, the collapse is not being applied.

`took_ms` is OpenSearch's own timing, not the round trip. Measured on this corpus, once
the JVM and the embedding model are warm — the first few requests after `docker compose up`
are several times slower and mean nothing:

| Endpoint | Round trip |
| --- | --- |
| `/search/` | 25-40ms |
| `/search/chunks` | 25-50ms |
| `/search/hybrid` | 120-270ms |

Hybrid is the outlier because embedding the query on CPU costs 50-110ms on its own, and the
two candidate queries add 20-50ms each. Roughly 30ms of the keyword half is spent
highlighting fifty candidates that nothing displays — the page returns at most fifty, and
usually ten. Worth knowing before treating hybrid as a hot path.

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
