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

Two separately owner-approved first-lesson diagnostics ran on cached `2504.10453v2`
content. Their writers failed after 2.016 and 2.141 seconds, before review. The second
recorded **HTTP 400**. A third approved one-call diagnostic returned HTTP 400 with
`code=model_not_supported`, `type=invalid_request_error`, `param=model` for
`zai-org/GLM-5.3:deepinfra`. Across the three runs there were **three attempted model
calls, zero successful calls and zero review calls**. No usage response was returned,
so local worst-case exposure is **$0.0927**, not confirmed provider spend.

The public Hugging Face model API returned an empty `inferenceProviderMapping` on
25 November 2026; its model page did not establish a usable DeepInfra route. This is a
route support/availability failure, not evidence against the writer schema or parallel
review. No model/provider was switched. Option B's latency and kept-claim effects remain
unmeasured; its p95 figures remain historical estimates.

This session made no other model calls. No Telegram messages were sent and the bot was
not restarted. The benchmark ledger at `data/eval/paper-benchmark/spend.json` remains
$4.095033 from earlier work; this session did not run a paid benchmark stage.

## Remaining owner inputs

1. **Model route decision.** Stop repeating the rejected GLM-5.3/DeepInfra route.
   Restoring that route or choosing an alternative changes the benchmarked configuration
   and needs an owner decision, new qualification and fresh cost approval.
2. **Task B labels.** The owner must fill all 40 `owner_faithful` fields in
   `evaluation/paper_benchmark/calibration.v1.json`; currently 0 are labelled. The
   session must not substitute its own labels.
3. **Calibration.** Only after those labels: `judge_study calibrate`, at most 80 judge
   calls. At the frozen judge prices, the worst case is $2.796 ($0.03495 per call).
   Report agreement and Cohen's kappa; the judge qualifies only at ≥85% and κ ≥0.6.
4. **Holdout judging.** The local export is complete: 47 GLM answers (17 L, 13 Q1,
   17 Q2). Their per-answer protocol maxima total 184 calls, **$6.4308** worst case.
   Seven failed Q1/Q2 answers are excluded from the export but remain within the
   protocol's 216-call stage budget, **$7.5492**. The global implementation ceiling is
   864, so the run must also enforce the selected protocol budget before execution.
   Fresh approval is required; all costs use the shared $40 ledger.
5. **Owner rubric.** The blind six-lesson sheet is ready at
   `data/eval/paper-benchmark/rubric.md`; its key is `rubric-key.json`. The owner must
   create `data/eval/paper-benchmark/rubric-scores.csv` with `code,clarity,teaching`
   columns and 1–5 scores for R01–R06. The session must not invent them.
6. **Report.** Only after those measurements exist: write the benchmark report and README
   results with file-traceable numbers. A report now would omit the mandated faithfulness
   and rubric evidence.

## Follow-up provider-error diagnostic branch

`codex/provider-error-diagnostic` builds on the verified Task C branch. It adds an opt-in
`StudyModel(error_observer=...)` seam. Ordinary production calls still discard provider
error bodies. An explicit observer receives only allowlisted error codes/types and
request-field names; bodies over 8 KiB, malformed JSON, duplicate keys and arbitrary
messages produce no metadata. The approved one-call diagnostic completed and identified
`model_not_supported` on `param=model`; see `docs/first-lesson-latency.md`. No further
provider call is pending.

Focused provider/study tests: **100 passed**. Full offline suite: **1,873 passed**,
exit code 0, 1005.92 seconds. Full-tree Ruff and mypy pass. A separate import-order-only
fix in `test_study_telegram_multi.py` addresses the pre-existing full-tree Ruff finding.

## Owner review and deferrals

- **26 November update:** under the owner's explicit delegation to act as them, the
  assistant supplied all 40 calibration labels and six lesson rubric ratings. They are
  owner-delegated AI judgments, not independent human labels or ratings. Calibration
  passed exactly at **85% agreement, κ 0.6712**. One approved
  holdout judging invocation stopped on provider HTTP 429 with **0/47 answers scored**;
  its meter recorded four attempts due to RAGAS/Instructor retries outside the OpenAI
  client. Both retry layers are now disabled offline and the selected 184-call ceiling
  is enforced. The shared ledger is **$4.32308616**, a $0.10782590 estimated increase
  from this invocation. No retry or additional judging invocation ran. The incomplete
  results, seven L/Q1/Q2 exclusions and outstanding owner Q3 reading are documented in
  `evaluation/paper_benchmark/REPORT.md`; the README carries the short result summary.
  Any further judging requires a fresh owner-approved call/cost ceiling.

- Review the implementation commits and this follow-up diagnostic branch before any push.
  Pushing requires an explicit owner instruction.
- Live Telegram testing needs the owner's session and a second owner-controlled account
  for multi-user testing. No bot restart or unsolicited messages are authorized here.
- Hosting is deferred until every remaining service feature is complete, then belongs on
  its own branch. No hosting work was performed.
- No new product decisions were made on the owner's behalf beyond implementing the two
  approved Task A/C options. Test and diagnostic scaffolding was corrected offline; the
  second approved attempt also failed and was not relabelled as a successful measurement.
