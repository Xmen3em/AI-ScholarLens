# Week 6 tracing, caching and monitoring — 2026-10-13

The subsequent approved [live acceptance](week6-live-acceptance.md) verified
real revision probes/caching and a full separate Langfuse backend/project/UI.
The historical resource decision below was resolved for **staged lab operation**
using idle WSL reclaim and bounded memory. Continuous concurrent RAG/Langfuse
activation remains unverified; the original API/image/key are preserved.

Scope: opt-in local controls, unchanged answer/selector policy, API access and
budgets. No activation/rebuild of the existing API, deployment, cloud telemetry,
ingestion, index/model changes, recovery replay, commits or pushes.

## Audit and resource decision

The six application containers are stopped, retaining the prior activated API
image (`808626dff29c`) and original mounts. Redis 7 Alpine is already installed;
Langfuse images and Python SDK/client were absent. Docker has 8,209,788,928 bytes
RAM; Windows reports about 710 MiB free. C: has 47.8 GiB free, D: 40.4 GiB.
The idle VM reports 6.7 GiB available; this does not represent headroom with
OpenSearch, Ollama, Airflow and Dashboards running.

Current [Langfuse Compose](https://langfuse.com/self-hosting/deployment/docker-compose)
uses web/worker, PostgreSQL, ClickHouse, Redis and object storage. Its VM guidance
recommends 4 cores/16 GiB RAM. Do not start that stack in this shared 8 GiB VM or
fall back to legacy v2 solely to save memory. Full UI/backend acceptance remains
pending capacity. Inspect the current SDK, isolate its tracer/exporter, and verify
the actual OTLP payload against a loopback receiver instead. No model execution
is needed for the deterministic request lifecycle checks.

## Questions and slices

1. Which request failed, and where did time go? Correlate server request ID,
   retrieval, generation attempts, validation/retry and complete SSE lifetime.
   Export explicit allowlisted metadata only; prohibit input/output, exception
   messages, keys, questions, evidence and answers. Bound queues, timeouts and
   shutdown. Verify disabled behavior, failures, concurrency, disconnects and
   actual serialized OpenTelemetry output before proceeding to caching. The
   inspected Langfuse Python 3.15 SDK starts unused media/score workers with
   100,000-entry queues. Use the documented native OTLP integration instead:
   isolated provider, 256 spans/queue, batches of 32, single-attempt 0.5 s HTTP
   export, no global instrumentation, proxies, redirects or cloud fallback.
2. Can an exact repeat avoid work safely? Redis stays disabled by default,
   after authentication and both budgets. Hash all effective request options,
   corpus/index revision, model digests, retrieval and evidence/answer policies.
   Require fresh read-only revision identity, validate cache content again, store only
   complete successful responses, and share ask/stream representation. Skip
   degraded retrieval, dependency failures and interrupted streams. Verify TTL,
   revision/policy/settings changes, unavailability and ask/stream parity using
   isolated Redis, never the unrelated `erp-redis` container.
   Revision probes hash every PostgreSQL paper field and schema revision, read
   aliases/mappings/settings, primary sequence numbers and searchable segment
   generations, and installed generation/embedding digests. Recheck identity on
   hits and writes; if unavailable or changed, bypass. No manual revision token
   or guessed identity is accepted. Cache keys and values use domain-separated
   HMAC with the existing API key. Redis stays volatile, bounded and local.
3. How often/how slow, including cache and quotas? Build local bounded JSON event
   files per worker and an offline monitoring report with p50/p95/p99, error/retry/
   validation/quota counts, actual Ollama tokens and duration, cache hit/miss and
   bypass/unavailability. Report usage, not hypothetical billed provider costs.

Run focused tests for each slice, then the repository suite, Ruff, mypy, Compose
validation and preservation comparison. Keep new evidence in
`test_output/week6-monitoring-20261013-01/`; never modify the frozen bundle.

## Sources reviewed

- [Course Week 6](https://github.com/jamwithai/production-agentic-rag-course#-week-6-production-monitoring-and-caching)
- [Langfuse SDK reference](https://python.reference.langfuse.com/langfuse)
- [Isolated providers and masking](https://langfuse.com/docs/observability/sdk/advanced-features)
- [Official Langfuse Compose source](https://github.com/langfuse/langfuse/blob/main/docker-compose.yml)
- [Redis Python connection guide](https://redis.io/docs/latest/develop/clients/redis-py/connect/)
- [Redis SET with expiry](https://redis.io/docs/latest/commands/set/)
