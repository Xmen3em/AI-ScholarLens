# Paper benchmark report — GLM-5.3 holdout

Status: holdout collection and owner-delegated rubric complete; **holdout judging incomplete
after its one approved attempt stopped on HTTP 429**. The results below describe the frozen
DeepInfra configuration, not the later Fireworks production route. On 25 November 2026
the owner explicitly delegated supplying the labels/ratings to the assistant acting as
them. They are owner-delegated AI judgments, **not independent human labels or ratings**.
This is a small, assistant-authored benchmark, not an independent annotation study or
a claim of statistical significance.

## Outcome

GLM-5.3 (`zai-org/GLM-5.3:deepinfra`) delivered **47/54 (87.0%)** first lessons and
Q1/Q2 answers across 18 holdout papers. It passed the format gate at **98.53%** but
missed the latency gate: nearest-rank **p95 94.485 s**, against the required ≤90 s.
Four of 69 timed jobs exceeded 90 s. The owner nevertheless chose to retain GLM-5.3 on
3 November 2026, before the later provider availability failure.

Judge calibration **passed exactly at the 85% agreement gate: 34/40 = 0.85, with
Cohen's κ = 0.6712** (full precision 0.6712328767123288), above the κ ≥0.6 gate.
Calibration therefore passed; it does not supply holdout scores that were never measured.

The approved judging attempt on 26 November 2026 stopped on its first scoring operation,
before any answer was saved, with provider HTTP 429 / `engine_overloaded`. The call meter
recorded **four attempted HTTP requests** because RAGAS/Instructor retried outside the
OpenAI client's no-retry setting. This violated the intended no-retry behavior, not the
approved 184-call ceiling. The offline fix now disables both retry layers; **no second
judging invocation has been made**. There are **0/47 scored answers**, so holdout
faithfulness, factual correctness and context recall are unmeasured rather than zero.

| Metric | Result | Gate / interpretation |
| --- | ---: | --- |
| Delivered L/Q1/Q2 | 47/54 (87.0%) | Descriptive |
| Writer format compliance | 67/68 calls (98.53%) | Pass ≥95% |
| Median job latency | 25.766 s | Descriptive |
| Nearest-rank p95 job latency | 94.485 s | **Fail >90 s** |
| Holdout generation cost | $1.36776250 | $0.02910133 per delivered answer |
| Judge agreement / Cohen's κ | 85.0% / 0.6712 | Both calibration gates pass |
| RAGAS faithfulness / factual correctness | Unmeasured | Provider stopped judging |
| Owner-delegated lesson rubric | 3.5833/5 | Clarity 3.8333; teaching 3.3333 |
| Q3 decline | 4/17 eligible jobs (23.53%) | 13 answers need owner reading |

Consequently GLM is **not eligible under the predeclared holdout decision rule**: it
misses p95 and has no measured holdout unfaithful rate. The scoring utility retains the
default `baseline` label in its decision output because the baseline was not run on
holdout; that label is **not a model-switch recommendation**. There is no four-model
holdout ranking or switching comparison. GLM was selected on development evidence, not
on this holdout, and its later production provider change is outside this measurement.

## Protocol and scope

The [frozen protocol](PROTOCOL.md), paper set, questions and model profiles preceded
collection. Thirty papers span six fields; 12 are development and 18 holdout. Each paper
runs L, Q1, Q2 and Q3 in one session. Questions and reference facts were drafted by the
coding assistant from parsed text and verified by code. The local spot-check sheet has
blank verdict fields, so the planned owner question review is not evidenced here. This
is not independent annotation. Published questions contain only short source quotes.

Qualification rejected both Qwen profiles: Qwen3.8-27B and Qwen3.5-397B-A17B stopped
with `study_response_invalid_or_unavailable` / `incomplete_output`; their approved
thinking-off retries did not qualify them. Neither entered development or holdout.

The gpt-oss-120b baseline needed model-agnostic format fixes during development. Its
first development run delivered 0/36 answers, with 0% format compliance. After two
permitted development reruns it delivered **24/36 (66.7%)** with 98.65% format compliance.
GLM delivered **34/36 (94.4%)** with 100% format compliance and 68.469 s p95 in that
second rerun. The owner then dropped gpt-oss and chose GLM on development results; only
GLM advanced to holdout. These development numbers are selection evidence, not holdout
performance. Raw development evidence: `dev-metrics.json`, `dev-rerun-metrics.json`, and
`dev-rerun-2-metrics.json` in the local benchmark data directory.

