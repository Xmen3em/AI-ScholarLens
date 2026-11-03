# paper-benchmark: multi-paper evaluation and model bake-off

Status: approved 3 November 2026; implementation in progress
([plan](../../tasks/paper-benchmark-plan.md)). Amended while planning: the AI-scope
rule, the license exception, four qualification calls per model, and the judge's path.
Amended after the first qualification run (3 November 2026, before development):
qualification also retries once with thinking switched off after an unfinished answer.
Inherits [shared rules](researcher-app.md) and measures
[paper-tutor](paper-tutor.md) with the [claim check](claim-check.md).
Production ran `openai/gpt-oss-120b:cerebras` until the owner chose GLM-5.3 after
development (3 November 2026; see §6).

## Why

Every prompt fix, fixture and science case so far came from one paper,
arXiv 2005.11401 (RAG). On 3 November 2026 the owner's first other paper,
2510.26807 (diabetes lifestyle medicine with reinforcement learning), failed all
three first-lesson attempts with `unsupported_number`, and the failed lesson left
no active paper, so the learner could not even ask a question. The tutor has
never been measured on a second paper, a second field or a second model.

Goal: a public, reproducible answer to "how often does ScholarLens teach a new
paper correctly, and which hosted model does it best", good enough to publish in
the README and to drive the next product decisions.

## Decisions (proposed, owner to confirm in review)

- 30 arXiv papers, 6 fields, frozen before any model call; 12 development and
  18 holdout.
- Four models: the current baseline, two Qwen models and one non-Qwen control,
  each on a provider that enforces strict JSON schema.
- Three judges of quality: the app's own deterministic measurements (free),
  RAGAS 0.4.3 with a calibrated judge model, and a small blind owner rubric.
- Every model call needs owner approval per stage, with a call ceiling and a
  price ceiling recorded before the stage runs.

## 1. Paper set

Fields, five papers each: machine learning and NLP; medicine and health;
physics; biology; economics and finance; computer systems and networking.

Selection rules, applied in this order and recorded per paper:

0. At least one arXiv category the app accepts (`AI_CATEGORY_ALLOWLIST`), since
   the intake rejects anything else; the fields are therefore AI applied to each
   domain (for example ML for biology), not the pure domain.
1. License CC BY, CC BY-SA or CC0 (from arXiv metadata), so questions and short
   reference quotes may be published in this repository.
2. Native text extraction succeeds with the current parser revision, at most
   40 pages; the PDF SHA256 and parser revision are frozen in the manifest.
3. Per field: at least one paper whose main result is a table, and at least one
   whose method is mainly equations.
4. 2510.26807 is in medicine (development set, since it was already seen). Its
   arXiv license is not CC, so it is the one unpublished paper: its questions live
   in an ignored private file and only aggregates mention it.
   2005.11401 is excluded from both sets: the system was tuned on it.

Split: two papers per field go to development (12), three to holdout (18),
chosen before any run. Holdout outputs are produced once, after development is
closed, and reported as they come out.

## 2. Questions and references

Per paper, four jobs, all through the real `StudyService` path:

| Job | Text sent | Reference |
| --- | --- | --- |
| L | the arXiv ID (first lesson) | none |
| Q1 | a number/table question in Egyptian Arabic naming the metric and setting | 1–3 reference facts |
| Q2 | a method question ("إزاي ...") | 1–3 reference facts |
| Q3 | a plausible question the paper does not answer | "not in paper" |

A reference fact is one English sentence plus the exact quote that supports it.
Code verifies every quote is a substring of the frozen parsed text after
whitespace normalization. Q3 is checked against the whole parsed text by search
for its key terms and recorded with that search.

Authorship is stated honestly in the report: questions and references are drafted
by the coding assistant from the parsed text, verified by code, and spot-checked
by the owner (at least 20 of the 90 questions, all fields). This is not an
independent annotation study.

## 3. Model profiles

`StudyModel` stops hard-coding one model. A frozen `ModelProfile` carries:

```text
ModelProfile { route: "org/model:provider", input_estimate: gpt_oss_tokenizer | utf8_bytes_div_3,
               request_options: {…}, price_in_usd_per_m, price_out_usd_per_m, priced_on: date }
```

- The default profile is today's exact request; production behaviour is
  unchanged (same payload, same tokenizer admission, same limits).
- Models without a local tokenizer use `ceil(utf8 bytes / 3)` as the input
  estimate against the same 20,000-token admission limit. This over-estimates
  both English and Arabic, so it only refuses early, never admits too much.
