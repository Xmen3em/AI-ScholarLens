# Bounded HF error structure diagnostic — 2026-10-14

The diagnostic observer and command are implemented. One approved synthetic
request returned HTTP400 / `json_validate_failed` / `invalid_request_error`.
The complete error envelope contained `failed_generation` as an **empty string**.
There is no rejected JSON object available to inspect, so the underlying cause
remains unresolved. Groq remains unqualified; no paper collection ran.

## Isolated implementation

The new [observer and parser](../src/commands/hf_error_structure.py) are used only
by the new [diagnostic command](../src/commands/diagnose_hf_structure.py).
Existing application source, settings, dependencies and earlier evaluations were
preserved. The observer wraps the retained HTTPX transport inside this command,
using the documented [custom asynchronous transport boundary](https://www.python-httpx.org/advanced/transports/)
and [async response cleanup](https://www.python-httpx.org/async/).
It checks HTTPX0.28.1 explicitly because attaching the wrapper uses the client's
private transport attribute. This is an isolated compatibility dependency.

On HTTP400, the observer buffers at most8192 decoded error bytes within the
original attempt deadline and closes the upstream stream on completion,
oversize, read failure, timeout or cancellation. It replays bounded decoded bytes
to the original label parser, omitting encoding headers that would cause a second
decode. Oversized content is discarded. Other statuses keep original handling.
The inherited decoder still runs before the decoded-byte buffer check; this
is not a new bound on the decoder's temporary allocation.

Transient parsing rejects invalid UTF8, duplicate fields and nonfinite JSON
constants. It records only fixed booleans/nulls and bounded counts: envelope and
generation parse status, object/field/type checks, canonical schema validity,
expected-match and marker membership/duplicates. Prefix flags recognize fixed
JSON/code-fence/reasoning tokens without repairing content. No error messages,
generated text, reasoning, arbitrary keys or credentials are saved or emitted.
Pydantic exceptions are discarded, and failed usage remains unknown.

The [protocol](../evaluation/week7_hf/structure-diagnostic-v1/PROTOCOL.md) and
[profile](../evaluation/week7_hf/structure-diagnostic-v1/profile.json) were frozen
before inference. Manifest SHA256:
`18119b207cec1a74781361c3b2666d542806763e92f496c6c7b52637b5b2dff7`.
Both original qualification-v2 and paired-route manifests are bound and verified.

Only the exact frozen synthetic relevance case is sent through the original
HF unified route with `openai/gpt-oss-120b:groq`. Prompt/system/schema, strict
mode, temperature0, low reasoning and256 output tokens remain unchanged. The
normalized request-content hash matches both prior route arms:
`931ef8f69542e6e68308765a0f948978bd2299772b881889546b6039237934f3`.
The30-ID schema still rejects locally with zero calls. No retry, redirect,
proxy, fallback, provider/model switch or public qualification was added.

Offline planning reads neither private settings nor the allowance and contacts
no service:

```powershell
.venv-win/Scripts/python.exe -m src.commands.diagnose_hf_structure --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/hf-structure-plan-new
```

Execution requires explicit `--execute`, fresh ignored output, unchanged live
source/model state, original hosted admission, owned quotas, and one slot from
the same cumulative SQLite allowance. A one-attempt client cap independently
enforces that ceiling. Unknown completion consumes the reservation. Even a
successful expected decision can never grant qualification or start paper jobs.

## Observed trial

| Measurement | Observed value |
| --- | --- |
| Actual outbound attempts | 1 |
| HTTP/code/type | 400 / `json_validate_failed` / `invalid_request_error` |
| Elapsed time | 768.39ms |
| Complete valid error envelope | Yes |
| Failed-generation field | Present, string, zero characters |
| Generation JSON validity | False; schema/expected-match stay null |
| Token usage/cost | Unknown |
| Qualification accepted / paper data sent | False / false |

The initial1024MiB admission check passed. The later pre-call sample was979.82MiB,
and minimum observed free RAM was931.42MiB, above the unchanged600MiB live margin.
The initial admission value was not persisted; do not describe the later979.82MiB
sample as meeting1024MiB. The failure is the observed completed providerHTTP400,
with no local memory stop. All four run preservation flags are true.

An empty reported field does not prove the model generated nothing: it may be
a placeholder, omission or incomplete error detail. It cannot establish token
exhaustion, invalid local schema, schema forwarding, refusal or malformed model
output. Official [Groq structured-output documentation](https://console.groq.com/docs/structured-outputs)
lists GPT-OSS120B strict support and requests reproductions of400 errors. That
advertisement does not establish this HF route's actual behavior.

**Eight of the approved13 attempts are used; five remain.** This one-attempt
reservation settled at one in the fixed
`tests/test_output/hf-approved-pilot-20261013/allowance.sqlite3`. Prior failed
trials and attempt balances are retained. Known-usage estimates across all runs
remain $0.00018090 plus five failed attempts with unknown usage/cost; zero in
this run's known-usage field is not zero billing. The five remaining slots cannot
fund five qualification calls plus the original eight-call paired paper case.

## Verification and continuation

**835 tests passed, zero skips; mypy passed for96 source files.** Forty-eight new
isolated tests cover parser/type/schema/privacy boundaries, compressed replay,
oversized and interrupted stream cleanup, original status handling, one-attempt
limits, memory rejection, offline planning, frozen protocol integrity and
cumulative allowance settlement/exhaustion. A deliberate arbitrary-content leak
failed its privacy regression; exact bytes were restored before full checks.
Changed-file Ruff and diff checks pass. Two existing Typer/Click deprecation
warnings remain.

All203 pre-turn protected hashes match, and all source hashes still match the
live run. Original local validation confirms64 frozen/prior files, eight
development/24 holdout cases and retained corpus/index/model state. All15 retained
container identities/image digests/states match, five running; only the owned
test database was created and removed. The recovery manifest is unchanged.
Original API/key, selector/controller guards/prompts, data/models and disabled
defaults remain intact. Source remains uncommitted atWeek6 checkpoint a597f23;
no deployment, push, merge, data/model replacement or selector tuning.

- [Live diagnostic](../tests/test_output/hf-structure-live-20261014-01/diagnostic.json).
- [Final audit](../tests/test_output/hf-structure-20261014-01/audit.json),
  [test/type evidence](../tests/test_output/hf-structure-20261014-01/verification.json)
  and [privacy mutation](../tests/test_output/hf-structure-20261014-01/mutation.json).
- Full-suite base: `tests/test_output/hf-structure-full-20261014-01`.
- [Offline plan](../tests/test_output/hf-structure-plan-20261014-01/metadata.json).

Next prepare a local minimal reproduction and a separately frozen experiment
that can distinguish provider compatibility from generation limits, using
public synthetic inputs and fixed privacy-safe failure categories. Preserve
the exact-contract failed trial; avoid another unchanged paid repetition.
Any experimental request-control variant must be explicit and cannot silently
change application prompts, limits or selectors. Do not send a support message
or publish the reproduction without a user request. Reviewed development and
locked holdout remain prerequisites in the existing research-interface/server
roadmap. Missing backup hardware does not block source work.
