# Week 6: local operational controls

Approved scope: audit existing controls, implement gaps, and verify locally.
Deployment, selector tuning, ingestion, corpus/index changes, model changes,
commits and pushes are excluded. Existing source/evaluation artifacts are retained.

## Audit before implementation (2026-10-08, Africa/Cairo)

| Area | Existing evidence | Missing control / action |
| --- | --- | --- |
| Observability | `RAGService.prepare`, generation timing/token counts, selection/answer validation diagnostics; SSE error event | Registered request middleware with correlation and full response duration; structured selector/stream diagnostics without provider text |
| Access and limits | Request schemas, model allowlist, bounded generation/retry/output; outbound arXiv delay | API key protection, fail-closed non-development config, shared worker-safe request/generation limits |
| Configuration and health | Compose dependency/container probes, named volumes, PostgreSQL SELECT 1, Ollama required/optional model readiness | OpenSearch cluster and read-alias readiness; bounded probes; loopback host bindings; key/limit configuration wiring |
| Recovery | Persistent PostgreSQL/search/PDF/model volumes, one table-dump example | Binary-safe full database backup and empty-target restore drill with content fingerprints; explicit index/PDF/model recovery procedure |

Questions telemetry must answer: which request failed, was it selector or stream
failure, how long did the complete response take, and were requests rejected before
expensive retrieval/generation? JSON events and request IDs answer these locally.

## Decisions and verification

1. Add safe JSON request events via pure ASGI middleware so stream lifetime is
   measured. Preserve RAG selection, candidates, prompts and validation behavior.
2. Use an optional development API key (required outside development/test), with
   only liveness public when configured. Use SQLite transactions for two global
   fixed-window budgets shared across the image's four workers; no Redis service
   required. This limits one local instance, not multiple replicas.
3. Retain existing health checks and add OpenSearch cluster/read aliases. Treat
   yellow single-node health as usable; missing aliases/red/unreachable are 503.
   Bind published ports to loopback in the local configuration.
4. Add backup/restore commands that never overwrite an existing target. Verify a
   full dump against an isolated scratch database, including all paper fields.
   Preserve existing corpus, both chunk indexes/alias and installed models.

Each slice gets focused failure/success tests, followed by full pytest, Ruff,
mypy, Compose validation and a local runtime check. Recovery artifacts stay in
ignored `test_output/`. No external deployment or cloud telemetry is involved.

## Course reference

Reviewed [production-agentic-rag-course Week 6](https://github.com/jamwithai/production-agentic-rag-course#-week-6-production-monitoring-and-caching)
on 2026-10-08. Its Week 6 teaches Langfuse traces, Redis exact-match caching,
TTL/key design, latency/token/cost monitoring and graceful cache fallback.
This repository already logs retrieval/generation timings and token counts.
This pass fills the user's four operational gaps with local controls. Langfuse,
Redis caching, dashboards and distributed tracing remain optional future work;
they are not claimed as implemented or required for these controls. Caching needs
corpus/model/policy-aware invalidation and separate quality verification.

## Answer-quality work remains open

The completed [selector report](../evaluation/selector_reliability/REPORT.md)
records 80/80 successful answer attempts and 40/40 identical endpoint pairs,
but the final seven-question holdout abstained on only 4/8 unsupported attempts:
SF-GNN energy-cost requests still received irrelevant quotations. Two-paper
fact coverage was BM25 0/2, hybrid 1/2 per endpoint. Inspected regression coverage
was 58.3%/50%, below the original array's 75%/66.7%. Multi-tokenizer false
abstention persists. Technical reliability does not establish answer quality.
Further tuning requires separate development examples and another fresh,
source-reviewed holdout; all saved questions are inspected data.
