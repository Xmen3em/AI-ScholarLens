# Disabled HF generation adapter: source checkpoint

Implemented 2026-10-13 after approval of the [hosted inference plan](hf-inference-research-plan.md).
Tasks HF-1 through HF-4 are implemented with isolated synthetic verification.
**Hosted generation and the agent remain disabled in defaults. No real HF
inference ran.** The retained API still runs the Week 6 image; this work is not
deployed or activated.

## Implementation

`src/schemas/generation.py` defines a provider-neutral result and retained caller
port. Its projection preserves real token counts and leaves unknown usage and
Ollama-specific durations `None`. Reasoning-token counts are available to a future
hosted collector through the neutral result, without adding public API fields.

`src/services/hf/client.py` uses existing async HTTPX and the fixed HTTPS HF router.
Requests contain a pinned model/provider, unchanged JSON schema with `strict=true`,
temperature zero, the original 256/512 completion limit and low reasoning effort.
The initial registry contains `openai/gpt-oss-120b:groq` and
`openai/gpt-oss-120b:fireworks-ai`; the configured default allowlist contains only
Groq. These are **candidates**, not live-qualified pairs. Automatic policies,
arbitrary URLs/providers, Cerebras and richer reasoning models are rejected.
Qwen/Kimi/GLM profiles require later provider-specific contract qualification.

`src/services/hf/rag.py` overrides model resolution and inherits the original
retrieval, selection, rendering and validation. The base RAG file changes only
its generation import/type boundary; all 15 other function blocks match `a597f23`.
The narrow legacy response/error projection preserves current route and selector
semantics. Local embedding/search services, prompts and vectors are unchanged.

Source lifespan selects hosted generation only when enabled, retains Ollama for
embeddings, skips hosted cache construction and closes both clients on normal or
exceptional shutdown. Default startup retains the local RAG/cache factory. API
key protection, shared quotas, JSON/SSE contracts and the bounded agent remain
in use; answers are rendered from validated excerpts. Monitoring accepts only
registered model/provider identity, status, duration and outcome, without provider
bodies, questions, credentials or reasoning text.

Implementation references: [HF chat contract](https://huggingface.co/docs/inference-providers/tasks/chat-completion),
[HTTPX async response lifecycle](https://www.python-httpx.org/async/).

## Bounds and failures

The client makes one outbound attempt per call, without client retries, redirects,
environment proxies, tool execution, provider fallback or schema-mode downgrade.
Each worker admits one HF call at a time and rejects overlap; this is not a
distributed limit. The future collection profile must use one worker/request
until wider concurrency has separately measured acceptance.

The whole local attempt, including body read, has a 1–30 second deadline, default
30 seconds. The agent retains its independent 90-second overall/30-second stage
deadlines, two retrievals, one rewrite, six generations and eight stages.
Cancellation closes the local response and releases capacity; remote computation
or billing may continue after disconnect.

Response limits: 65,536 decoded bytes and 8,192 content characters. Exactly one
assistant choice, integer index zero and `finish_reason=stop` are required.
Malformed/duplicate envelope fields, whitespace/reasoning-only output, unexpected
tools/refusals, truncated completion and invalid/over-limit token counts fail
closed. Unknown envelope metadata is ignored. Application validators still check
the content's semantics and evidence identity.

Input admission is conservative for the registered byte-tokenized GPT-OSS model:
UTF-8 bytes of the full serialized request, **including the original schema**,
must fit `8192 - completion_limit - 512`. The reserve allows template overhead;
returned prompt/completion counts are checked too. This is not an exact provider
tokenizer or proof of all internal provider work. Missing usage remains unknown
and cannot establish token-budget acceptance. The 20,000-character prompt bound
also remains. Ollama's `num_ctx` feeds admission and is not sent to the HF API.

This stricter hosted profile can reject otherwise valid requests before inference.
The original 30-ID regex alone is 9,303 characters and cannot fit; its test verifies
**zero outbound calls**, without removing constraints or falling back. Patterns
for 1 and 10 IDs are forwarded unchanged. Input-admission failures use the generic
generation-unavailable API error. HF-5 must account for them and cannot claim full
request-range parity. Revising this admission requires a separate explicit profile;
the existing selector policy remains fixed.

Status/transport/timeout/invalid-envelope failures map to the existing generic
503/504/502 contracts, without provider error text. The existing one plain-ID
retry for invalid selected outputs remains; provider schema/transport failures
do not trigger a hidden retry/downgrade. A pinned request pair identifies routing,
not a cryptographically verified served weights revision. Saved Hub revisions
provide provenance, not proof of provider serving artifacts.

## Configuration and readiness

Example/test environment defaults:

```dotenv
HF_INFERENCE_ENABLED=false
HF_TOKEN=
HF_MODELS=openai/gpt-oss-120b:groq
HF_DEFAULT_MODEL=openai/gpt-oss-120b:groq
HF_TIMEOUT_SECONDS=30
```

Hosted enablement requires a private server-side HF token, existing API-key
protection, an allowed default and an uncached profile. Duplicate/unregistered
pairs and cached hosted configuration are rejected. Secret reprs are redacted
and validation error display hides input values. The private `.env`, `OLLAMA_*`
settings, dependencies, lockfile and Docker/Compose files were not changed.

Health makes **no inference calls**. HF selection adds a degraded `hf_generation`
service with live qualification pending, alongside existing local checks.
Configuration/catalog presence does not prove authorization, credits, schema
support or quality. The pending status remains until hosted acceptance is defined
and completed.

## Verification and preservation

- Test-first contract/client/RAG/API failures were observed before implementation.
- **91 new focused HF tests passed** with HTTPX MockTransport, synthetic search,
  in-process ASGI/lifespan and temporary quota files; no real HF token/inference.
- **Full suite: 698 passed, zero skips**, including disposable PostgreSQL; two
  existing dependency deprecation warnings remain.
- **Mypy: 85 source files**, changed-file Ruff and `git diff --check` pass.
- Removing completion-token overrun rejection caused one test failure; exact
  source bytes were restored before the passing full suite.
- Offline provenance/freeze checks reverified **64 frozen/prior files**. Before/
  after evidence verifies **152 prior files unchanged**, with five approved
  config/wiring/type/metadata files changed. Selector helpers, prompts, private
  environment, old workflow/evaluations and dependency files remain intact.
- All **15 original containers** retain IDs/images/states, with five running.
  Original corpus/index/model volumes and the frozen recovery bundle received
  no writes. No ingestion, reindex, model replacement or selector tuning occurred.

Evidence: `tests/test_output/hf-foundation-20261013-01/` (fingerprints, preservation,
container comparison and mutation record), `hf-final-focused-20261013-01/`, and
`hf-full-20261013-01/`. Synthetic tests do not prove hosted quality or latency.
Source remains uncommitted on `master`, HEAD `a597f23`; no push/merge/deployment.

## Next checkpoint

HF-5: freeze a separate hosted protocol/collector/resource profile while retaining
local v2/no-start evidence. Then qualify real schemas with requested smoke calls
and locally configured credentials, compare development candidates and lock one
pair before same-model baseline/agent holdout. Add Qwen's provider controls after
contract qualification. Research browsing/detail/search/citation inspection and
server preparation follow the original roadmap. Missing backup hardware does not
block source work.
