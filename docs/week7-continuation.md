# Continue application development after Week 6

Prepared 2026-10-13, Africa/Cairo. The user requested local commits for completed
Week 6 application work and context for another session to continue implementation.
They want further application development toward a future server release. Missing
backup hardware does not block local feature work. Deployment remains future work;
do not provision, publish, push, merge or cut over as setup.

Read `SESSION_HANDOFF.md` for current local state, then this document,
`tasks/plan.md`, `tasks/todo.md`, `docs/week6-local-activation.md` and
`docs/week6-observation.md`. Existing older statements saying no commits occurred
are historical; the new checkpoint section in the handoff identifies the commits.

## Completed baseline

The application has arXiv ingestion/PDF parsing, PostgreSQL storage, BM25/hybrid
search over grouped passages, validated cited answers, typed SSE and Gradio.
Week 6 adds opt-in signed exact-match Redis caching with live corpus/index/model
identity, TTL and unavailable-cache fallback; isolated metadata-only Langfuse OTLP
tracing; rotating per-worker event files and offline percentile/token/cache reports.
Authentication and unchanged global budgets run before cache access. SSE results
are stored only after complete delivery. Feature defaults remain off in source.

Verified pre-commit: **494 passed, zero skips**, including disposable Docker
PostgreSQL integration tests; mypy passed for 73 source files, changed-file Ruff,
base/cache-profile Compose and diff checks passed. The existing full-repository
import-order issue in `tests/api/test_operational_health.py` was not changed.
Pre-commit pytest emitted two dependency deprecations and an existing pytest-cache
ACL warning, but all tests passed. New evidence: `test_output/week6-commit-20261013-01/`.
Earlier mutation coverage detected a bypassed cache signature check; source restored.

Live one-worker API at `127.0.0.1:8000` and normal Gradio at
`127.0.0.1:7861` passed authentication, equal hit/miss quotas, quote/citation/SSE
parity, Redis fallback and browser checks. Eight controlled BM25 UI requests had
four real misses/stores and four hits, no failures/retries and matching outputs.
Hits took 263–579 ms; misses 7.2–16.5 s. Cold inference briefly left only 539 MiB
free Windows memory; this is not sustained-load, default-hybrid or quality acceptance.
The full Langfuse lab/backend/storage/UI passed separately using explicitly
historical metadata replay, not concurrently live RAG collection.

Answer-quality defects are open: irrelevant quotes on unsupported SF-GNN energy
questions, incomplete multi-paper coverage and tokenizer-related abstention.
All saved questions are inspected data. Use new development examples and a
separate fresh source-reviewed holdout for any behavioral optimization; do not
relabel old evaluations or treat cache correctness as answer-quality improvement.

## Reference and recommended implementation order

