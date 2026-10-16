# Paced Cerebras development accepted — 2026-10-16

The complete `hosted-cerebras-paced-v4` development comparison **passes every
gate**. All 64 jobs and five fresh schema checks succeeded. The quota drift is
resolved in this run, and measured latency passes the unchanged targets.
The application and private Telegram bot remain disabled pending full holdout
acceptance and explicit activation.

The user approved one new maximum of 261 calls in
`call_ac6574a5a0e749d4ae647ff98af4c1f1`. The exact question/answer, approved receipt
and authorization binding are retained in the execution directory. Collection
used checkpoint `e0fe52e`; application source remains `ba1f168`, digest
`8baa1a6e12e3e14e7c061dfec03653e3670dee929fde5340aa889b944c950487`.
Profile manifest:
`a289b0f75fdf6af2da9687e9e0ecd8df281598cb69b235141704515a34f31ca7`.
No source, frozen profile, label, threshold or default changed during collection.

**125 new attempts are used**, all settled as one with known usage. Earlier
249 remain used, **374 cumulative**. The completed grant's remaining 136 slots
stay bound to this scope; the earlier unused 164/137 are also not transferred.
Returned-usage cost estimate is USD 0.07434775, not an invoice. No holdout calls
or Telegram traffic occurred.

Codex reviewed all **48 substantive responses and 82 quotations** against the
original questions and frozen fact judgments. Every positive answer covers
both required facts; every quotation is relevant. Partial supporting excerpts
earn no complete fact credit by themselves. Every baseline/agent cell has
100% fact coverage and relevance; all **16 negative responses abstain correctly**.
There are zero request failures, scope errors, attribution failures, hybrid
fallbacks or unknown-usage attempts. The scorer reports no gate failures.

This is a convenience development sample with Codex review, not independent
human annotation or holdout acceptance. Literal quotation validity alone earns
no semantic credit. No holdout labels were used to tune these corrections.

| Cell | Baseline p95 | Agent p95 | Unchanged limits |
| --- | ---: | ---: | --- |
| BM25 / JSON | 3.52 s | 10.20 s | 10 s / 20 s |
| BM25 / SSE | 2.67 s | 9.74 s | 10 s / 20 s |
| Hybrid / JSON | 6.44 s | 10.45 s | 10 s / 20 s |
| Hybrid / SSE | 3.41 s | 11.27 s | 10 s / 20 s |

The post-run audit preserves **520 protected paths**, all 15 retained container
IDs/images/states, five running/no extras, 58 papers/2,775 chunks and installed
model digests. API8000 remains available; API8002 is closed. Global HF, agent and
Telegram remain false. All source/corpus/model/label preservation checks pass.
Minimum sampled paper-request RAM was **1,739.98 MiB**. Admission had passed at
2,193.96 MiB after earlier zero-call checks rejected lower available RAM; no
threshold was lowered. Rolling pacing completed the previously failing job 63
and the final job without a quota rejection or retry.

The accepted development selection lock is in
`tests/test_output/hf-cerebras-paced-development-live-20261016-01/selection-lock.json`,
byte SHA256 `9ddebd299671abfe932f225c1aaf2a9df172a6863d833afa8cccc0b71a09335e`.
It binds the current source, full reviewed result and funding evidence. Collection,
qualification, records, completion, reviews, score and selection report remain
in that run directory. Exact approval, preflight, semantic review and final
preservation/accounting audit are in
`tests/test_output/hf-cerebras-paced-development-execution-20261016-01/`.

All 1,386 source tests, zero skips, Ruff and mypy127 remain passing; source is
unchanged since those checks. Full testing is not repeated for these result-only
documentation changes. Next is the separately funded complete 192-job holdout,
described in [hf-cerebras-paced-holdout-execution.md](hf-cerebras-paced-holdout-execution.md).
No application acceptance lock or activation is created from development alone.
