# Week 7 bounded agent: audit and acceptance specification

2026-10-13, Africa/Cairo. Baseline: `a597f23`. Source-only development is
authorized; activation, deployment, push, merge and selector tuning are excluded.

## Reference audit

The course `week7.0` resolves to `d185d9b45d5ee02b7c11ac8f868597448c31cd34`.
Read the actual [workflow](https://github.com/jamwithai/production-agentic-rag-course/blob/d185d9b45d5ee02b7c11ac8f868597448c31cd34/src/services/agents/agentic_rag.py),
[nodes](https://github.com/jamwithai/production-agentic-rag-course/tree/d185d9b45d5ee02b7c11ac8f868597448c31cd34/src/services/agents/nodes),
[configuration](https://github.com/jamwithai/production-agentic-rag-course/blob/d185d9b45d5ee02b7c11ac8f868597448c31cd34/src/services/agents/config.py)
and [route](https://github.com/jamwithai/production-agentic-rag-course/blob/d185d9b45d5ee02b7c11ac8f868597448c31cd34/src/routers/agentic_ask.py).

| Reference capability / finding | Local decision |
| --- | --- |
| StateGraph, runtime context, conditional routing, ToolNode retrieval | Adapt the finite stages using existing async services; no dependency/lockfile changes or arbitrary tool calls |
| Model scope score, threshold 60; absent guardrail continues | Strict boolean domain decision; missing/malformed output fails closed |
| Two retrieval attempts, rewriting after failed grading | Two retrievals and one rewrite; no rewrite after second unsuccessful grade |
| Grading failure falls back to context length greater than 50 | Reject invalid grading; accept only unique known server-owned markers |
| Rewriter failure appends generic keywords | Reject invalid rewrite; unchanged rewrite abstains |
| Generation uses latest query and free-form model prose | Grade/select against original question; reuse existing excerpt, schema, rendering and grounding helpers |
| Query/context previews, reasons and answers enter logging/tracing | Fixed operation labels, counts, timings and error types only |
| Route forwards only query despite request controls | Forward model, top-k, mode and category controls; preserve actual fallback mode |
| Telegram, feedback, graph visualization | Later scope; no bot, outbound messages, identity/history store or visualization service |

Official [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
documents state, nodes, edges and conditional routing. Recursion limits bound graph
steps, not provider calls or elapsed time; private channels can still appear in
state streams. This implementation uses an explicit finite workflow instead of
installing LangGraph: no persistence/resume, fan-out or open tool selection is
needed. Budgets and public event filtering remain application responsibilities.

## Contract and success criteria

- Add `POST /api/v1/agent/ask` and `/api/v1/agent/stream`, accepting the unchanged
  AskRequest. `AGENT_ENABLED=false` by default. Disabled authenticated requests
  return 503 before retrieval/model/cache work. Authentication and the same global
  generation quota precede both routes, including disabled attempts. One request
  reserves one generation slot; the explicit six-call ceiling bounds its work.
- Sequence: domain validation -> retrieve -> relevance grade -> optional rewrite
  -> retrieve -> grade -> validated selection or fixed abstention. Scope rejection
  returns fixed abstention with outcome `out_of_scope`, no evidence. No evidence
  after refinement returns `abstained`. Provider/invalid-output failures are errors,
  never evidence success. No model-generated reasoning is returned.
- Hard ceilings: eight operation stages, two retrievals, one rewrite, six model
  generation calls (scope + two grades + rewrite + up to two existing selector attempts).
  Response `model_calls` counts generation; existing hybrid search can additionally
  make one query-embedding call per retrieval (up to two, eight inference requests
  overall). BM25 makes no embedding calls. There are no embedding retries.
  No controller retries. Query/rewrite <=500 characters, top-k <=10, at most 30
  context citations, 12,000 evidence characters, prompts <=20,000 characters,
  controller outputs <=4,096 characters and selector outputs <=8,192 characters.
  Controllers use temperature zero and <=256 output tokens; selector options and
  candidate policy remain unchanged (default one candidate, max three IDs,
  exact quotation attribution and <=200 answer words).
- `AGENT_DEADLINE_SECONDS=90` (1..120) and
  `AGENT_NODE_TIMEOUT_SECONDS=30` (1..60). Timeout maps to 504 for JSON;
  cancellation propagates. Search runs off-loop with cancellable waiting and at
  most one outstanding synchronous agent search per worker. An abandoned read
  may finish under existing backend transport timeouts; Python cannot kill that
  thread or guarantee a remote Ollama computation stops when HTTP is cancelled.
- Agent response extends AskResponse with policy version, outcome, retrieval and
  model-call counts, rewritten boolean and bounded operation steps. Original query
  stays the answer identity. Rewriting changes only retrieval text. Grading filters
  citations without replacing evidence or renumbering markers.
- SSE: fixed `status` operations, then validated `sources -> delta* -> done`, or
  generic `error`. No answer/citation events before selection validation succeeds.
  No raw model IDs, rewritten queries or graph state in status events. Failed or
  disconnected streams cannot store anything. Agent paths always bypass caching.
- Existing ask/stream, selector files, evaluations, keys, corpus/index/model files,
  live/rollback containers and frozen recovery bundle remain preserved.

## Implementation and verification

Python 3.12, existing FastAPI/Pydantic/AnyIO/Ollama services. New contracts in
`src/schemas/api/agent.py`, finite workflow in `src/services/agent.py`, routes in
`src/routers/agent.py`. Minimal settings/router/quota integration only.
Use typed models, explicit counters and async functions, matching repository style:
`async def ask(self, request: AskRequest) -> AgentResponse`.

Build slices: (1) tests and finite service, (2) route/quota/SSE boundary tests and
integration, (3) regression/type/lint verification and continuation documentation.
Write failing tests first. Mock only search/model boundaries using synthetic new
examples; run actual validation, ASGI, HTTP transport and temporary quota stores.
Cover scope denial, direct/refined answers, exhausted/empty retrieval, malformed/
duplicate/unknown grading, invalid/unchanged rewrite, selector retry/rejection,
size ceilings, deadlines, cancellation at each stage, concurrent search occupancy,
mode/control forwarding, cache bypass, auth/quota before work and event ordering.

```powershell
.venv-win/Scripts/python.exe -m pytest tests/unit/test_agent_service.py tests/api/test_agent_routes.py -q
.venv-win/Scripts/python.exe -m pytest -q
.venv-win/Scripts/python.exe -m mypy src
.venv-win/Scripts/python.exe -m ruff check src/services/agent.py src/schemas/api/agent.py src/routers/agent.py src/main.py src/middlewares.py src/config.py tests/unit/test_agent_service.py tests/api/test_agent_routes.py
git diff --check
```

Always preserve guards and run checks; keep private artifacts ignored. Do not
activate services, change dependencies, ingest/reindex, replace/download models,
tune selectors, mutate old evaluations or refresh the frozen bundle in this work.

## Later acceptance and roadmap

These isolated tests establish bounded execution and evidence integrity, not an
answer-quality improvement. Before enabling: collect separate new development
examples and freeze a fresh source-reviewed holdout, including paraphrases,
multi-paper/numeric questions, unsupported and out-of-domain negatives. Compare
against unchanged baseline in both retrieval modes for relevance, fact coverage,
abstention, errors, p50/p95 latency and model calls. Require zero attribution/word/
budget breaches, no unsupported answers, and no relevance/coverage regression;
report sample sizes and uncertainty. Measure sustained and cold-model RAM before
setting live latency/concurrency targets; do not fabricate those targets here.

Next research-interface work exposes existing browse/detail/search APIs and citation
previews/source inspection. Saved searches/history/feedback depend on identity and
record ownership requirements. Server preparation follows with reproducible config,
HTTPS proxy, secret injection, user/replica quotas, build/check/release/rollback and
resource sizing. Off-machine backup and separate-machine recovery remain release
gates; missing hardware does not block this feature. No deployment is authorized.
