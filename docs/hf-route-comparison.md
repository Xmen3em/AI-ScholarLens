# HF/Groq route comparison — 2026-10-13

Current continuation2026-10-14: [bounded structural diagnostics](hf-structure-diagnostic.md)
are implemented and verified. One exact synthetic request returnedHTTP400 and
reported failed_generation as an empty string.835 tests pass,zero skips;
**8/13 approved attempts used,5 remain**. This paired-route report below retains
its original observations and historical attempt balance.

The explicit two-route comparison is implemented and tested. Both live arms
returned HTTP 400 with `json_validate_failed` / `invalid_request_error` for the
same frozen synthetic relevance request. The provider-specific relay did not
resolve the failure in this pair. Groq remains unqualified; paper collection
and application activation remain pending.

## Implementation and source evidence

The new [command](../src/commands/compare_hf_routes.py) plans offline by default.
Its [comparison helper](../src/commands/hf_route_comparison.py) uses the existing
bounded HF adapter only inside this diagnostic command. No existing application
source, registry, default settings, dependencies or prior evaluation files were
edited in this slice.

The [protocol](../evaluation/week7_hf/route-comparison-v1/PROTOCOL.md),
[profile](../evaluation/week7_hf/route-comparison-v1/profile.json) and
[source provenance](../evaluation/week7_hf/route-comparison-v1/sources.json)
were frozen before inference. Comparison manifest SHA256:
`d68d2a7e37bead8df18de30dab7033fa3b6fd208bb7187202097bdc6a6ae963c`.
The exact synthetic prompt, system, schema and expected decision come from the
retained [qualification-v2 fixtures](../evaluation/week7_hf/qualification-v2/fixtures.json),
manifest `762bbc82e159bd873d41185059bcb838a641b4fa81d8636805b1eec1417a6464`.

