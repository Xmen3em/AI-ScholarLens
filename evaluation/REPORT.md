# Retrieval and answer-quality evaluation — 2026-10-08

The initial evaluation is complete. Hybrid retrieves more of the **pre-reviewed
support** than BM25, but answer quality remains limited by lexical rejection,
one-sentence candidate selection, irrelevant model selections, and four endpoint
failures. Week 5 attribution and word-limit guards remain intact. **Phase 6 has
not started.** This is a diagnostic baseline, not broad answer-quality acceptance.

## Scope and reproducibility

24 evaluation-only questions: eight literal/paraphrase pairs, two multi-paper
questions, four related but unsupported questions, and two unrelated questions.
18 are answerable from stored source text. Seven distinct primary papers cover
agent recovery, visual entailment, video/audio generation, bilingual models,
tokenization, debate, and revocation. The old Week 5 acceptance prompts are excluded.

Labels, required facts, source excerpts and arXiv/section/chunk locators were saved
before collection in [benchmark.json](benchmark.json). Metrics and denominators
were fixed in [PROTOCOL.md](PROTOCOL.md). Every successful answer received a
separate semantic review against those facts. Reviewer: Codex source review;
there is no independent human annotation or statistical generalization claim.

The read-only runner is [evaluate_retrieval.py](../src/commands/evaluate_retrieval.py).
It made **192 serial calls**: 96 retrieval requests (24 × two modes × two k values)
and 96 answer requests (24 × two modes × two endpoints). Answer top_k=3. k counts
paper groups with up to three passages each. Retrieval at k=3 and k=5 was requested
separately because hybrid candidate depth depends on size. Timeout 240 seconds;
no client retries. Existing llama3.2:1b and nomic-embed-text were used unchanged.
Collection took 404.7 seconds. No runtime source or prompt was changed.

## Retrieval comparison

Metrics below use 18 supported questions and the frozen, non-exhaustive support
judgments. Unit recall gives each required evidence unit equal weight, and allows
alternative reviewed locators. MRR and binary nDCG rank paper groups containing
reviewed supporting passages, not title matches. Negative cases are excluded.

| Mode | k | Evidence hit | Mean unit recall | Evidence MRR | Evidence nDCG |
|---|---:|---:|---:|---:|---:|
| BM25 | 3 | 15/18 (83.3%) | 83.3% | 0.796 | 0.806 |
| BM25 | 5 | 15/18 (83.3%) | 83.3% | 0.796 | 0.806 |
| Hybrid | 3 | 17/18 (94.4%) | 91.7% | 0.917 | 0.910 |
| Hybrid | 5 | 17/18 (94.4%) | 91.7% | 0.917 | 0.910 |

All 96 retrieval requests succeeded. Every hybrid response reported actual hybrid
mode; zero embedding fallbacks. Increasing k to 5 improved none of these frozen
metrics in this run. That does not imply increasing k is universally ineffective.

**Judgment limitation:** BM25's frozen misses are undo-design-2 and both Kandinsky
queries; hybrid's is kandinsky-1. Hybrid also has half frozen unit recall for the
multi-tokenizer question. Post-collection review found complete unjudged support
for undo-design-2 and BM25 kandinsky-1, and useful alternate tokenizer evidence.
Kandinsky overviews also contain partial requested facts. These are not all true
retrieval failures. [Supplemental judgments](retrieval_adjudications.v1.json)
record locators and supporting text without changing primary scores. The small
judgment set favors detecting particular reviewed passages and is insufficient
for an exhaustive relevance or passage-recall claim. See [ERRATA.md](ERRATA.md).

## Answer quality and abstention

Coverage is the mean fraction of complete predeclared facts covered per supported
question; abstentions and endpoint failures score zero. Compound facts require
all specified details. Relevance counts excerpts that contribute to the request;
merely topical background earns no credit. Partial useful detail can be relevant
without covering a complete compound fact. Repeated useful quotes add no coverage.
Attribution/quotation validity supplies no semantic credit.

