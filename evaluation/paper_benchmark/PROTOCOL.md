# Paper benchmark protocol v1

Fixed before any model call. It restates the measurement rules of the
[spec](../../docs/specs/paper-benchmark.md); `manifest.json` freezes this file
with [papers](papers.v1.json), [questions](questions.v1.json) and
[models](models.v1.json). The runner refuses to start if any of them changes.

## Data

- 30 arXiv papers, 5 per field (ML/NLP, medicine, physics, biology,
  economics/finance, systems), each cross-listed in an AI category the app
  accepts. 12 development papers (2 per field), 18 holdout papers (3 per field).
- CC BY, CC BY-SA or CC0 licenses, except 2510.26807, which stays in
  development unpublished.
- Per paper: L (first lesson), Q1 (number/table), Q2 (method), Q3 (not answered
  by the paper). Q1/Q2 carry 1–3 English reference facts, each with a quote that
  code verifies inside the named parsed block. Each Q3 records search terms that
  are absent from the parsed text.
- Authorship: questions and references were drafted by the coding assistant from
  the parsed text, verified by code, and spot-checked by the owner (20
  questions, at least 3 per field). This is not an independent annotation study.

## Runs

- One session per paper per model, jobs in the order L, Q1, Q2, Q3, through the
  production `StudyService` with the model's frozen profile and prompt revision
  v7. No per-model prompt tuning.
- If L fails, Q1–Q3 are `blocked`. They count as not delivered and are left
  out of the Q-metric denominators.
- No counted call is ever retried. An interrupted job is `unknown`, and its
  calls still count.
- Stages and call ceilings per model: qualification 4 (one first lesson,
  with one retry without request options after HTTP 400/422, and one retry
  with thinking off, `chat_template_kwargs: {"enable_thinking": false}`,
  after an answer that stops unfinished); development 96;
  holdout 144. The judge: ≤2 calls per lesson and ≤5 per Q1/Q2 answer, on
  holdout only, plus ≤80 for calibration.
- Price ceiling: $40 across all stages, charged from each response's usage. A
  call without usage is charged its worst case (its input estimate plus 3,000
  output tokens).
- Development may fix only defects that affect all models equally, and is rerun
  at most once. Holdout runs once, after development is closed.

## Metrics

- **Delivered:** ready L/Q1/Q2 jobs ÷ (3 × papers); blocked jobs count as not
  delivered.
- **Format compliance:** 1 − format-failed calls ÷ calls made. A format failure
  is `study_response_invalid_or_unavailable`, `review_validation_failed`, or
  diagnostic `shape`.
- **Claims:** written, kept, and withheld by reason, from each job's review
  report.
- **Q3 decline:** Q3 jobs failed with `lesson_validation_failed` ÷ Q3 jobs that
  are neither blocked nor failed for provider or format reasons. Every Q3 with
  a kept claim is listed for owner reading.
- **Latency:** job seconds of non-blocked jobs, median and nearest-rank p95.
- **Cost:** total and per delivered job.
- **RAGAS (holdout):**
  - Faithfulness of L/Q1/Q2 answers (kept paper claims only) against the
    snippets sent to the writer;
  - factual correctness (recall) and LLM context recall of Q1/Q2 against
    the reference facts.
  - **Unfaithful** = 1 − mean faithfulness.
- **Judge calibration:** 40 claims (16 science cases plus 24 development
  claims) labelled by the owner. RAGAS enters the decision only with agreement
  ≥ 85% and Cohen's κ ≥ 0.6. Otherwise it is reported as exploratory, and the
  owner's reading of sampled kept claims replaces it.
- **Owner rubric:** 6 holdout papers (one per field) × 4 models, blind and
  shuffled. Each lesson gets two 1–5 ratings: Arabic clarity and teaching value.

## Decision (holdout only)

- **Eligible:** format compliance ≥ 95%, p95 job latency ≤ 90 s, and an
  unfaithful rate no higher than the baseline's plus 2 points.
- **Ranking:** eligible models are ranked by delivered rate, then factual
  correctness, then mean rubric, then cost per delivered job.
- **Switching:** a challenger replaces the baseline only if it gains at least
  10 points of delivered rate or 0.10 of factual correctness.
- **Reporting:** counts only, with no claim of statistical significance.
  Switching production is a separate, owner-approved change.