The route derivation is pinned to official HF SDK commit
`a704b8488c6ec78f719c576ba77a6035095dae77`: its
[Groq helper](https://raw.githubusercontent.com/huggingface/huggingface_hub/a704b8488c6ec78f719c576ba77a6035095dae77/src/huggingface_hub/inference/_providers/groq.py)
uses `/openai/v1/chat/completions`, and the
[shared provider helper](https://raw.githubusercontent.com/huggingface/huggingface_hub/a704b8488c6ec78f719c576ba77a6035095dae77/src/huggingface_hub/inference/_providers/_common.py)
selects the HF provider proxy for an HF token and maps the model to its native
provider ID. The proxy host comes from the pinned
[constants](https://raw.githubusercontent.com/huggingface/huggingface_hub/a704b8488c6ec78f719c576ba77a6035095dae77/src/huggingface_hub/constants.py).
The public Hub mapping was checked before inference: Groq, conversational,
live, native ID `openai/gpt-oss-120b`. Metadata requests carried no credentials.

| Arm, in frozen order | Fixed HF endpoint | Wire model |
| --- | --- | --- |
| Unified | `https://router.huggingface.co/v1/chat/completions` | `openai/gpt-oss-120b:groq` |
| Provider relay | `https://router.huggingface.co/groq/openai/v1/chat/completions` | `openai/gpt-oss-120b` |

Both arms use the same HF credential, model and provider. All request content
apart from the wire model is identical: original strict JSON schema, production
controller instructions, temperature 0, low reasoning, 256 output tokens and
8192 context with 512 reserve. The whole-payload hash with `model` omitted is
`931ef8f69542e6e68308765a0f948978bd2299772b881889546b6039237934f3`
for both arms. The original 30-ID schema still rejects locally with zero calls.

Each arm allows one attempt. The two scheduled arms share an owned six-per-minute
quota and atomically reserve two slots from the existing cumulative allowance.
A completed HTTP 400 allows the second predeclared arm; unavailable memory,
quota denial, cancellation, timeout or uncertain transport work stops it.
Existing 30-second timeouts, body limits, privacy rules, 1024 MiB host admission
and 600/384 MiB live memory boundaries remain. No retries, redirects, proxy,
fallback, direct Groq credential, schema relaxation or public qualification
are introduced.

## Observed result and allowance

The retained run is
[`hf-route-comparison-live-20261013-01`](../tests/test_output/hf-route-comparison-live-20261013-01/comparison.json).
Terminal metadata reports `comparison_completed`, meaning both scheduled arms
finished; `qualification_accepted` remains false.

| Arm | Status and allowlisted error | Elapsed | Minimum host free RAM | Usage |
| --- | --- | --- | --- | --- |
| Unified | 400 / `json_validate_failed` / `invalid_request_error` | 625.52 ms | 2198.28 MiB | Unknown |
| Provider relay | 400 / `json_validate_failed` / `invalid_request_error` | 710.50 ms | 2231.08 MiB | Unknown |

Exactly two synthetic attempts were made. No public-paper question or passages
were sent, and no evaluation app or paper job ran. Error messages, failed
generations, raw decisions and reasoning were discarded. These observations
do not establish why validation failed, the router's internal strict forwarding,
reliability, task quality or application latency.

**Seven of the approved 13 outbound attempts are used; six remain.** Trial04
used two, trial05 used two, the prior one-call diagnostic used one, and this
comparison used two. Both new attempts settled against the fixed
`tests/test_output/hf-approved-pilot-20261013/allowance.sqlite3`. Fresh output
directories cannot reset that allowance; unknown completion consumes its
reservation.

Neither new response reported token usage. The saved known-usage estimate of
zero reflects absent reported usage, not zero billing. Across all retained
trials, the known-usage estimate remains $0.00018090 plus four failed attempts
with unknown usage/cost. This is not an invoice or verified credit balance.

## Verification and preservation

**787 tests passed, zero skips; mypy passed for 94 source files.** Seventeen new
isolated tests cover frozen routing and public mappings, identical payload
controls, shared quotas, per-arm caps, scheduled failure behavior, timeout and
memory stops, offline planning and insufficient cumulative allowance. A mutation
omitting the native wire-model mapping failed its regression test; exact source
bytes were restored before the full suite. Changed-file Ruff and diff checks pass.

All 193 pre-turn protected file hashes match, including existing source,
private settings, dependencies, earlier evaluations and failed trials. All four
run preservation flags pass. Original local validation confirms 64 frozen/prior
files, eight development/24 holdout cases, 58 papers, 2775 v2 chunks, 1221 v1
chunks, the v2 alias and retained model digests. All 15 retained container
identities/images/states match, five running; the owned test database was removed.
The recovery manifest remains
`a17b2ac49f8f44b74a5090510668e5c93d1fadd7afdd547b4090f350d1fb7685`.

Evidence:

- [Final audit](../tests/test_output/hf-route-compare-20261013-01/audit.json)
  and [mutation check](../tests/test_output/hf-route-compare-20261013-01/mutation.json).
- Full suite base: `tests/test_output/hf-route-compare-full-20261013-01`.
- [Offline two-arm plan](../tests/test_output/hf-route-compare-plan-20261013-01/metadata.json).
- [Live metadata](../tests/test_output/hf-route-comparison-live-20261013-01/metadata.json)
  and [paired ledgers](../tests/test_output/hf-route-comparison-live-20261013-01/comparison.json).

## Next diagnostic slice

Prepare an isolated structural parser for the provider's failed-generation field
before another paid attempt. Enforce existing error-body bounds and reject
malformed/duplicate fields; persist only parse/type/schema/expected-match
booleans and bounded counts, with synthetic privacy tests. Never retain error
messages, generated content or reasoning. Freeze the diagnostic protocol and
reserve its explicit ceiling from the six remaining calls before execution.
The current records cannot be retroactively enriched because error content was
discarded. Further live calls require a new evidence-producing experiment,
not repetition of this already completed pair.

Keep Groq unqualified and the HF/agent defaults disabled until exact-schema
qualification, reviewed development and locked holdout acceptance pass. A
provider/model comparison outside the approved Groq scope needs its own explicit
transfer authorization and frozen experiment. Continue the existing research
interface/server roadmap after acceptance; missing backup hardware does not
block source work. No deployment, push, merge, selector tuning, or model/data
replacement occurred.