| Mode / endpoint | Strict fact coverage | Relevant excerpts | False abstentions / 18 | Paraphrase false abstentions / 8 | Failures / 24 |
|---|---:|---:|---:|---:|---:|
| BM25 /ask | 36.1% | 19/36 (52.8%) | 5 | 4 | 1 |
| BM25 /stream | 36.1% | 19/36 (52.8%) | 5 | 4 | 1 |
| Hybrid /ask | 41.7% | 23/36 (63.9%) | 5 | 4 | 1 |
| Hybrid /stream | 38.9% | 21/33 (63.6%) | 6 | 4 | 1 |

Every combination correctly abstained on all six unsupported questions: **24/24
negative attempts**, with no unsupported substantive answer. Answerability-decision
accuracy (successful substantive attempt on supported cases or correct negative
abstention; failures incorrect) was 75.0% for BM25 /ask, BM25 /stream and hybrid
/ask, and 70.8% for hybrid /stream. This decision metric does not establish that
a substantive answer is useful or complete.

False abstentions affect both UndoBench paraphrases, the Kandinsky paraphrase,
the tokenizer paraphrase, and the multi-tokenizer question. Hybrid /stream also
abstained on literal AVE, while hybrid /ask answered it from the same catalog.
Arkios's paraphrase produced substantive but irrelevant answers: false abstention
alone would miss this failure. The multi-vision answers omit DREAM; neither
multi-paper question receives complete two-paper coverage.

/ask complete-fact counts, against fixed expected facts:

| Case | BM25 | Hybrid |
|---|---:|---:|
| undo-design-1 | Error | Error |
| undo-design-2 | Abstain | Abstain |
| undo-results-1 | 2/2 | 2/2 |
| undo-results-2 | Abstain | Abstain |
| ave-1 | 1/2 | 1/2 |
| ave-2 | 1/2 | 1/2 |
| kandinsky-1 | 2/4 | 2/4 |
| kandinsky-2 | Abstain | Abstain |
| arkios-1 | 3/3 | 3/3 |
| arkios-2 | 0/3 | 0/3 |
| tokenizer-1 | 1/2 | 2/2 |
| tokenizer-2 | Abstain | Abstain |
| dream-1 | 1/2 | 1/2 |
| dream-2 | 1/2 | 1/2 |
| vera-1 | 2/2 | 2/2 |
| vera-2 | 1/2 | 1/2 |
| multi-vision | 0/2 | 1/2 |
| multi-tokenizer | Abstain | Abstain |

Hybrid /stream differs from its /ask coverage only for ave-1 (abstention).
Full judgments and rationales: [semantic_reviews.v1.json](semantic_reviews.v1.json).

## Attribution, streaming and failures

92/96 answer attempts succeeded. **All 690 citation records on successful answers**
matched the indexed chunk and the stored paper section. All substantive answer
lines passed exact excerpt-to-citation attribution. All 92 successful answers
were within 200 whitespace-separated words including markers; maximum **137**.
This verifies the conservative excerpt guards, not contextual scientific truth.

The four failures are undo-design-1 in both modes and both endpoints. /ask
returned HTTP 502 after the existing bounded retry; /stream returned HTTP 200
with a sources event followed by an error event and no done. Container logs show
selection rejection for failing the at-most-three-distinct-IDs constraint, in
both initial selections and /ask retries. The collector correctly counts SSE
errors as endpoint failures. It never counts a failed endpoint as abstention.

All 46 successful streams had one sources and one done event, no error, and joined
deltas matching the done answer. No internal selection JSON was exposed as answer
text. Among pairs where both endpoints succeeded, BM25 final answers matched in
23/23 and hybrid in 22/23; citation coordinates and effective modes matched in
all 46 pairs. Both endpoints failed on the remaining pair in each mode. The one
hybrid answer/abstention difference remains a measured model-selection limitation.

## Latency

Wall time includes failures. Median / nearest-rank p95 seconds:

| Operation | BM25 median / p95 | Hybrid median / p95 |
|---|---:|---:|
| Retrieval k=3 | 0.054 / 0.114 | 0.176 / 1.113 |
| Retrieval k=5 | 0.076 / 0.112 | 0.160 / 0.239 |
| /ask | 7.231 / 11.463 | 6.398 / 11.579 |
| /stream | 1.291 / 2.883 | 1.091 / 3.171 |

