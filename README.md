# AI-ScholarLens

AI-ScholarLens is a research-paper ingestion and retrieval platform for arXiv papers. It is being built in phases: first the service foundation, then automated arXiv/PDF ingestion, followed by search, RAG answers, and evaluation.

The project is intentionally split into small replaceable components. The arXiv client, PDF parser, metadata pipeline, repository layer, and model client can evolve independently as later phases are completed.

## Current phase

| Phase | Capability | Status |
|---|---|---|
| Phase 1 | Docker foundation, FastAPI, PostgreSQL, OpenSearch, Ollama, and Airflow | Complete |
| Phase 2 | arXiv metadata, PDF download/cache, Docling parsing, PostgreSQL storage, and Airflow orchestration | Complete |
| Phase 3 | OpenSearch indexing and hybrid retrieval | In progress — BM25 keyword search complete, dense vectors next |
| Phase 4 | Chunking and retrieval evaluation | Planned |
| Phase 5 | Grounded RAG answers with Ollama | Planned |
| Phase 6 | Production hardening: observability, security, and deployment | Planned |

Update this table and the diagrams when a phase is accepted. Keep unfinished work in the “Planned” or “In progress” rows instead of presenting it as an active runtime dependency.

## Architecture

### Runtime architecture

Solid edges are implemented in the current application. Dashed edges are reserved for later phases.

~~~mermaid
flowchart LR
    User[Researcher / Client]

    subgraph Runtime[Docker Compose runtime]
        API[FastAPI API<br/>:8000]
        Airflow[Airflow Scheduler + DAG<br/>:8080 or AIRFLOW_PORT]
        DB[(PostgreSQL<br/>papers + parsed content)]
        Search[(OpenSearch<br/>arxiv-papers + paper-chunks)]
        Ollama[Ollama<br/>answers Phase 5]
    end

    Arxiv[(arXiv API)]
    PDF[(PDF cache)]
    Docling[Docling PDF parser]
    Retriever[Retriever / RAG service<br/>Phase 3–5]

    User --> API
    API --> DB
    API -- BM25 search --> Search
    API -- health check --> Ollama

    Airflow --> Arxiv
    Airflow --> PDF
    PDF --> Docling
    Docling --> DB
    DB -- chunks --> Search
    Airflow --> DB

    DB -. index papers .-> Search
    Search -. retrieve context .-> Retriever
    DB -. retrieve metadata .-> Retriever
    Ollama -. generate answer .-> Retriever
    Retriever -. answer .-> API
~~~

### Paper-ingestion flow

~~~mermaid
sequenceDiagram
    participant S as Airflow DAG
    participant A as arXiv API
    participant M as MetadataFetcher
    participant C as PDF cache
    participant P as DoclingParser
    participant D as PostgreSQL

    S->>M: fetch_and_process_papers()
    M->>A: Fetch AI-category metadata
    A-->>M: Paper metadata
    M->>C: Download PDF if not cached
    C-->>M: Local PDF path
    M->>P: Parse PDF
    P-->>M: Sections and raw text
    M->>D: Upsert metadata and parsed content
    D-->>S: Processing counts and errors
~~~

The ingestion pipeline is designed to degrade gracefully: a failed PDF download or parse should be recorded while allowing other papers to continue through the batch.

### AI category scope

