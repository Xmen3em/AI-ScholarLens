# Cerebras paper evaluation and private PC runtime

The selected provider is absent from the original frozen Groq/Fireworks profile.
The retained `cerebras-evaluation-v1` adds only the model/provider and dated rates.
Current execution uses the separate `evaluation/week7_hf/cerebras-tokenized-v2/`
profile to correct one input-admission algorithm. Both old profiles and all original
labels, quality gates, resource/work limits and payload controls remain immutable.
Collector, scoring, call accounting and acceptance integration are prepared.
Execution still requires new explicit approval; no paper run is funded.

The implementation binds profile identity through planning,
collection, per-run qualification, semantic reviews, scoring, development selection
and holdout locks. Corruption and replay checks reject profile/model/manifest
mismatches. The old CLI defaults and existing quality gates remain. A complete run
uses the same model for baseline and agent. Development has 64 jobs and a maximum
of 261 outbound attempts; holdout has 192 jobs and a maximum of 773, including five
fresh qualifications in each. These are future ceilings, not authorizations.

`src.commands.evaluate_hf_papers` defaults to an offline plan. `--propose-approval`
writes a pending receipt without loading credentials, initializing funding or
contacting services. `--execute --approval PATH` requires the exact approved
source, full matrix, snapshot and historical 28-attempt accounting. Development
and holdout have separate fixed ledgers and registration files; missing registered
state requires recovery. A reservation is durable before every provider attempt.
Failed and uncertain attempts count; a stopped run cannot restart or fall back to
another provider. No automatic inference retry is implemented.

Paper execution sends the frozen evaluation questions and bounded excerpts from
the retained public papers to HF/Cerebras. It does not send local credentials,
Telegram identifiers, provider reasoning or unrelated documents. Admission stays
1,024 MiB for BM25 and 1,536 MiB for the full comparison containing hybrid jobs;
live margin is 600 MiB, emergency floor 384 MiB. The model runs remotely.

Scoring uses the explicit `--profile hosted-cerebras-tokenized-v2`. Semantic reviews bind
each response and its supported facts to the records. `lock` requires accepted
64-job development evidence; holdout revalidates that lock before spending. After
the separately approved 192-job holdout passes, `accept` creates an application
lock that rechecks the complete evidence, funding and current source. Schema
compatibility alone never enables the application.

Offline plan and proposal (choose fresh ignored output directories):

```powershell
.venv-win/Scripts/python.exe -m src.commands.evaluate_hf_papers --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/cerebras-paper-plan-new
.venv-win/Scripts/python.exe -m src.commands.evaluate_hf_papers --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/cerebras-paper-proposal-new --propose-approval
```

The initial proposed scope is **at most 261 development attempts**, including
five fresh synthetic checks and the complete 64-job comparison. Failed or
uncertain work counts. It stops on qualification, schema, attribution, accounting,
source, usage or resource failure. This does not authorize holdout spending,
runtime activation or Telegram messages. At the frozen rates and native token
ceilings, 261 attempts have an estimated upper usage cost below USD 0.81; this is
not an invoice, and provider pricing is checked before execution.

The candidate runtime source is prepared before evaluation to keep source binding
intact. `run_pc_api --check-app --acceptance PATH` validates offline;
`--execute-app --acceptance PATH` serves only loopback port 8002, one worker,
with a separate quota file and read-only PostgreSQL sessions. It validates the
accepted corpus/models at startup and revalidates acceptance before each model
call. Each API request has at most six model attempts; only the accepted Cerebras
pair and canonical schemas are admitted. Cache and tracing stay off in this
isolated configuration. The original API8000 and private `.env` are preserved.

`run_telegram --check --acceptance PATH` validates the already paired owner
configuration offline. With explicit activation, `--execute --acceptance PATH`
uses the authenticated candidate API8002 and verifies its acceptance identity
before Telegram polling. Only the configured owner can ask questions. Existing
offset state prevents replay; question inference is never automatically retried.
No runtime or Telegram process has been started by this preparation.

The approved two-case selector check is complete. Its initial admission stopped
at 674.26 MiB free RAM before any attempt. RAM recovered naturally; a fresh second
run reused the registered ledger and passed both cases. The counter is exhausted
and immutable. The strict combined report verifies all five cases on checkpoint
`1f7af96`; paper/app acceptance remains false. All 28 approved attempts are used.
No paper evaluation or extra schema execution is currently funded.

