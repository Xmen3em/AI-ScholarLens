# Cerebras evidence development result — 2026-10-16

The approved `hosted-cerebras-evidence-v3` comparison improved development answer
quality, but **is not accepted**. It stopped on a local HTTP 429 at job 63 of 64,
and agent latency exceeds the unchanged target. The application and Telegram bot
remain disabled. The stopped run has not been retried.

## Scope, accounting and preservation

The user explicitly approved one new ceiling of 261 additional calls in response
to `call_71a0432279974fda8683515bd3c09962`. The exact question and answer are retained
in the ignored execution directory. Source checkpoint `50ab668`, source-map digest
`a5aa4ad496a324c69ccbce8a42584fea2b899a317319238920d642813944cb26`, and profile
manifest `2dc8ab7bb2dd98c544d06b80d5b41873a7e3399e04af9375d332829719c6c23b`
were unchanged throughout collection.

Five fresh canonical schema checks passed, including the expected local rejection
of the oversized schema. Collection saved 63 records: 62 successful responses and
one local HTTP 429. It stopped before the final baseline job. The 429 sent no HF
request. **124 new calls are used**, all settled as one, with zero unknown usage;
earlier 125 remain used, **249 total**. The 137 unspent slots in this stopped grant
and the earlier grant's 164 are not transferred or available for another source,
replay, holdout or activation. Returned-usage cost estimate is USD 0.07419595,
not an invoice.

The post-run audit verifies all **449 protected file paths** unchanged, all 15
retained container IDs/images/states matching, five running/no extras, and the
same 58 papers/2,775 chunks and installed model digests. Original API8000 remains
available; API8002 is closed. Global HF, agent and Telegram flags are false.
Minimum sampled free RAM during paper requests was 1,222.04 MiB, above the
preserved 600 MiB acceptance margin. All source/corpus/model preservation checks
passed. Holdout funding and an accepted selection lock remain absent.

## Reviewed quality and failed gates

Codex reviewed all 48 substantive positive responses and all 82 quoted excerpts
against the original questions and frozen fact labels. Every positive response
covers both required facts, and every selected quotation is relevant: **100%
fact coverage and relevance in every collected baseline/agent cell**, with zero
scope errors and zero hybrid fallbacks. All 14 successful negative responses
abstain. The failed negative is a request error and earns no abstention credit.
The final negative baseline response was never collected.

These are development tuning results on a convenience sample, with Codex review
rather than independent human annotation. They are not holdout acceptance or a
population-quality claim. Exact quotation validity alone earned no fact credit;
partial supporting quotations were explicitly distinguished from complete facts.

| Cell | Baseline p95 | Agent p95 | Frozen limits |
| --- | ---: | ---: | --- |
| BM25 / JSON | 8.81 s | 32.85 s | 10 s / 20 s |
| BM25 / SSE | 9.23 s | 33.76 s | 10 s / 20 s |
| Hybrid / JSON | 9.24 s | 34.21 s | 10 s / 20 s |
| Hybrid / SSE | 9.29 s | 34.54 s | 10 s / 20 s |

The scorer rejects the incomplete matrix, latency, failed hybrid/JSON request,
incomplete negative abstention, and the resulting cell regression. Its
`hosted_preservation_incomplete` gate also requires collection status `collected`;
the physical preservation checks above all passed. No gate is removed or waived.

## Diagnosed local issues and next work

The collector paces batches of six from its own clock, while the API resets its
fixed 60-second window on the next arriving request. With slow requests followed
by fast negatives, those windows drift: six requests consumed the API window
starting at 05:40:02.885914 UTC, and the next request at about 05:40:28 was rejected.
The scheduler needs conservative admission before each request, preserving the
six-request quota and stop-on-failure behavior. Retrying the 429 is not allowed.

Read-only profiling with networking forbidden reproduced approval-history checks
at 3,476 / 3,770 / 3,642 ms. One profiled validation recursively loaded the same
qualification 834 times, generated 4,170 schemas and opened 10,159 files. A sampled
23.59-second agent response spent only 2.05 seconds in the recorded HF transport.
Optimize redundant work within a validation operation while retaining fresh
content verification, call-history checks, registration, source binding and all
existing failure gates. Measure and test before keeping a change.

An initial offline review helper used Windows' default cp1256 decoding. The
fingerprint guard rejected it; explicit UTF-8 decoding verifies all 62 successful
response fingerprints. The helper was corrected. Saved records were never edited.

Next: reproduce quota drift and validation redundancy in offline regressions,
fix and measure those local issues, then prepare any fresh source/history-bound
execution scope before asking for another inference approval. No further live
calls are authorized by this stopped run. Accepted full development must still
precede separate full holdout funding and eventual private owner Telegram testing.

Evidence:

- `tests/test_output/hf-cerebras-evidence-development-live-20261016-01/`: metadata,
  qualification, records, completion, bound semantic reviews and failed score.
- `tests/test_output/hf-cerebras-evidence-development-execution-20261016-01/`:
  exact approval, receipt/binding, preflight, 449-file baseline/audit, semantic
  review summary and reproducible read-only history profile.
- `tests/test_output/hf-cerebras-evidence-development-allowance-20261016/`:
  the original registered grant and all 124 settled rows, never reset or replayed.
