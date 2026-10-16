# Paced Cerebras development proposal — 2026-10-16

The local quota drift and repeated-validation overhead are corrected and
committed. A fresh `openai/gpt-oss-120b:cerebras` development comparison is
prepared on the corrected source. **No new calls are approved; the application
and private Telegram bot remain disabled.** The previous stopped result remains
authoritative for its captured source and is never replayed or rescored as a pass.

## Corrections and frozen scope

Source checkpoint `ba1f168` follows `dca1a18` (quota pacing), `8582a96` (scoped
validation) and `6a59c56` (additive frozen profile). Source-map digest:
`8baa1a6e12e3e14e7c061dfec03653e3670dee929fde5340aa889b944c950487`.
The new profile is `hosted-cerebras-paced-v4`, manifest SHA256
`a289b0f75fdf6af2da9687e9e0ecd8df281598cb69b235141704515a34f31ca7`.
Its immutable files are in `evaluation/week7_hf/cerebras-paced-v4/`.

The collector admits at most six requests in every rolling 61-second interval
and waits a full 61 seconds after qualification completes. This prevents the
observed slow-then-fast drift against the API's fixed 60-second window. Admission
waits stay outside request latency, as before. An unexpected HTTP 429 still stops
the run without retry. The API quota is unchanged.

Validation reuses pure frozen loader results within one synchronous operation,
checks frozen content hashes before and after that operation, and discards the
memo afterward. Cached returns are independent copies. Fresh checks of source,
receipts, registration, SQL call accounting, history and resources remain in
place. Same-size/mtime changes, deletion, newly added frozen files and changes
between operations fail verification. No TTL or file-stat-only proof cache.

The profile differs from evidence-v3 only in its version. It retains the model,
three sentences per passage/ten total candidates, native input counting and byte
caps, all five canonical qualification payloads, controller system, deadlines,
work bounds and every quality/resource gate. Agent/baseline p95 targets remain
20/10 seconds. RAM admission remains 1,024 MiB for BM25 and 1,536 MiB for hybrid;
live/emergency floors remain 600/384 MiB. Older frozen profiles and defaults are
unchanged. No holdout labels are used to tune these corrections.

## Proposed authorization and accounting

One **new ceiling of up to 261 additional attempts** covers five fresh synthetic
schema checks and the complete **64-job development matrix**: eight cases,
BM25/hybrid, JSON/SSE, baseline/agent. Only bounded questions and public paper
excerpts from the retained corpus are sent. Failed or uncertain attempts count.
Failed qualification, schema, attribution, accounting, source, usage or resource
checks stop execution. No stopped-run replay, provider fallback, holdout spending
or application/Telegram activation is included.

**249 previous attempts remain used:** 28 historical schema/prompt checks,
97 completed first-development attempts, and 124 settled attempts from the
stopped evidence-v3 comparison. Its 137 unspent slots and the older 164 are not
transferred. The new receipt binds all three histories, including both sealed
development results. Historical receipts, evidence and ledgers are read-only;
no missing registration or ledger is reconstructed.

The pending receipt and source-bound metadata are in
`tests/test_output/hf-cerebras-paced-development-proposal-20261016-01/`.
Receipt byte SHA256:
`1db8bf7374eb94f72b5873d47912e76f58063a2fb78cbe015dbe4c2fb888ea6d`.
They grant zero calls until explicit approval. The separate fixed ledger would
be `tests/test_output/hf-cerebras-paced-development-allowance-20261016/allowance.sqlite3`,
with its `.registered` marker; both remain absent before approval. A pending
receipt was passed to the actual execution entry point and rejected before
Settings, networking or ledger allocation.