The model runs remotely. Local RAM is still needed by the collector and retained
services; Ollama's read-only loaded-model list was empty during the schema audit.
Model task and app acceptance remain incomplete; the private bot is paired and
disabled. Current verification results are recorded in `session-checkpoint.md`.

The previous source checkpoint `16af44a` passed 1,307 unique tests, Ruff and mypy
for 124 files. A later local prompt rehearsal found a real pre-wire failure in the
first development relevance prompt: 12,276 characters cannot pass the old byte
admission. Synthetic schema success had not proved task prompt compatibility.
This was found with zero HF calls and no new funded ledger.

Tokenizer source checkpoint **8bb7a7b** fixes admission with a new explicit profile,
manifest SHA-256 `92ec9996534e5a958d4ead38fa9224b83ce6c3a318ca3919d886decaeba2558d`.
It uses the published GPT-OSS ordinary BPE vocabulary to count the entire serialized
schema-inclusive request. The 8,192-token context, 512-token template reserve and
256/512 output limits stay fixed. Request JSON additionally has a 65,536-byte cap
and schema JSON a 7,168-byte cap. The original 30-candidate grammar still rejects
locally. Full passages, question text, markers and original schemas are preserved.
Old native clients continue to enforce the old byte gate.

Tokenizer data is prepared explicitly, then only read and hash-checked at runtime:

```powershell
.venv-win/Scripts/python.exe -m src.commands.prepare_hf_tokenizer
.venv-win/Scripts/python.exe -m src.commands.prepare_hf_tokenizer --download
```

The second command fetches a single 3,613,922-byte public vocabulary into ignored
`data/pc-app/tokenizer/` storage. It verifies the published SHA-256 before writing
and never silently overwrites an existing file. Runtime never downloads or repairs
the table; missing, changed, oversized or wrongly versioned tokenizer data stops
before inference. `tiktoken==0.14.0` is pinned, with no changes to existing locked
package versions. No model weights are downloaded. The task dependency cache is
under `.cache/uv-tokenizer-20261016`, outside pytest discovery.

Primary tokenizer definitions:
[GPT-OSS](https://github.com/openai/gpt-oss/blob/main/gpt_oss/tokenizer.py) and
[tiktoken 0.14.0](https://github.com/openai/tiktoken/blob/0.14.0/tiktoken_ext/openai_public.py).
The local splitting expression and ordinary token counts match the pinned package
on five synthetic Unicode/special-looking-text samples. The local first-pass
rehearsal checks 32 real BM25/hybrid development cells and 60 native payloads;
all fit, with maximum 4,573 conservative input tokens and 13,651 payload bytes,
zero hybrid fallbacks and preserved source/corpus/model digests. It uses synthetic
model decisions and verifies neither semantics nor real model decisions/rewrites.
It makes no HF requests and does not replace the full paper benchmark.

The current exact pending development proposal is
`tests/test_output/hf-cerebras-tokenized-development-proposal-20261016-02/proposed-approval.json`,
byte SHA-256 `f324be5d4444af0c0ff970926f51e5def71e0256edf09bfb34cfcce7897206d1`.
Its source-map digest is
`41fc2932e58fc53ecacd9bcabd83374bd92fa989ca0c5eb3704b4f04192d65c0`.
It supersedes the earlier **unapproved** v1 proposal; the ceiling remains 261,
with no second allowance or reset. Both actual task ledgers and registrations
remain absent. Current verification results are in `session-checkpoint.md`.

Source checkpoint **005651b** additionally enforces the promised stop on any
failed funded paper response, including HTTP/SSE failures after an invalid
context-specific controller decision. A real-loopback fault-injection regression
qualifies five checks, rejects an unknown relevance marker, records exactly seven
mocked attempts and leaves the next job unattempted. All 13 collector regression
tests pass. Original collector behavior outside the funded run is unchanged.
The input-generation files are byte-identical to the successful local rehearsal;
only the collector and funded client's stop policy changed afterward. Final full
regression passes **1,323 tests, zero skips**, in 865.49 seconds (two existing
Typer warnings). Ruff and mypy for 126 source files pass. All 367 protected files
match, as do all 15 retained container identities/images/states, five running and
no extras. The 58-paper/2,775-chunk corpus and installed model digests are preserved.
Final free RAM was 1,597.38 MiB, above the 1,536 MiB hybrid admission; check again
at execution. No current user RAM action is needed. Global flags stay disabled.
No new inference or Telegram request has been made. Exact audit and JUnit evidence
are recorded in the current session checkpoint and pending proposal directory.