The maximum /ask latency was 85.6 seconds (BM25's first failing case); its log
reports a 60.5-second model load. The first hybrid retrieval took 12.6 seconds.
Every stream immediately followed its matching /ask request, benefiting from
warm/prompt-cache state. These are order-dependent local timings, not evidence
that streaming intrinsically accelerates generation. First-event and first-delta
timings are retained per stream. Substantive deltas arrive after buffered selection
validation, near completion, rather than as model tokens are generated.

## Diagnosed limitations and next work

- **Lexical gate:** supporting passages are supplied, but synonyms fail 60% query
  coverage. UndoBench numeric paraphrase reaches only 20%; the two-paper tokenizer
  query gives each relevant paper 7/12 = 58.3%, rejecting both. Multi-vision gives
  DREAM 5/9 = 55.6%, eliminating one required source even though it was retrieved.
- **Candidate selection:** selecting only one sentence per passage loses distinct
  requested details. AVE literal offers accuracy but not the learned classifier;
  its paraphrase offers the classifier but not accuracy, from the same abstract.
  Kandinsky's BM25 introduction contains all requested facts, but its candidate
  retains model sizes and loses duration/sample rate. Arkios's paraphrase drops
  the requested numbers despite retrieving the supporting abstract.
- **Sentence filter:** DREAM's 76-word abstract mechanism sentence is excluded by
  the 55-word ceiling. Shorter selected statements describe the mechanisms but
  omit explicit multi-resolution probing, so that compound fact gets no full
  coverage credit. No false abstention was isolated solely to the seven-word
  minimum. UndoBench's numeric sentence is 50 words and is admitted; the original
  58-word review-note hypothesis was incorrect and is explicitly corrected in
  ERRATA.md without changing frozen labels.
- **Model selection:** the 1B selector often fills three slots with background or
  other-paper quotations, sometimes selects embedded corpus prompt instructions,
  rejects a useful AVE catalog in streaming, and produces invalid selections on
  the UndoBench sizing question. These observations do not prove a larger model
  alone would fix quality: several required facts never reach the selector.
- **Retrieval/context:** some requested evidence remains absent or partial, and the
  12,000-character budget drops passages in several catalogs. Inspected severe
  answer failures frequently already have useful source support in the actual
  context, so they cannot be attributed solely to retrieval or index repairs.

Per-case evidence and diagnosis: [diagnoses.v1.json](diagnoses.v1.json). No guard
was weakened, prompt tuned, model replaced, or larger model downloaded. Before
changing runtime behavior, create separate development examples for paraphrase
eligibility, preserving multiple facts per passage, and selecting fewer irrelevant
excerpts. Validate fixes on those examples; treat later reuse of this now-inspected
benchmark as regression measurement, and reserve fresh unseen cases for quality
claims. Expanded source judgments also need a new explicit benchmark version.

## Preservation and verification

Before/after full paper and chunk content fingerprints match. The corpus remains
58 papers, 57 chunkable, 2,775 v2 chunks; alias paper-chunks points to v2. Preserved
v1 remains 1,221 chunks. Kandinsky remains processed with 116 chunks; withdrawn
2608.30076v2 remains chunkless. All **73 pre-existing runtime/prompt and selected
Week 5/repair-test source fingerprints** are unchanged. No commit, push, merge,
ingestion, PDF parse, repair, reindex, model download, service rebuild or restart ran.

Final checks: **363 passed, 32 integration tests skipped**, zero test failures;
Ruff and mypy passed for new tooling. Six evaluation regressions cover evidence
coordinates/denominators, SSE failure handling, attribution-versus-relevance
separation, failure-versus-abstention accounting, and stale semantic reviews.
The existing integration skips were retained; no tests were disabled for this work.

Machine-readable summary: [results.v1.json](results.v1.json).
Raw responses/SSE, candidates, timings, corpus snapshots, metadata, semantic reviews
and preservation audit: [run-v1](../test_output/retrieval_eval/run-v1/).
Container error diagnostics: [api-evaluation.log](../test_output/retrieval_eval/api-evaluation.log).
Raw outputs are ignored local artifacts. Dataset, reviews, runner, tests and this
report are saved as project files. README marks the initial Phase 4 evaluation
complete with limitations; Phase 6 remains planned pending this results discussion.