The credential-free [HF router catalog](https://router.huggingface.co/v1/models),
checked at 08:22:58 UTC on 2026-10-16, lists Cerebras as live with structured
output at USD 0.35/0.75 per million input/output tokens. The conservative
261-call estimate is **USD 0.801792**, under USD 0.81; this is not an invoice.
Availability, rates, current source, accounting and free RAM are rechecked
before any approved execution. The model runs remotely; local retrieval and
retained services still use RAM.

## Verification and limitations

**All 1,386 tests pass, zero skips**, in 946.66 seconds, with the two
existing Typer dependency warnings. Ruff and mypy127 pass. Focused checks cover
quota drift, frozen-input mutation, all retained accounting, separate pending
funding, collection, scoring, acceptance and private runtime. A deliberately
inverted history-status guard is caught; the source was restored byte-identically.

The final audit preserves all **480 protected file paths**, all 15 retained
container IDs/images/states, five running/no extras, 58 papers/2,775 chunks and
installed model digests. API8000 is available; API8002 is closed. Global HF,
agent and Telegram flags remain false. Both old 97/124-call ledgers remain
settled and unchanged; every holdout ledger and the new development ledger and
registration remain absent. Free RAM at audit was 1386.74 MiB;
hybrid admission returned `insufficient_memory` against its unchanged
1,536 MiB threshold. No inference was attempted. Execution must pass current
admission again. The added diff passes the private
configuration secret scan.

A subsequent collector-only source/history/admission probe also rejects at
1,293.56 MiB free, below 1,536 MiB. It creates no grant or inference request.
The prepared scope can only execute after a later passing admission check.

The initial full run passed 1,384 tests and hit two preserved CLI-output path
collisions because its fresh absolute temporary path reused an older basename.
The globally unique namespace yields the clean full run above. Both reports
are retained; no earlier output, test or assertion was removed or changed.
The final report is `full-final.xml` in the preparation evidence directory.

On exactly the same historical proposal, validation fell from a mean 3,629.608 ms
to 373.998 ms, a 9.7-fold improvement with identical output and networking
forbidden. The new v4 proposal additionally verifies the stopped 124-call history;
its three samples are 922.018/905.185/908.718 ms, mean 911.974 ms. These measurements
are local validation timings, not fresh model or application latency acceptance.

The current-source local rehearsal passes **32 cells and 60 native payloads**
using real retained retrieval, installed embeddings and service/LangGraph paths.
Maximums are 4,573 input tokens, 13,651 payload bytes and 947 schema bytes; the
thirty-candidate schema rejects. Admission free RAM was 2,094.33 MiB and minimum
sampled availability 1,215.09 MiB. Source, corpus and models match afterward.
HF generation and external HTTP are forbidden by the helper.

Its synthetic scope=true/relevance=all/selector=NONE decisions establish first-
pass input compatibility only. They do not establish actual answer quality,
rewrites, HTTP transport equivalence, live latency or acceptance. Fresh inference
and honest review/scoring remain necessary. Evidence and reproducible helpers
are in `tests/test_output/hf-cerebras-local-runtime-fix-20261016-01/`.
Its `evidence-sha256.json` seals 39 preparation files, SHA256
`e5c0222dd1baf91598b713694ba4d1334482e59df93c036b1890c29b6ce0bb1e`.
`protected-expanded.json` supplies the next 520-path preservation baseline.

## Execution and remaining application work

After explicit approval, preserve the exact question/answer in a fresh ignored
execution directory and derive the approved receipt without changing its scope.
Keep source/profile/proposal fixed, pass current admission, then run:

```powershell
.venv-win/Scripts/python.exe -m src.commands.evaluate_hf_papers `
  --snapshot tests/test_output/week7-source-review-20261013-01 `
  --split development --profile hosted-cerebras-paced-v4 `
  --output tests/test_output/hf-cerebras-paced-development-live-20261016-01 `
  --execute --approval <fresh-approved-receipt-path>
```

Review the actual answers against frozen development judgments and score all
64 jobs. Only accepted full development permits a selection lock and a separate
192-job holdout proposal, at most 773 additional attempts with five fresh
qualifications. Accepted full holdout precedes explicit private PC/API and owner
Telegram activation and a real bot test. The token and owner pairing are already
configured; no repeated setup or token sharing is required.
