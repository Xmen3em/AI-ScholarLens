# Airflow

Orchestration for the arXiv ingestion pipeline. The Airflow service is defined in the
project's `compose.yml`; `make start` brings it up at http://localhost:8080 with the
admin/admin account that `entrypoint.sh` creates.

## Layout

```
airflow/
├── Dockerfile                  # Airflow 2.10.3 + Docling and its native dependencies
├── entrypoint.sh               # airflow db init, admin user, webserver + scheduler
├── requirements-airflow.txt    # Project dependencies for this image
└── dags/
    ├── arxiv_paper_ingestion.py    # DAG definition and task wiring
    ├── arxiv_ingestion/
    │   └── tasks.py                # The task callables
    └── hello_world_dag.py          # Connectivity check
```

The application code is not copied into the image — `compose.yml` bind-mounts `./src`
to `/opt/airflow/src`, and `tasks.py` puts `/opt/airflow` on `sys.path` so it can
`import src.*`. Editing `src/` therefore affects the next DAG run without a rebuild.

## arxiv_paper_ingestion

Runs weekdays at 06:00 UTC (`0 6 * * 1-5`), one run at a time, no catchup. Airflow
creates DAGs paused, so it only runs after being unpaused or triggered.

```
setup_environment
  └─> fetch_daily_papers
        ├─> process_failed_pdfs ─┐
        └─> index_paper_chunks ─────────┴─> generate_daily_report ─> cleanup_temp_files
```

Each run fetches the previous day's submissions across the eight AI categories fixed in
`src/policies/ai_scope.py`, capped by `ARXIV__MAX_RESULTS` (10 in `compose.yml`) as a
total across all of them. `index_paper_chunks` then rewrites the whole corpus into the
`paper-chunks` OpenSearch index: the pass is idempotent, so it also heals a partial run
and picks up papers parsed before indexing existed.

## Two constraints worth knowing

**SQLAlchemy 1.4.** Airflow 2.10 does not support SQLAlchemy 2.x, while the API image
installs 2.x from `pyproject.toml`. Shared code under `src/` must stay inside the
overlap: declare columns with `Column()` rather than `Mapped[]`/`mapped_column()`, import
`declarative_base` from `sqlalchemy.orm`, and avoid 2.0-only names such as `sa.UUID`.

**One database, two Alembic histories.** Compose points Airflow's metadata database and
the application at the same `rag_db`. Airflow owns the `alembic_version` table; the
application's migrations use `alembic_version_scholarlens` and restrict autogenerate to
their own tables. See the migrations section of the root README before touching
`src/db/alembic/env.py`.

Docling and its native dependencies exist only in this image, which is why PDF parsing
belongs to the DAG rather than the API.