- `request_options` holds per-model request fields (for example whether
  `reasoning_effort` is sent, or a provider's switch to disable thinking).
  They are fixed by the qualification stage below and frozen with the profile.
- Prices are copied from the HF router model list on the run date.

Candidates (router list, 3 November 2026; all report structured output support
on the named provider):

| Profile | Route | $/M in / out |
| --- | --- | --- |
| baseline | `openai/gpt-oss-120b:cerebras` | 0.35 / 0.75 |
| qwen-27b | `Qwen/Qwen3.8-27B:deepinfra` | 0.20 / 2.50 |
| qwen-397b | `Qwen/Qwen3.5-397B-A17B:deepinfra` | 0.45 / 3.00 |
| control | `zai-org/GLM-5.3:deepinfra` | 0.90 / 4.00 |

`Qwen/Qwen3.8-2.4T-A95B` is excluded: no provider offers strict structured
output for it. All models use the same prompt revision (v7); there is no
per-model prompt tuning.

## 4. Stages and budget

Each stage needs the owner's explicit approval at the time it runs. The runner
refuses to start without `--execute`, a frozen manifest hash, free memory of at
least 1,024 MiB, and a call ceiling written into its own SQLite store
(`data/eval/paper-benchmark/<run>/state.sqlite3`, never the bot's store). Runs
are sequential, resumable by job, and never retry a counted call.

| Stage | Calls (ceiling) | What it decides |
| --- | --- | --- |
| Q: qualification | 4 per non-baseline model (12): one first lesson, one retry without options after HTTP 400/422, one retry with thinking off (`chat_template_kwargs: {"enable_thinking": false}`) after an unfinished answer | strict schema honoured; request options |
| D: development | 12 papers × 4 jobs × ≤2 calls × 4 models (384) | fix model-agnostic defects only |
| H: holdout | 18 × 4 × ≤2 × 4 (576) | the reported numbers |
| J: judging | holdout answers only: ≤2 per lesson, ≤5 per Q1/Q2 answer, 4 models (864), plus calibration (≤80) | RAGAS scores |

A qualification failure removes that model from the bake-off; it is reported,
not worked around. Development may change code that affects all models equally
(for example a profile option or a parser bug), after which development is rerun
once. Amended 3 November 2026: a second rerun is allowed, because the first
rerun's fix to the lesson-format rule was checked against one gpt-oss draft and
missed the other ways it breaks the rule (11 of 12 first lessons still failed).
Nothing changes after holdout starts.

Each paper runs as one session per model, in the order L, Q1, Q2, Q3, so
follow-ups see the same dialogue context a student would. Today a failed first
lesson leaves no active paper; the runner then records Q1–Q3 as `blocked`, counts
them as not delivered, reports them separately, and leaves them out of the
Q-metric denominators. It does not work around the product rule.

Estimated cost from the prices above: about $20 for all stages; the hard
ceiling is $40, checked from each response's usage before the next call.
Inference is billed to the owner's HF account.

## 5. Measurements

### App measurements (no extra calls)

Per model, from stored job results and attempts:

- delivered rate: jobs L, Q1 and Q2 that returned a lesson;
- failure codes and stages for the rest;
- writer format compliance: calls that parse against the schema;
- claims written, kept, and withheld by reason;
- Q3 decline rate: Q3 jobs with zero kept paper claims; every Q3 job with a kept
  claim is listed in the report for owner reading;
- job latency median and nearest-rank p95; tokens and cost per delivered lesson.

### RAGAS (separate environment)

RAGAS and its dependencies run in their own `.venv-eval` (`ragas==0.4.3`),
reading the runner's exported JSONL; the bot never imports them. Metrics, all
LLM-judged, no embeddings:

- Faithfulness on L, Q1 and Q2: the answer's statements against the snippets
  that were actually sent to the writer.
- Factual correctness (recall mode) on Q1 and Q2 against the reference facts.
- LLM context recall on Q1 and Q2: whether `select_evidence` supplied the
  reference quotes. This separates retrieval misses from writing errors.

Judge: `deepseek-ai/DeepSeek-V4-Pro:deepinfra`, not a candidate, so no model
grades itself. Before RAGAS numbers are trusted, the judge's faithfulness
verdicts are compared with owner labels on 40 claims (the 16 science cases plus
24 claims sampled from development runs, Arabic claim and English source shown
side by side). If agreement is below 85% or Cohen's kappa below 0.6, RAGAS
results are reported as exploratory and do not enter the decision rule.

### Owner rubric

Six holdout papers (one per field) × four models = 24 first lessons, shuffled,
model names hidden. Two 1–5 ratings each: Arabic clarity for a student, and
teaching value (does it explain the paper's idea). About one hour of owner time.

## 6. Decision rule

On holdout only. A model is eligible if:

- writer format compliance ≥ 95% of its calls;
- p95 job latency ≤ 90 seconds;
- unfaithful kept claims (calibrated judge, or owner reading if the judge failed
  calibration) no higher than the baseline's rate plus 2 percentage points.

Eligible models are ranked by delivered rate, then factual correctness, then
mean owner rubric, then cost per delivered lesson. A challenger replaces the
baseline only if it beats it by at least 10 points of delivered rate or 0.10 of
factual correctness. Otherwise the baseline stays, because it is the fastest
and cheapest. With 18 holdout papers the report states counts and makes no
claims of statistical significance.

**Owner decision, 3 November 2026, after development.** The owner dropped
gpt-oss-120b and switched production to GLM-5.3 (`zai-org/GLM-5.3:deepinfra`) on
the development results. In the second development rerun GLM-5.3 delivered 94% of
36 answers with 100% format compliance and a 68 s p95; gpt-oss-120b delivered 67%
with thin lessons (a median of 2 kept claims per first lesson against GLM's 9.5).
Both Qwen models had failed qualification. The holdout therefore measures GLM-5.3
alone (≤144 calls; judging ≤216): it must meet the format and latency gates above,
and its unfaithful rate is reported as measured, not against a baseline. The report
states that the model was chosen on development data.

Switching the production model is a separate, owner-approved change. If one
model writes best and another checks best, a writer/checker split is proposed
as a follow-up, not decided here.

## 7. Files

| Path | Content |
| --- | --- |
| `evaluation/paper_benchmark/PROTOCOL.md` | this measurement plan, frozen with hashes |
| `evaluation/paper_benchmark/papers.v1.json` | 30 papers: ID, version, field, split, license, SHA256, parser revision |
| `evaluation/paper_benchmark/questions.v1.json` | 90 questions with reference facts and quotes |
| `evaluation/paper_benchmark/models.v1.json` | four profiles plus judge, prices and date |
| `evaluation/paper_benchmark/REPORT.md` | results, per field and overall; failures listed |
| `src/services/study/models.py` | `ModelProfile` and the default profile |
| `src/commands/evaluate_study.py` | runner: plan by default, `--execute` per stage |
| `src/commands/score_study.py` | app measurements and JSONL export |
| `src/commands/judge_study.py` | RAGAS judging, run only from `.venv-eval`; `ragas` imported lazily |

Raw outputs stay in ignored `data/eval/paper-benchmark/`. Published files carry
paper IDs, questions, short reference quotes and aggregate results, never full
paper text.

## 8. Tests (offline, zero model calls)

- The default profile produces a byte-identical request to today's for a fixed
  lesson; the existing suite passes unchanged.
- The byte estimate refuses a payload the tokenizer would refuse, on Arabic and
  English fixtures.
- Manifest checks: 30 papers, 5 per field, 12/18 split, allowed licenses,
  2005.11401 absent; every reference quote is a substring of its frozen text.
- The runner without `--execute` makes no network call; with it, it stops at
  the call ceiling, the price ceiling and low memory, and resumes without
  repeating finished jobs.
- Scoring on a stubbed run reproduces hand-computed delivered rate, withheld
  counts, Q3 decline and latency percentiles.
- The RAGAS script on two canned samples with a stubbed judge writes the
  expected rows (run in `.venv-eval` only).

## Out of scope

The Telegram presentation pass, opening the paper after a failed first lesson,
`/deep`, OCR papers, fine-tuning and self-hosting. Each gets its own change;
this benchmark is what measures them afterwards.

## Acceptance

BM-1: The paper, question and model manifests are frozen with hashes before any
call, and every reference quote is verified against its paper's text.

BM-2: Production requests are unchanged with the default profile; every
candidate runs through the same `StudyService` path with its own frozen profile.

BM-3: No stage runs without owner approval, and none exceeds its call or price
ceiling.

BM-4: `REPORT.md` gives, per model and per field, the delivered rate, claim
outcomes, Q3 declines, latency and cost; RAGAS scores with the judge's
calibration result; the owner rubric; and the decision under §6 with its reasons.
