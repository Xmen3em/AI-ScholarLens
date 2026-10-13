# Source review and freeze record

Reviewed 2026-10-13, Africa/Cairo, before generation. Reviewer/author: Codex.
All sources are preserved stored paper sections and indexed passages, not model
outputs, title-only search matches or newly downloaded papers. No evaluation calls
have been collected. Labels describe what these papers report, not independent
verification of their scientific conclusions.

## Corpus and prior-data separation

The new read-only snapshot contains 58 papers, 2,775 v2 chunks and the unchanged
`paper-chunks -> paper-chunks-v2` alias; v1 has 1,221 chunks. Canonical digests:

- Papers: `fe1188f2bcf0a15b87585ddcc53824e909319683cf99e4c6ae4705a2f1f47c0d`
- Chunks: `240d4fbab63f8fe58447859b488c3e0379d1a8c896b6bf9c30c90f634cfe5068`

All 60 prior evaluation files are fingerprinted in the manifest. The recursive
saved-case inventory found 73 unique earlier questions and 18 support papers.
The new development and holdout questions were reviewed for close semantic overlap
with that inventory; all positive and paper-scoped-negative sources below are
outside those 18 papers. This strengthens separation from saved tuning data, but
does not prove the author has never encountered those papers or similar questions.
No holdout output may be used for subsequent implementation changes.

## Positive fact review

| Split | Paper | Reviewed claim and locator |
| --- | --- | --- |
| Development | 2610.05633v1, GenAI4IDN Benchmark 3.0 | Fact-checking and bias detection tasks/rubrics; section 1, chunk 0 |
| Development | 2610.05607v1, Emergency Obstacle Avoidance Maneuvers | 539 retained trials; speeds 45/55/65 cm/s; section 1, chunk 0 |
| Development | 2608.30093v1, Robust K-means with DPD | Median Davies-Bouldin and Trimmed Calinski-Harabasz indexes; section 2, chunk 0 |
| Holdout | 2608.30086v1, When Does a Classifier Help an LLM? | Default of Credit Card Clients dataset; bootstrap confidence intervals; abstract-reported AUC-ROC 0.72 -> 0.78; section 1, chunk 0 |
| Holdout | 2608.30081v2, Tracing Generated Samples to Training-Data Clusters | Independently retrained LOCO counterfactual validation; section 3, chunk 0 |
| Holdout | 2608.27785v1, Compositional Failure in Audio-Visual LLMs | Stronger alignment changes answer bias but does not improve conflict resolution; section 2, chunk 0; corroborated by conclusion section 18 |
| Holdout | 2608.26432v1, SpeechGym | Misheard tool arguments and pressure-induced unauthorised writes; per-turn successful-call reward; section 2, chunk 0 |
| Holdout | 2608.27448v1, TTPO | Agreeing rollouts distilled through OPSD, disagreeing rollouts penalized with Grouped RL; Qwen3-1.7B average TTT accuracy 38.0% -> 45.2%; section 2, chunk 0; average confirmed in Table 2, section 14 |
| Holdout | 2608.26442v1, Don't Overthink, Don't Underthink | MATH-500 and GAIA public validation benchmarks; section 1, chunk 0 |

The holdout uses six papers; development uses three different papers. Literal and
paraphrase pairs have identical required facts/support. This deliberate dependence
means 24 holdout cases are not 24 independent studies. The two-paper training case
requires SpeechGym successful-call reward plus both TTPO rollout branches. The
two-paper validation case requires flow-matching LOCO validation plus credit metric
bootstrap uncertainty. Partial one-paper responses do not earn full coverage.

Numeric review: the credit question explicitly asks for rounded values in the
abstract. Table II (section 14) gives 0.719 and 0.782; these are compatible with
0.72 and 0.78 at the requested precision. Correctly attributed table values may
also receive fact credit, with the rounding rationale recorded. TTPO 38.0% and
45.2% are cross-benchmark averages in Table 2, not individual AIME scores and not
relative percentage improvements. Unit/metric confusion receives no fact credit.
The development trial count is retained 539, not scheduled 540.

Source excerpts preserve PDF extraction quirks and whitespace normalization.
In particular, the adaptive-reasoning source writes "underreasoning" in its abstract;
this is not edited in the label to improve lexical eligibility. Positive labels
remain answerable even when current guards/retrieval/selection fail to expose the
facts. The long SpeechGym evidence is intentionally not shortened to suit the
existing sentence-length policy.

## Negative review

| Case | Bounded source review | Decision |
| --- | --- | --- |
| Development GenAI4IDN energy | Abstract, web application/evaluators, results, limitations, conclusion; all stored sections scanned for kWh/watts/carbon/energy | No per-narrative electrical-energy measurement is reported |
| Holdout credit ethnicity | Dataset, metric definitions, result tables, analysis and limitations; no ethnicity/demographic-parity/fairness reporting in the named paper | Requested ethnicity-wise demographic-parity gap unsupported |
| Holdout flow Apple timing | Abstract, methodology, latent-space experiments, results, discussion; no Apple/M2/millisecond/runtime reporting in the named paper | Requested Apple M2 GPU attribution time unsupported |
| Holdout TTPO energy | Abstract, experimental setup, main results, implementation details and limitations; no kWh/watts/electrical-consumption reporting | Requested kWh per training step unsupported |
| Holdout French signing | Abstract, dataset, protocol, conflict/alignment results, limitations and conclusion; no French/sign-language evaluation | Requested French Sign Language accuracy unsupported |

The JSON files record section inventories, reviewed section coordinates and both
scoped-section and whole-corpus scan hit counts. Generic energy/fairness/runtime
terms occur elsewhere in the corpus; that does not answer these named-paper
questions. Absence in scoped review is a corpus-bounded judgment, not proof that
no such measurement exists anywhere. No negative here relies on old SF-GNN,
tokenizer or other inspected regression questions.

The development picnic-menu case and holdout origami instructions, birthday-poem, phrase-
translation and geography cases request external tasks/general facts. They are
out of the AI-paper domain, even if individual words appear in paper text. No
external instruction site, translation service or web query was performed to answer them.

## Validation and reproduction

`src.commands.validate_agent_evaluation` verifies the 32 cases offline: 24 positive
support-locator checks, five recomputed paper-scoped negative reviews, split and
prior-paper/query separation, matched pair labels, source hashes and frozen files.
It tests provenance and consistency; semantic fact/negative judgments above remain
human-readable review responsibilities. SHA-256 is an audit fingerprint, not a
signature or access-control mechanism.

```powershell
.venv-win/Scripts/python.exe -m src.commands.validate_agent_evaluation --snapshot tests/test_output/week7-source-review-20261013-01
.venv-win/Scripts/python.exe -m pytest tests/unit/test_agent_evaluation.py -q
```

The full source snapshot and preparation scripts are locally ignored. The validator
can use a later read-only snapshot only if its canonical digests and recorded source
facts still match. Use the manifest as the frozen pre-run record; do not replace it
after viewing outputs. Live comparison requires the protocol's resource admission,
uncached paired baseline/agent process and pre-run preservation checks.

Pre-run correction: the original weather negative was semantically close to an
earlier Cairo forecast case. Freeze v2 replaces it with origami instructions;
`frozen-v1/` retains every first-freeze file. No model outputs were inspected.
See `ERRATA.md`.