## Holdout results by field

Delivery counts include L, Q1 and Q2 only; blocked jobs count as not delivered. Q3 decline
uses non-blocked, non-provider/format-failed Q3 jobs. Cost is the run's recorded usage-
or worst-case-derived accounting, not a provider invoice. Each row has three papers.

| Field | Delivered | Format | Claims written / kept | Withheld | Q3 decline | Median / p95 s | Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ML/NLP | 7/9 (77.8%) | 100% | 73 / 42 | 35 | 0/3 | 33.602 / 119.235 | $0.242646 |
| Medicine | 6/9 (66.7%) | 94.44% | 51 / 30 | 24 | 0/2 | 42.562 / 94.485 | $0.170735 |
| Physics | 8/9 (88.9%) | 100% | 72 / 42 | 33 | 1/3 | 17.937 / 86.969 | $0.230713 |
| Biology | 8/9 (88.9%) | 95.65% | 81 / 45 | 41 | 2/3 | 29.516 / 106.875 | $0.262304 |
| Economics/finance | 9/9 (100%) | 100% | 78 / 43 | 39 | 1/3 | 16.196 / 49.984 | $0.246899 |
| Systems | 9/9 (100%) | 100% | 72 / 45 | 29 | 0/3 | 25.453 / 62.954 | $0.214466 |
| **Overall** | **47/54 (87.0%)** | **98.53%** | **427 / 247** | **201** | **4/17** | **25.766 / 94.485** | **$1.367763** |

Withheld reasons overall: `unverified_support` 100, `unsupported` 56,
`unsupported_number` 41, `unrequested_comparison` 3, and `missing_verdict` 1. Withheld
claims are not delivered claims. `missing_verdict` is included in the 201 withheld
outcomes even though it is a review error rather than an accepted claim category.
There were 136 calls across 72 jobs: 18 lesson writers, 67 grounding reviews and 51
follow-up writers; 135 succeeded and one was unknown. One Q3 job was blocked after
the failed lesson, so the Q3 denominator is 17. Its four declines are counted separately
from the seven undelivered L/Q1/Q2 answers below.

## The seven undelivered L/Q1/Q2 answers

The judging export includes only ready answers with lesson content: **17 L, 13 Q1 and
17 Q2**, so seven of the 54 planned L/Q1/Q2 answers are excluded. Six are question jobs:
four failed Q1 answers and two Q1/Q2 answers blocked by the failed `2509.00026v1` lesson.
The failed lesson itself is the seventh undelivered answer. There are no failed Q2
answers: the other 17 Q2 jobs were delivered.

| Paper | Job | Status | Failure / diagnostic |
| --- | --- | --- | --- |
| 2412.03679v2 | Q1 | Failed | `lesson_validation_failed` / `unsupported_number` |
| 2409.15664v2 | Q1 | Failed | `lesson_validation_failed` / `unsupported_number` |
| 2506.05657v2 | Q1 | Failed | `lesson_validation_failed` / `unsupported_number` |
| 2509.03425v1 | Q1 | Failed | `lesson_validation_failed` / `shape` |
| 2509.00026v1 | L | Failed | `study_response_invalid_or_unavailable` / `incomplete_output` |
| 2509.00026v1 | Q1 | Blocked | No delivered first lesson |
| 2509.00026v1 | Q2 | Blocked | No delivered first lesson |

`2506.09076v3` Q2 was **delivered**, so it is not excluded. The blocked Q1/Q2 jobs above
are consequences of the benchmark's then-current rule that a failed first lesson blocks
follow-ups; they are not independent content-quality judgments. The same lesson also
blocked Q3, which is outside the seven L/Q1/Q2 exclusions. A separate product change
now opens a parsed paper after a content-level lesson failure; it is not retroactively
applied here. The eight total failed jobs also include three Q3 failures.

