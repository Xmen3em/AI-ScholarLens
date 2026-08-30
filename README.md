# AI-ScholarLens

AI-ScholarLens is a research-paper ingestion and retrieval platform for arXiv papers. It is being built in phases: first the service foundation, then automated arXiv/PDF ingestion, followed by search, RAG answers, and evaluation.

The project is intentionally split into small replaceable components. The arXiv client, PDF parser, metadata pipeline, repository layer, and model client can evolve independently as later phases are completed.

## Current phase

| Phase | Capability | Status |
|---|---|---|
| Phase 1 | Docker foundation, FastAPI, PostgreSQL, OpenSearch, Ollama, and Airflow | Complete |
| Phase 2 | arXiv metadata, PDF download/cache, Docling parsing, PostgreSQL storage, and Airflow orchestration | Complete |
| Phase 3 | OpenSearch indexing and hybrid retrieval | In progress — chunk indexing complete, retrieval next |
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
        Search[(OpenSearch<br/>paper-chunks index)]
        Ollama[Ollama<br/>answers Phase 5]
    end

    Arxiv[(arXiv API)]
    PDF[(PDF cache)]
    Docling[Docling PDF parser]
    Retriever[Retriever / RAG service<br/>Phase 3–5]

    User --> API
    API --> DB
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
7. The DAG rewrites every stored paper into the `paper-chunks` OpenSearch index.
8. Retrieval endpoints and RAG answering are reserved for later phases.

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
| GET | /docs | Interactive OpenAPI documentation |

Example:

~~~powershell
Invoke-RestMethod http://localhost:8000/api/v1/ping
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod http://localhost:8000/api/v1/papers/
~~~

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
│   │   └── chunk_indexer.py     # Corpus -> OpenSearch chunk index
│   ├── repositories/            # Query logic (PaperRepository)
│   ├── models/                  # SQLAlchemy models
│   ├── schemas/                 # Pydantic contracts
│   ├── policies/                # AI category allowlist, chunk boundaries
│   ├── search/                  # OpenSearch index mapping and client
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
