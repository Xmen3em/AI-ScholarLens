# Remaining-work handoff — 25 November 2026

## Local implementation complete

All work is local and unpushed. The branches were cut successively so the final branch
contains the complete result:

| Branch | Commit | Scope |
| --- | --- | --- |
| `codex/remaining-work-d` | `c46e600` | Multi-user, claim-review, accounting and benchmark cleanup |
| `codex/content-failure-open` | `1a18a84` | Open a parsed paper after content-validation failure |
| `codex/parallel-claim-check` | `1eb66df` | Two concurrent claim-review halves with preserved IDs and evidence |

Task D did not change legacy model behavior. Task A used owner option 2: only
`lesson_validation_failed` opens the parsed paper; provider/transport failures do not.
The job stays failed and costs no paper quota. Its approved reply is:

> ماقدرتش أتأكد من شرح كامل من الورقة دي، بس فتحتها. اسألني عن جزء محدد زي الطريقة أو النتائج أو جدول.

Task C used owner option B. A writer plus up to two concurrent review calls fits the
four-attempt durable budget; multi-user admission reserves three calls for lessons and
four for `/deep`. Prompts, reasoning options, proof checks and global claim IDs are
unchanged. Each review half receives only its cited blocks. No analogy-only review call
is made.

Verification on the final Task C tree:

- `tests/unit tests/api`: **1,871 passed**, exit code 0, 830.77 seconds.
- Ruff `check src tests`: passed.
- mypy `src`: passed (174 source files).
- `git diff --check`: passed.
- Focused final study/claim/transport tests: 140 passed.
- Frozen benchmark protocol, papers, questions, models and manifest were not changed.

## Live check and cost record

One owner-approved first-lesson diagnostic ran on cached `2504.10453v2` content. Its
writer failed after 2.016 seconds before review. There were **one attempted model call,
zero successful calls and zero review calls**. No usage response was returned, so local
worst-case exposure is **$0.0309**, not confirmed provider spend. The failed attempt
cannot be diagnosed further from saved state: the initial script retained only the
generic exception class. The ignored diagnostic script now preserves safe failure codes.

No retry was made. Option B's measured latency and kept-claim effects remain unknown;
the p95 values in `docs/first-lesson-latency.md` are still historical estimates. A real
p95 needs a separately approved multi-lesson run, not one sample.

This session made no other model calls. No Telegram messages were sent and the bot was
not restarted. The benchmark ledger at `data/eval/paper-benchmark/spend.json` remains
$4.095033 from earlier work; this session did not run a paid benchmark stage.

## Remaining owner inputs

1. **Option B retry (optional).** Fresh approval is required for at most three GLM-5.3
   model calls, worst case $0.0927. The diagnostic must use a new intent and new output
   file; its existing result is a run-once guard against duplicate spending.
2. **Task B labels.** The owner must fill all 40 `owner_faithful` fields in
   `evaluation/paper_benchmark/calibration.v1.json`; currently 0 are labelled. The
   session must not substitute its own labels.
3. **Calibration.** Only after those labels: `judge_study calibrate`, at most 80 judge
   calls. At the frozen judge prices, the worst case is $2.796 ($0.03495 per call).
   Report agreement and Cohen's kappa; the judge qualifies only at ≥85% and κ ≥0.6.
4. **Holdout judging.** If calibration passes, export with `score_study --stage holdout
   --export-ragas`, then judge the exported answers. The implementation allows up to 864
   calls, worst case **$30.1968** at frozen judge prices; this is the safe upper bound
   because RAGAS may make multiple provider calls per metric. The task's 216-call figure
   is not a reliable worst case and needs reconciliation with the frozen protocol before
   execution. Export locally first to inspect answer count, then obtain approval for an
   explicit call and dollar ceiling. All costs use the shared $40 ledger.
5. **Owner rubric.** `score_study --rubric-sheet` is local, but the owner must fill
   `rubric-scores.csv` for the six GLM holdout lessons. The session must not invent them.
6. **Report.** Only after those measurements exist: write the benchmark report and README
   results with file-traceable numbers. A report now would omit the mandated faithfulness
   and rubric evidence.

## Owner review and deferrals

- Review the three local commits before any push. Pushing requires an explicit owner
  instruction.
- Live Telegram testing needs the owner's session and a second owner-controlled account
  for multi-user testing. No bot restart or unsolicited messages are authorized here.
- Hosting is deferred until every remaining service feature is complete, then belongs on
  its own branch. No hosting work was performed.
- No new product decisions were made on the owner's behalf beyond implementing the two
  approved Task A/C options. Test and diagnostic scaffolding was corrected offline; the
  failed live writer was not retried or relabelled as a successful measurement.