Ingestion covers eight core AI categories from [arXiv's taxonomy](https://arxiv.org/category_taxonomy):

| Category | Field |
| --- | --- |
| `cs.AI` | Artificial Intelligence |
| `cs.LG` | Machine Learning |
| `cs.CL` | Computation and Language |
| `cs.CV` | Computer Vision and Pattern Recognition |
| `cs.RO` | Robotics |
| `cs.MA` | Multiagent Systems |
| `cs.NE` | Neural and Evolutionary Computing |
| `stat.ML` | Machine Learning (Statistics) |

A paper qualifies when **any** of its arXiv categories is in that list, so cross-listed work counts: a
paper tagged `["quant-ph", "cs.LG"]` is ingested. Adjacent fields such as information retrieval, HCI,
speech, and signal processing are excluded unless they are cross-listed into an allowlisted category.

The scope is a code constant in `src/policies/ai_scope.py`, not a setting, so no deployment
configuration can widen ingestion beyond it. It is enforced twice: the arXiv query asks only for these
categories, and `MetadataFetcher` re-checks every fetched paper before any PDF is downloaded, parsed,
or stored.

To check the stored corpus against the allowlist, see [Corpus scope audit](#corpus-scope-audit).

### Search

Two OpenSearch indices, for two different questions.

| Index | Document | Answers |
| --- | --- | --- |
| `arxiv-papers` | one per paper | "which papers are about X" |
| `paper-chunks` | one per passage | "which passage says X" |

One index cannot do both. BM25 normalizes relevance by field length, so in a
paper-sized document the passage that actually matched is buried, and a passage-sized
document has no title or abstract to weight.

Both are rewritten in full by the `index_to_opensearch` DAG task and both go through an
alias, so a mapping change can be rolled out by building the next index and repointing.

Both endpoints share one query builder, differing only in a profile: which fields are
searched and with what boost, which are returned, and how they are highlighted. The
matching rules — `best_fields`, fuzziness, the filter clause, `track_total_hits` — are
the same for both, and a test asserts they stay that way.

#### Ranking papers

`POST /api/v1/search/` scores matches across three fields, weighted:

| Field | Boost | Why |
| --- | --- | --- |
| `title` | 3x | The strongest signal a paper *is about* the query |
| `abstract` | 2x | The author's own summary of it |
| `authors` | 1x | Searching by name, which a fuzzy text match would otherwise rank below an incidental mention |

The query is a `best_fields` multi-match, so a paper whose title alone matches the whole
query beats one that spreads the terms across three fields — which is the only way a 3x
title boost means anything. `fuzziness: AUTO` with `prefix_length: 2` absorbs typos
("retreival augmnted generaton" finds the RAG papers) while keeping the first two
characters exact, so short queries do not match half the vocabulary. Titles and
abstracts are stemmed with snowball; author names are only lowercased, because stemming
a surname produces something no query spells.

Results carry `<mark>`-wrapped highlights — whole field for titles and authors,
fragments for abstracts — and `took_ms` from OpenSearch. Category filtering is a `filter`
clause rather than a query clause, so a category never contributes to relevance. An
empty query browses: filters and the newest-first sort still apply, which is how "the
latest cs.CL papers" is asked for.

#### Ranking passages

`POST /api/v1/search/chunks` scores the passage text at 3x and its section heading at 2x.

The paper title is deliberately **not** scored. Every passage of a paper carries the same
title, so boosting it returns forty pieces of one paper instead of the best passage from
each — measured on this corpus, six results collapsed to a single distinct paper. The
section heading earns its 2x: it lifts "F LIMITATIONS AND FUTURE WORK" into the top three
for "limitations and future work", which the passage text alone ranked fifth.

Each hit carries `section_index` and `chunk_index` alongside the `arxiv_id`, so a quoted
passage can always be traced back to where in the paper it came from.

### Search chunks

Parsed papers are split into retrievable chunks and written to the `paper-chunks`
OpenSearch index by the `index_paper_chunks` DAG task. The rules live in
`src/policies/chunking.py`:

- **The unit is a section.** Docling already recovers the paper's own structure, so a
  section is a real boundary rather than a blind split. A section longer than 2000
  characters is split further at the last paragraph, line, or sentence boundary that
  fits, with 200 characters of overlap so a passage cut mid-argument stays recoverable.
- **Reference lists are excluded.** A bibliography is a list of other people's titles:
  indexed as body text it matches almost any query and grounds nothing. It is the
  largest section in the corpus — 26 of 26 parsed papers, 234k of 1.8M characters. The
  text stays in `papers.sections` for whoever extracts citations later.
- **Sections under 100 characters are dropped.** Measured on the live corpus, all 48 of
  them were arXiv stamp lines, author affiliation blocks, or bare link captions.
- **Chunk ids are positional** (`{arxiv_id}:{section_index}:{chunk_index}`), so
  re-indexing a paper overwrites its chunks instead of duplicating them.

Each pass rewrites the whole corpus, then deletes any chunk it did not rewrite — which
covers both a paper re-parsed into fewer sections and a paper purged from the database.
That cleanup is skipped when any paper failed to index, so a transient failure cannot
delete chunks that are still good.

Writes and reads both go through the `paper-chunks` alias, which points at
`paper-chunks-v1`. An OpenSearch mapping cannot be changed in place, so a field-type
change means building the next index and repointing the alias — and an alias cannot
share a name with an existing index, so it has to exist from the first write.

## How the application works today

1. The API starts, connects to PostgreSQL, and brings the schema to the latest migration.
2. The API exposes health, ping, and paper read endpoints.
3. Airflow schedules the arxiv_paper_ingestion DAG for weekdays at 06:00 UTC. Airflow creates DAGs paused, so it runs only after the DAG is unpaused or triggered manually.
4. The DAG fetches metadata from arXiv across the eight allowlisted AI categories.
5. PDFs are downloaded and cached, then parsed with Docling inside the Airflow image.
6. Paper metadata and parsed content are upserted into PostgreSQL.
7. The DAG rewrites every stored paper into both OpenSearch indices.
8. `POST /api/v1/search/` ranks papers with BM25 over the `arxiv-papers` index.
9. Dense retrieval and RAG answering are reserved for later phases.

The API image does not initialize Docling. PDF parsing belongs to the Airflow image, which contains the heavier PDF-processing dependencies.

The two images run `src/` under different SQLAlchemy majors: the API installs SQLAlchemy 2.x from `pyproject.toml`, while the Airflow image pins `>=1.4.36,<2.0.0` because Airflow 2.10 does not support SQLAlchemy 2.x. Shared code under `src/` must stay inside the compatible subset — declare columns with `Column()` rather than `Mapped[]`/`mapped_column()`, and import `declarative_base` from `sqlalchemy.orm`.

## Quick start

### Prerequisites

- Docker Desktop
- Python 3.12
- PowerShell on Windows, or an equivalent shell
- At least one available host port for each exposed service

Start the stack from the repository root:

~~~powershell
docker compose up --build -d
~~~

If host port 8080 is already in use, select another Airflow host port:

~~~powershell
$env:AIRFLOW_PORT = "8081"
docker compose up -d
~~~

Check the containers:

~~~powershell
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 airflow
~~~

Airflow creates new DAGs in a paused state. Unpause the ingestion DAG before expecting it to run on schedule:

~~~powershell
docker compose exec airflow airflow dags unpause arxiv_paper_ingestion
~~~

The API documentation is available at http://localhost:8000/docs. Airflow is available at http://localhost:8080, or at the configured AIRFLOW_PORT. The default Airflow credentials are admin/admin.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /api/v1/ping | Basic API connectivity check |
| GET | /api/v1/health | API, database, and Ollama health information |
| GET | /api/v1/papers/ | List stored papers with pagination |
| GET | /api/v1/papers/{arxiv_id} | Retrieve one stored paper |
| POST | /api/v1/search/ | BM25 keyword search over papers |
| POST | /api/v1/search/chunks | BM25 keyword search over passages |
| GET | /docs | Interactive OpenAPI documentation |

Example:

~~~powershell
Invoke-RestMethod http://localhost:8000/api/v1/ping
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod http://localhost:8000/api/v1/papers/

# Relevance-ranked search
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/search/ -ContentType application/json `
  -Body '{"query": "retrieval augmented generation", "size": 5}'

# The newest cs.CL papers, no query term
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/search/ -ContentType application/json `
  -Body '{"query": "", "categories": ["cs.CL"], "newest_first": true}'

# The passages that answer a question, not the papers that mention it
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/search/chunks -ContentType application/json `
  -Body '{"query": "how are the benchmarks constructed", "size": 5}'
~~~

`size` is 1-50, `offset` 0-1000, and `categories` must be inside the ingested AI
allowlist — a filter on `hep-th` is a 422 rather than a silent zero-result page, because
the corpus can never contain one. `/search/` accepts an empty query and browses;
`/search/chunks` requires one, because a passage is only meaningful as an answer to
something.

## Testing

Run the deterministic local test suite:

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
~~~

The automated tests cover settings, schemas, arXiv parsing and caching, Ollama client behavior, API routes, ingestion pipeline accounting, and the Airflow-to-metadata pipeline contract. `tests/integration/` additionally runs `PaperRepository` against a real PostgreSQL container when Docker is available, and skips when it is not.

For Docker service checks, database verification, Airflow DAG checks, PDF processing, and the complete ingestion test, see [TESTING.md](TESTING.md).

## Useful commands

| Command | Purpose |
|---|---|
| docker compose up --build -d | Build and start the full stack |
| docker compose ps | Show service status |
| docker compose logs -f api | Follow API logs |
| docker compose logs -f airflow | Follow Airflow logs |
| docker compose exec airflow airflow dags list | List Airflow DAGs |
| docker compose exec airflow airflow dags list-import-errors | Check DAG import errors |
| docker compose exec airflow airflow dags unpause arxiv_paper_ingestion | Enable the scheduled DAG |
| docker compose exec airflow airflow dags trigger arxiv_paper_ingestion | Trigger ingestion manually |
| docker compose exec postgres psql -U rag_user -d rag_db | Open a PostgreSQL shell |
| docker compose down | Stop containers and preserve volumes |
| docker compose down -v | Stop containers and delete volumes |

Use docker compose down -v only when existing local data can be discarded or the schema needs a clean rebuild. It also clears the cached arXiv PDFs and Docling's model weights, so the next ingestion run re-downloads them.

## Repository layout

~~~text
AI-ScholarLens/
├── airflow/
│   ├── dags/
│   │   ├── arxiv_paper_ingestion.py
│   │   └── arxiv_ingestion/tasks.py
│   ├── Dockerfile
│   └── requirements-airflow.txt
├── src/
│   ├── main.py                  # FastAPI app, lifespan, router wiring
│   ├── config.py                # Settings loaded from environment
│   ├── dependencies.py          # FastAPI dependency injection
│   ├── exceptions.py            # Domain exception hierarchy
│   ├── routers/                 # FastAPI endpoints
│   ├── services/
│   │   ├── arxiv/               # arXiv client
│   │   ├── ollama/              # Ollama client
│   │   ├── pdf_parser/          # Docling parser
│   │   ├── metadata_fetcher.py  # Ingestion orchestration
│   │   ├── reindex.py           # Idempotent full-corpus reindex, shared
│   │   ├── paper_indexer.py     # Corpus -> arxiv-papers index
│   │   ├── chunk_indexer.py     # Corpus -> paper-chunks index
│   │   └── paper_search.py      # BM25 search over arxiv-papers
│   ├── repositories/            # Query logic (PaperRepository)
│   ├── models/                  # SQLAlchemy models
│   ├── schemas/                 # Pydantic contracts
│   ├── policies/                # AI category allowlist, chunk boundaries
│   ├── search/                  # Index mappings, query builder, client
│   ├── commands/                # Operational CLIs (python -m src.commands.*)
│   └── db/                      # Database interface, PostgreSQL impl, factory
│       ├── migrations.py        # Startup migration runner
│       └── alembic/             # Alembic env and versions/
├── tests/
│   ├── api/
│   ├── integration/
│   └── unit/
├── compose.yml
├── Dockerfile
├── pyproject.toml
├── uv.lock
├── TESTING.md
└── README.md
~~~

## Phase update process

At the end of each phase:

1. Update the phase table and mark only verified capabilities as complete.
2. Move newly implemented diagram nodes from dashed to solid edges.
3. Add the phase's automated and Docker-backed acceptance checks to TESTING.md.
4. Update the “How the application works today” section.
5. Record major architectural decisions in an ADR if a component boundary or technology choice changes.

This keeps the README useful to both developers and future agents without requiring a complete rewrite after every phase.

## Configuration

Copy `.env.example` to `.env` and adjust:

~~~bash
cp .env.example .env
~~~

`.env.example` lists every setting with its in-code default, so an empty `.env` is a working
one. Docker Compose does not read `.env` — it sets the container environment inline in
`compose.yml` — so `.env` matters when running the API or tooling on the host.

Runtime settings are loaded from environment variables and .env through src/config.py. Important settings include:

- POSTGRES_DATABASE_URL
- OPENSEARCH_HOST
- OLLAMA_HOST
- ARXIV__MAX_RESULTS — papers per ingestion run, counted across all eight AI categories combined
  rather than per category. Defaults to 10, which compose.yml also sets explicitly for Airflow.
- arXiv rate-limit, timeout, and cache settings
- PDF page-size and file-size limits

The set of arXiv categories is deliberately **not** configurable; it lives in
`src/policies/ai_scope.py`. `ARXIV__SEARCH_CATEGORY` has been removed, and any leftover entry for it
in a local `.env` is ignored.

Do not commit credentials or private environment files.

## Database migrations

The schema is owned by Alembic, in `src/db/alembic/versions/`. `PostgreSQLDatabase.startup()`
runs `alembic upgrade head`, so both the API and the Airflow DAG converge on the same schema
without a manual step. A PostgreSQL advisory lock serialises them, since both call
`make_database()`.

This replaced `Base.metadata.create_all`, which only ever created *missing tables*. It never
altered an existing one, so any new column silently failed to reach a deployed database.

A database created before migrations existed is detected (schema present, no history) and
stamped at `0001_papers_baseline` before newer revisions run, so no manual `alembic stamp` is
needed and existing rows are untouched.

After changing a model:

~~~bash
make migration m="add citation_count to papers"   # autogenerate
# review the generated file in src/db/alembic/versions/ before committing
make migrate                                       # apply locally
~~~

Two constraints are load-bearing, both in `src/db/alembic/env.py`:

- **The version table is `alembic_version_scholarlens`, not `alembic_version`.** Compose points
  Airflow at the same `rag_db`, and Airflow runs Alembic itself — sharing the default table
  would interleave two unrelated migration histories.
- **`include_name` limits autogenerate to this project's tables.** Without it, autogenerate
  compares against a database full of Airflow's tables and emits `drop_table()` for every one
  of them, including Airflow's own `alembic_version`.

## Corpus scope audit

`python -m src.commands.ai_scope` checks stored papers against the AI allowlist and removes any that
predate it.

~~~bash
# Read-only report of scanned, compliant, and non-compliant rows
docker compose exec airflow python -m src.commands.ai_scope audit

# Exit non-zero when anything is out of scope (for scripting)
docker compose exec airflow python -m src.commands.ai_scope audit --fail-on-violation

# Rehearse a cleanup; writes nothing without --apply
docker compose exec airflow python -m src.commands.ai_scope purge --expected-count 3

# Delete, having reviewed the audit above
docker compose exec airflow python -m src.commands.ai_scope purge --expected-count 3 --apply
~~~

`purge` is a dry run unless `--apply` is passed, and `--apply` requires `--expected-count N`. If the
number of non-compliant rows no longer matches `N`, the command aborts without deleting anything, so a
stale audit can never authorise a deletion. Deletion is permanent — back the table up first:

~~~bash
docker compose exec postgres pg_dump -U rag_user -d rag_db -t papers > papers_backup.sql
~~~

Add `--json` to either subcommand for machine-readable output on stdout; logs stay on stderr.

## License

This project is currently under active development. Add the project license here when it is selected.