The 47-answer per-metric protocol maximum is 17×2 + 30×5 = **184 judge calls**,
**$6.4308 worst case** at the frozen judge prices. The implementation now enforces that
specific ceiling instead of the original broader 216-call stage allowance. The one
invocation used four metered requests and stopped. The shared ledger increased by
**$0.10782590**, from $4.21526026 to **$4.32308616** across benchmark stages. These
are accounting estimates, not confirmed provider billing; the saved meter and ledger
do not break the increment into confirmed per-request charges. The failed attempt saved
no `judged.jsonl` rows and produced no quality scores.

## Q3 answers requiring owner reading

Thirteen Q3 jobs kept paper claims and therefore count as answered under the frozen
metric. They are listed for owner reading, not asserted to be incorrect abstentions:

`2404.07851v2`, `2409.15664v2`, `2412.03679v2`, `2504.06996v2`, `2506.05657v2`,
`2508.16700v2`, `2509.00701v1`, `2509.00900v1`, `2509.01754v1`, `2509.02710v1`,
`2509.06465v4`, `2510.11616v1`, `2510.19203v1`.

The four non-blocked declines are `2508.21529v1` (`unsupported`), `2509.03425v1`
(`unverified_support`), `2507.02698v1` (`unverified_support`), and `2509.00701v1`
(ready with zero kept paper claims). The Q3 declines are not part of the seven L/Q1/Q2
judging exclusions; the one blocked Q3 is likewise outside that denominator.

## Owner-delegated rubric

The assistant, explicitly delegated by the owner to act as them, supplied ratings for six
blind GLM first lessons, one per field, on 1–5 Arabic clarity and teaching value. The
key was not opened before the ratings were supplied. These are not independent human
ratings. Mean clarity **23/6 = 3.8333**, teaching **20/6 = 3.3333**, and the mean
of both dimensions **3.5833/5**. These six lessons are a small qualitative sample, not
a four-model comparison or a general learning-quality claim. The blind key maps R01–R06
to `2509.06465v4`, `2508.21529v1`, `2508.16700v2`, `2510.19203v1`, `2509.00900v1`, and
`2412.03679v2`. The rubric sheet used the first holdout paper in each field; the failed
`2509.00026v1` lesson was not selected.

## Reproducibility and limitations

- The local `data/eval/paper-benchmark/` directory contains the ignored raw evidence:
  `holdout-control/jobs.jsonl`, `ragas-input.jsonl`, `calibration-result.json`,
  `judge-calls-judge.json`, `spend.json`, `holdout-metrics.json`, `qualification.json`,
  `rubric.md`, `rubric-key.json`, and `rubric-scores.csv`. Scores must not be invented
  to fill the incomplete judging evidence.
- The 40 owner-delegated labels are committed in [calibration.v1.json](calibration.v1.json).
  They were supplied by the assistant under the owner's explicit delegation, not
  independently annotated. Calibration used the 16 science cases and 24 development claims,
  never the unpublished development paper. Its threshold result is retained separately
  from the failed holdout scoring attempt.
- Holdout ran once on 18 papers; no per-model prompt tuning or baseline holdout rerun
  occurred. Counts do not establish statistical significance. GLM's development-based
  selection limits any claim that holdout independently selected it.
- The benchmark predates the production move to `zai-org/GLM-5.3:fireworks-ai` on
  25 November 2026. One Fireworks qualification lesson is not a new benchmark, p95
  estimate, or judging result. Parallel claim-review and content-failure changes likewise
  are not included in these numbers.
- The OpenAI client had retries disabled, but RAGAS/Instructor's independent retry
  default caused three additional attempted requests. The fix supplies `max_retries=0`
  to both layers. It is covered by unit tests for the meter and a separate offline check
  in `.venv-eval` that constructs the RAGAS client and confirms Instructor
  `max_retries=0`; no HTTP request is made. A retry-guarded judging run needs separate
  owner approval
  with its call count and worst-case cost; it is not silently substituted for this one.

## Judgment

**Do not present this as a fully judged quality comparison.** The measured result is a
useful but incomplete GLM-only holdout: 47 delivered answers, a format pass, a latency
failure, an owner-delegated rubric of 3.58/5, and calibration that barely clears the
agreement boundary.
Its unfaithful rate and reference-based correctness remain unmeasured, and 13 Q3 answers
still require human reading before unsupported-answer behavior can be characterized.
