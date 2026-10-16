# Full Cerebras holdout: collected, quality rejected — 2026-10-16

All **192 holdout jobs and five fresh schema checks completed** on the frozen
`hosted-cerebras-paced-v4` source using `openai/gpt-oss-120b:cerebras`. The
holdout **fails acceptance**: the agent regresses against the baseline in all
four retrieval/transport comparisons. The application and private Telegram bot
remain disabled, and no application acceptance lock was created.

The user explicitly approved the separate 773-call ceiling in
`call_b003f7dbf66a4b71a4568fa76fd020bf`. **345 calls were used**, all settled with
known usage; **719 cumulative** = 28 + 97 + 124 + 125 + 345. The remaining **428**
stay bound to this completed holdout. Earlier unused 164/137/136 slots also stay
bound to their previous grants. No replay, transfer, provider fallback or new
inference was used during review. Returned-usage cost is approximately
**USD 0.20357985**, an estimate rather than an invoice.

## Quality and latency

Each comparison cell contains 16 answerable and eight negative questions.
Every agent cell falsely abstains on three answerable questions, compared with
two for its baseline. All **64 negative responses correctly abstain**, and
there are no scope errors, request failures, attribution failures, unknown-usage
attempts, schema violations or hybrid fallbacks. The four failed gates are
`regression_or_empty_relevance:{bm25,hybrid}:{json,sse}`; these runs have
substantive answers, so the observed failures are regressions.

| Mode / transport | Baseline fact coverage | Agent fact coverage | Baseline relevance mean | Agent relevance mean | Baseline p95 | Agent p95 |
|---|---:|---:|---:|---:|---:|---:|
| BM25 / JSON | 70.83% | 68.75% | 85.71% | 80.77% | 3.934 s | 9.307 s |
| BM25 / SSE | 70.83% | 68.75% | 85.71% | 80.77% | 2.681 s | 9.488 s |
| Hybrid / JSON | 78.13% | 78.13% | 92.86% | 100% | 3.935 s | 10.070 s |
| Hybrid / SSE | 78.13% | 78.13% | 92.86% | 100% | 3.247 s | 10.058 s |

All p95 values pass the unchanged baseline/agent limits of 10/20 seconds.
Hybrid still fails because its agent has more false abstentions and lower
paraphrase coverage than its baseline. Agent coverage on the two multi-paper
questions is zero in every cell; numeric-question coverage is 100%.

Codex reviewed all **108 substantive responses and 170 quotations**, including
26 unique quotation texts, against the original questions and frozen facts.
154 quotations are relevant. Response, question, fact, record and profile
fingerprints bind the reviews. Exact quotation validity alone earns no semantic
credit; partial support is distinguished from a complete required fact. For
example, a quotation naming GAIA without its public-validation split does not
independently earn the complete split-specific fact. These are Codex judgments,
not independent human annotation or a population-quality guarantee. All four
comparisons also fail the false-abstention check independently of quotation-credit
choices. No source, label, prompt, gate or saved model response changed during review.

## What the saved evidence establishes

The failure is in evidence handling and answer coverage; the hosted route and
schema checks work. Offline inspection used only saved outputs and the unchanged
candidate builder, with no model calls or parameter sweeps:

- For the SpeechGym paraphrase, the agent retains the abstract containing both
  required facts. Its question-term coverage is 0.50, below the frozen 0.60
  per-paper threshold, so the candidate builder offers zero sentences. The
  agent abstains before calling its selector. Baseline context contains more
  passages from that paper, passes the lexical check and answers both facts.
- For the cross-training question, final BM25 agent citations contain both
  required supporting passages. The TTPO paper matches 0.545 of the combined
  question's terms and is excluded by the same per-paper check. A paper that
  answers one part of a multi-paper question need not repeat the other part's
  terms. The selector receives three candidates and the agent abstains.
- For cross-evaluation, the BM25 agent returns a general attribution sentence
  without the requested LOCO validation or bootstrap confidence intervals.
  Hybrid abstains. The credit paper's term fraction is 0.375 in contexts that
  retain it; the final catalog excludes that paper.
- The literal reasoning-benchmark question fails under BM25 despite one rewrite
  and succeeds under hybrid. The saved final contexts differ. Final citations
  occur after grading, so absent final support does not prove it was absent
  from the initial retrieval.

The diagnostic records these limits explicitly. It neither reruns the holdout
nor converts it into a passing result.

## Preservation and evidence

Application source remains checkpoint `ba1f168`, collected at documentation
checkpoint `296835a`, with source-map digest
`8baa1a6e12e3e14e7c061dfec03653e3670dee929fde5340aa889b944c950487`.
Profile manifest remains
`a289b0f75fdf6af2da9687e9e0ecd8df281598cb69b235141704515a34f31ca7`.
The accepted development selection remains unchanged. All 1,386 source tests,
zero skips, Ruff and mypy127 remain the last passing source verification; no
source changes justified another test-suite run.

Preflight verifies all 552 protected paths, current provider rates, source,
selection, retained services and RAM before execution. Free RAM is 2,701.19 MiB
at manual preflight and 2,599.09 MiB at collector admission, above the unchanged
1,536 MiB hybrid requirement. The lowest sampled paper-request RAM is
1,130.41 MiB, above the 600 MiB live floor. No threshold was lowered.

The final audit preserves all **552 protected paths**, all 15 container
identities/images/states, five running/no extras, 58 papers, 2,775 chunks and
installed model digests. Original API8000 remains up, API8002 is closed, and
global HF/agent/Telegram flags remain false. The earlier Docker Desktop recovery
started only verified existing containers; it recreated or rebuilt none.

Evidence remains in ignored local storage:

- `tests/test_output/hf-cerebras-paced-holdout-live-20261016-01/`: metadata,
  qualification, 192 saved records, completion, reviews and failed score.
- `tests/test_output/hf-cerebras-paced-holdout-execution-20261016-01/`: exact user
  approval, approved receipt and binding, preflight, semantic review, offline
  diagnosis, accounting/preservation audit and reproducible helpers.
- `tests/test_output/hf-cerebras-paced-holdout-allowance-20261016/`: the original
  fixed ledger and registration, with 345 settled rows. Never reconstruct them.

The result seal covers **32 files**, SHA256
`32928bd5969ab1ce09324dee5aa51bb56dac59c9a33072bd8609b0dc0242c0bf`.
`protected-expanded.json` is the next **585-path preservation baseline**. Do not
modify sealed artifacts or rerun their finalizers in place. An initial unsealed
preflight helper had a date-path replacement error before inference or ledger
creation; the failed helper and incident are preserved. The exact user approval
record was retained, the helper paths were corrected, and the successful full
preflight preceded the only collector execution.

## Next development work

Preserve this rejected holdout as historical evidence. It has now been inspected
and cannot serve as an unseen acceptance set for a tuned replacement.

The next change should address the interaction between relevance filtering,
lexical candidate eligibility and questions requiring multiple papers. Start with
new synthetic development examples that test paraphrases, complementary evidence
from different papers, and unrelated passages. Verify that relevant evidence
survives filtering while unrelated evidence still cannot produce an answer;
retain bounded exact quotations, source ownership, budgets, deadlines and resource
limits. Do not simply lower the threshold or alter the acceptance gates to make
this holdout pass.

Any replacement needs a separately versioned source/profile and fresh development
and unseen holdout evidence. Prepare and verify the implementation offline before
presenting a concrete new live-call scope. This completed grant authorizes none
of that new inference. Only accepted evidence permits the subsequent private PC
API/owner Telegram activation and actual owner question/reply test. The bot token
and owner pairing are already configured; no repeated setup is needed now.