Reviewed [production-agentic-rag-course](https://github.com/jamwithai/production-agentic-rag-course)
and its [Week 7 release](https://github.com/jamwithai/production-agentic-rag-course/releases/tag/week7.0).
Week 7 covers LangGraph orchestration, query/domain validation, document relevance
grading, rewriting, adaptive retrieval and optional Telegram integration.
Adapt these ideas to this application's stronger evidence/operational boundaries.
Never execute reference reset commands that delete this project's volumes.

1. Audit the actual Week 7 node/workflow code and official current LangGraph docs.
   Write a short capability/acceptance specification before implementation. Inspect
   existing RAG/search/evidence boundaries and tests; do not clone over this project
   or replace the live image merely to follow the reference layout.
2. Implement a disabled-by-default agent path with mocked-service tests first,
   reusing existing search, local models and server-owned citation validation.
   Suggested sequence: validate question, retrieve, assess relevance, optionally
   rewrite once and retrieve again, then return a validated answer or abstain.
   Bound graph transitions, model calls, input/output sizes, deadlines and retrieval
   attempts; retries must not create unbounded loops or multiply hidden generation.
3. Preserve the existing `/ask` and `/stream` contracts and selector policy. A new
   agent endpoint must receive authentication and the SAME generation-budget
   protection before work; middleware currently classifies only those two original
   paths as generations, so explicitly test the new endpoint's classification.
   Define disabled behavior and cancellation/error paths. Expose short operation
   status events, retaining metadata-only diagnostics and validated-output ordering.
4. Keep the new path uncached until its identity/contract is defined. If adding
   caching, include agent policy/version, effective retrieval/rewrite controls and
   original request identity; do not reuse standard-answer entries across paths.
   Verify expiry, resource changes, failures and interrupted delivery again where
   new behavior introduces a distinct boundary.
5. Establish new evaluation data and compare the optional workflow against the
   unchanged baseline for relevance, coverage, abstention, latency and model calls.
   Preserve every existing evaluation and guard. Acceptance targets should be
   explicit before running fresh holdout evaluations. Enable only after evidence
   supports the new behavior and resource limits.
6. Build the research interface: expose existing paper browsing/detail/search APIs,
   clearer citation previews and source inspection; then saved searches/history and
   feedback. Define authentication/data ownership before retaining user-specific
   records. Telegram is optional follow-up; no bot token or outbound messaging is
   presently authorized or required to implement the agent backend.
7. Prepare a reproducible server configuration, HTTPS proxy, secret injection,
   appropriate user/replica quotas, automated build/check/release and rollback.
   Select host/model-serving resources from actual load and user/budget needs.
   Staging, off-machine backup/recovery and actual deployment are later gates.

This is continuation context, not a completed Week 7 implementation or permission
to loosen existing selector guards. Keep candidate default 1, output limits,
exact quotations, attribution and fail-closed validation. Routine isolated local
development can proceed; unsupported assumptions about server/user requirements
should be resolved before their dependent implementation.

## Runtime and preservation constraints

- Current branch at checkpoint: `master`. Preserve existing git state; use a
  `codex/` branch if creating a Week 7 feature branch. Commit authorization in the
  handoff checkpoint applies to this completed Week 6 work; do not infer push,
  merge or deployment authorization.
- Use `.venv-win/Scripts/python.exe` from PowerShell; Docker Desktop pipe access
  needs execution escalation. Check actual RAM before live generation. Avoid
  starting heavyweight services to run tests that can use mocks/small isolated
  fixtures; do not close user applications or alter system memory settings.
- The same five containers run: `rag-api`, `scholarlens-week6-cache`,
  `rag-postgres`, `rag-opensearch`, `rag-ollama`. Airflow, Dashboards, all Langfuse
  lab services and unrelated `erp-redis` remain stopped. Recheck status on resume.
- Active API image: `scholarlens-api:week6-local-20261013`,
  `sha256:c91c20ebe2ed71d7f433caff393d7eb0c18b1cbb046f2c7a094eb4d2f0b20c89`.
  Original complete API retained stopped as `rag-api-before-week6-20261013`, image
  `sha256:808626dff29c7bf0e222655fa9a0d6984f255b036d2ae5dddfe0bb1018514e11`.
  Preserve both, original key, dependency IDs/mounts/settings and rollback controls.
- The activated runtime uses explicit local containers and protected ignored
  runtime configuration; ordinary base Compose does not reproduce it and could
  disable features/recreate containers. Use documented controls, not a broad
  `compose up`, prune, volume deletion or reference reset.
- Read the API key privately through Settings; never print it or publish `.env`,
  test-output configurations, credentials, private answers or recovery archives.
  Preserve 58 papers, 58 paper documents, 1,221 v1 chunks, 2,775 v2 chunks and
  aliases, installed model files/digests and all inspected evaluations. No ingestion,
  reparse, reindex, model download/replacement or corpus mutation as setup.
- Frozen bundle `test_output/replacement-recovery-20261012-01/bundle/` remains
  unchanged: 233 manifest files, 8,970,337,129 bytes, original credentials and
  earlier verified runtime. It does not include these later Week 6 additions.
  All 304 protected baseline hashes previously matched. Off-machine destination
  and separate-machine access remain missing; transfer helpers are prepared in
  `test_output/week6-transfer-prep-20261013-01/`. Do not repeat the completed
  same-machine recovery drill. Missing hardware does not block feature development.

Evidence directories: `week6-monitoring-20261013-01`, `week6-live-20261013-01`,
`week6-local-activation-20261013-01`, `week6-observation-20261013-01`,
`week6-transfer-prep-20261013-01`, `week6-commit-20261013-01`, all under ignored
protected/local `test_output/`. Historical failures and their corrections remain.
