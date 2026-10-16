# HF/Cerebras development result — 2026-10-16

The approved full development comparison completed, but **development acceptance
failed**. Do not create a development selection lock, spend on holdout, or enable
the private API/bot from this run. This is a task-quality failure, with successful
provider transport and schema compatibility.

Source checkpoint `005651b`, source-map digest
`41fc2932e58fc53ecacd9bcabd83374bd92fa989ca0c5eb3704b4f04192d65c0`;
profile `hosted-cerebras-tokenized-v2`, manifest
`92ec9996534e5a958d4ead38fa9224b83ce6c3a318ca3919d886decaeba2558d`;
model `openai/gpt-oss-120b:cerebras`. Source stayed unchanged throughout collection,
review and scoring. No application source was changed in this execution session.

## Authorization and accounting

The user explicitly answered **“Approve up to 261 additional calls”** to the
corrected, source-bound development scope. This was one allowance replacing the
older pending requests. Exact question/answer and approved receipt are retained in
`tests/test_output/hf-cerebras-tokenized-development-execution-20261016-01/`.

- Five fresh schema checks passed: scope, relevance, rewrite, selector-1 and
  selector-10. The oversized 30-candidate schema rejected locally.
- All 64 planned jobs completed: eight cases × BM25/hybrid × JSON/SSE ×
  baseline/LangGraph agent.
- **97 additional calls used**: five qualifications, 28 baseline calls and 64
  agent calls. All 97 reservations settled as used; zero uncertain/unknown usage.
- The earlier 28 used attempts remain unchanged: **125 total attempts used**.
- **164 of the approved ceiling remain unspent.** This completed source-bound
  grant cannot be replayed or redirected to a changed prompt/source, another
  development run, holdout, or runtime activation. No ledger was reset or repaired.
- Known usage cost at the checked profile rates: **USD 0.04131235**; an estimate
  from returned usage, not a provider invoice.

## Reviewed result

All 64 requests passed transport, attribution, resource and accounting checks;
no hybrid fallback occurred. Codex reviewed all 32 substantive responses and 48
validated excerpts against the frozen questions/facts. Eight excerpts were
irrelevant to the requested fact. These are explicitly AI reviews, not human
reviews. Abstentions receive no fact-coverage credit.

Each of the four mode/transport comparisons produced the same quality metrics:

| Measure | Baseline | LangGraph agent |
| --- | ---: | ---: |
| Required-fact coverage on answerable questions | 66.7% | 33.3% |
| Mean response excerpt relevance | 80.0% | 66.7% |
| False abstentions per eight-job cell | 1 | 3 |
| Correct abstentions on the two negative cases | 2 | 2 |

The score fails `in_scope_question_rejected_by_scope` and
`regression_or_empty_relevance` for all four cells. There are 12 incorrect scope
rejections: the two robot-experiment cases and the unsupported energy question,
each repeated across four mode/transport cells. The energy question should be
in scope but unsupported; its final abstention is correct for the wrong reason.

## Offline diagnosis and next engineering work

The trace and reconstructed candidate catalog support two distinct findings:

1. The controller asks only whether the question concerns “AI/ML research papers.”
   The corpus's actual fixed category policy includes `cs.RO` (robotics), along
   with its other AI categories. Its scope instruction needs that domain context
   and must distinguish topic membership from whether a requested fact is present.
   This identifies an instruction mismatch; it does not prove a replacement prompt
   will improve the model without a fresh evaluation.
2. The current one-sentence-per-passage ranking loses answering evidence before
   selection. For the literal benchmark question, it offers sentences about the
   web application, adding models and modifying lists, omitting the task names.
   For the clustering paraphrase, it offers algorithm descriptions instead of
   the two evaluation indexes. The answer-bearing paper passes the existing
   lexical admission check in all four inspected catalogs; these cases concern
   sentence ranking/availability.
   The final model cannot select a correct sentence that the server omitted.

Next, correct scope instructions and improve bounded candidate availability
offline. Keep exact quotations, original labels, quality gates, schema/input/work
bounds and RAM limits. Rehearse the affected actual catalogs without HF first;
avoid spending on prompt tuning while the required evidence is absent. Preserve
this failed run and all ledgers. Freeze and seek approval for a concrete fresh
live scope only after the correction is reviewable. No holdout proposal or new
live allowance is prepared or authorized by these findings.

## Preservation and evidence

All **382 protected files** match, including private configuration, pairing,
historical receipts/ledgers, frozen evaluation files, tokenizer data and recovery
artifacts. All **15 retained container IDs/images/states** match, five running,
with no extra containers. The original API8000, **58 papers/2,775 chunks** and
installed model digests are preserved. Global HF, agent and Telegram flags remain
false; API8002 is not listening. No bot polling or Telegram messages occurred.
The holdout ledger and registration remain absent.

Evidence lives under ignored local directories:

- Run: `tests/test_output/hf-cerebras-tokenized-development-live-20261016-01/`:
  `metadata.json`, `qualification.json`, `records.jsonl`, `completion.json`,
  `review-template.json`, `reviews.json`, `score.json`,
  `offline-candidate-diagnosis.json`.
- Execution: `tests/test_output/hf-cerebras-tokenized-development-execution-20261016-01/`:
  `confirmation.json`, `approval.json`, `preflight.json`, before/after protected
  hashes and container inventories, `preservation-after.json`.
- Fixed grant:
  `tests/test_output/hf-cerebras-development-allowance-20261015/allowance.sqlite3`
  and its `.registered` marker. Preserve both; never bootstrap missing state.

The already-passed 1,323-test source suite, Ruff and mypy remain the source
verification. No code changed, so they were not rerun. Live collection, semantic
scoring, catalog reconstruction and preservation checks are the new verification.
