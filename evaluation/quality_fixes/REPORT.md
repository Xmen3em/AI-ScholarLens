# Answer-quality fixes before Week 6 — 2026-10-08

Sentence expansion improves the evidence offered to the selector, but the existing
1B model does not reliably use it. **Expansion remains opt-in; the default stays
at one sentence per passage. Week 6 has not started.** Both endpoints now use the
same buffered generation, validation and bounded retry path. Invalid selections
still fail closed; none is deduplicated or repaired.

## Changes retained

- `build_excerpts` can offer one to three ranked, whole source sentences per
  passage. Candidates must share a normalized query term. The 60% per-paper
  lexical gate, seven-to-55-word sentence filter, exact source wording/markers,
  maximum three selected excerpts and 200-word answer limit remain intact.
- `RAG_SENTENCE_CANDIDATES_PER_PASSAGE=1` is the default. Values 2/3 explicitly
  enable the experiment; 3 is measured here. Value 2 is bounded but not separately
  quality validated. Expanded mode adds complementary-fact/minimal-selection
  guidance. The default retains the original prompt wording because development
  testing found that even adding "distinct" increased false abstentions.
- Structured generation requests unique IDs; the server remains the authority
  for rejecting duplicates, unknown IDs, excessive selections and bad quotations.
  The schema hint is not proof that Ollama enforces uniqueness.
- `/stream` uses the same ordinary Ollama generation transport as `/ask`, then
  emits complete validated quotation deltas. Both routes allow at most one
  plain-ID retry for invalid selections or malformed structured selection shape.
  Empty selections are valid abstentions and do not trigger retries. Connection
  errors/timeouts are not retried. No internal model selection is exposed.

The old endpoint inconsistency was not isolated to a proven Ollama transport bug.
The two routes had different transports and retry policies; sharing the path
removes that implementation asymmetry. It does not guarantee model determinism
or semantic relevance. The small development transport probe alone showed no
normal-versus-stream difference and cannot explain the historical AVE observation.

## Development evidence

Eight synthetic cases are separate from all corpus benchmarks. Offering the two
literal passages' requested facts improved from **2/5 to 5/5**. With the accepted
expanded prompt, rendered literal coverage improved from **0/5 to 5/5**. The
two-paper classifier example retained both requested facts. Both synonym-heavy
paraphrases still abstained at the unchanged lexical gate in both endpoints.

One of three unsupported development controls, a classifier question adding an
unsupported cancer-diagnosis condition, received irrelevant topical quotations
before and after expansion and with the final conservative default. The other
two controls abstained. This is a measured contextual-relevance failure, despite
valid attribution. No lower threshold or unverified semantic replacement was
adopted. Development results do not justify broad paraphrase or abstention safety.

A more restrictive prompt initially made the model abstain even with complete
literal evidence. A two-by-two prompt/schema comparison isolated that regression
to the wording, not `uniqueItems`. That prompt was rejected. Raw development and
ablation artifacts are retained under `test_output/quality_fixes/`.

## Initial fresh holdout: expansion rejected as the default

Twelve source-reviewed questions were fixed before baseline collection: eight
supported, including two paraphrases and one two-paper question, plus four
unsupported. Four primary papers are outside the v1 primary papers. Baseline
answer bodies were not reviewed until the implementation was finalized on
development examples. Both modes/endpoints were exercised: 96 calls before and
96 after expansion, including separate retrieval at k=3 and k=5. No client retry.

Each answer was reviewed against predeclared complete facts and for quotation
relevance. Both endpoints produced identical semantic scores within each mode.

| Mode, both endpoints | Fact coverage before → expanded | Relevant excerpts before → expanded | Endpoint failures before → expanded |
|---|---:|---:|---:|
| BM25 | 41.7% → 47.9% | 11/21 (52.4%) → 8/21 (38.1%) | 0/24 → 0/24 |
| Hybrid | 43.8% → 41.7% | 8/17 (47.1%) → 8/20 (40.0%) | 2/24 → 0/24 |

Excerpt fractions in the table describe either endpoint; failure counts combine
both endpoints. All **16/16 unsupported attempts** abstained in each run. Each
combination falsely abstained on one of two paraphrases before and after; the
other hybrid paraphrase failed both endpoints before expansion and supplied a
partial answer afterward. Neither configuration completely answered the two-paper
question. Exact final answers agreed across endpoints for 23/23 successful pairs
before and 24/24 after; this holdout did not reproduce the historical AVE mismatch.

Expansion supplied SEA-LM's two-stage/six-task curriculum, recovering that fact
on its paraphrase. But it also filled slots with unrelated results, capabilities
and an unrelated paper's teacher-rollout description. The hybrid SWE-Prime
method answer fell from 3/3 complete facts to 1/3 even though the criterion
sentence remained available. BM25's top-three-per-passage ranking still excluded
the detailed screening criteria. More candidates alone do not solve ranking or
selector attention, and the no-filler prompt did not reliably reduce filler.

Judged-support hit@3/@5 remained 5/8 for BM25 and 4/8 for hybrid. These locators are
non-exhaustive, and some support units are redundant alternatives saved as separate
units. Reported unit recall in the JSON is locator-unit coverage, not exhaustive
fact-evidence recall. No retrieval-policy or index change was made.

Median / nearest-rank p95 seconds, including failures:

| Operation | Baseline | Expanded |
|---|---:|---:|
| BM25 /ask | 7.20 / 71.52 | 9.76 / 19.47 |
| BM25 /stream | 1.30 / 3.80 | 1.16 / 2.57 |
| Hybrid /ask | 4.80 / 34.49 | 6.49 / 14.22 |
| Hybrid /stream | 1.41 / 3.20 | 1.40 / 2.69 |

These are local order-dependent observations, not speedup claims. Every stream
followed its matching ask and benefited from warm model/prompt state. Expansion
increased median /ask time. Buffered streaming delivers evidence after validation,
not during model token generation.

## Final conservative default

Expansion was rolled back to an opt-in configuration after the first holdout.
Seven further questions from WikiSkill and CritICL were fixed before final live
collection; neither paper is a primary paper in the first holdout or v1. Five
questions are supported, including a paraphrase and a two-paper question; two
are unsupported. All 56 collection requests succeeded, including all 28 answer
attempts. These are different questions from the initial holdout; the scores
below are **not a before/after improvement estimate**.

| Final default, either endpoint | BM25 | Hybrid |
|---|---:|---:|
| Complete-fact coverage, 5 supported questions | 60.0% | 70.0% |
| Relevant excerpts | 8/14 (57.1%) | 8/14 (57.1%) |
| False abstentions / supported questions | 0/5 | 0/5 |
| Paraphrase false abstentions | 0/1 | 0/1 |
| Correct unsupported abstentions | 2/2 | 2/2 |
| Answer failures | 0/7 | 0/7 |

Both endpoints matched exactly for **14/14 pairs**; all 14 streams had valid event
ordering, matching joined deltas/done text and no error. All eight unsupported
attempts abstained. Both modes recovered the complete three-layer WikiSkill
mapping and persistent-wiki rule. BM25 omitted CritICL-static in the literal
comparison; both modes omitted dynamic input-specific prediction in its
paraphrase. Neither mode covered the complete two-paper facts: partial CritICL
guidance was quoted, but WikiSkill trace consolidation was absent. Thus zero
false abstentions does not mean complete or consistently relevant answers.

Judged-support hit@3/@5 was 2/5 in both modes. Alternate unjudged passages supplied
useful evidence, including complete facts in accepted answers; these small locator
judgments are not exhaustive recall. Neither mode fell back to BM25 unexpectedly.

Final-default median / p95 seconds: BM25 /ask **7.75 / 21.72**, /stream **1.49 /
3.63**; hybrid /ask **7.32 / 9.33**, /stream **2.99 / 3.28**. The same local order
and prompt-cache limitations apply.

## Inspected v1 regressions: known defects remain

The four copied v1 cases required 32 requests, including 16 answer attempts.
**UndoBench sizing still failed all four answer attempts.** Both ask requests
returned HTTP 502 after the bounded retry. Both streams returned sources then
error, with no answer delta or done. API logs record eight rejected distinct-ID
selections: initial plus retry for every attempt. The uniqueness schema hint did
not prevent these model outputs, and none was repaired to make it pass. Failed
stream latency was 15.58 seconds for BM25 and 16.18 for hybrid; sharing the retry
adds bounded generation work compared with the former no-retry stream path.

**Hybrid AVE still showed the answer/abstention inconsistency**: ask quoted the
0.803 result, whereas stream abstained on the same citation catalog. Both now use
the same generation method, prompt construction and validation policy. This
rules out the old transport difference as a sufficient explanation; the remaining
model/runtime variation is not isolated. BM25 AVE endpoints matched. Neither
answered the full learned-classifier fact with the conservative candidate limit.

The two-paper tokenizer question still abstained in both modes/endpoints at the
unchanged lexical gate; the unsupported AVE question correctly abstained in all
four attempts. Among successful regression pairs, BM25 matched 3/3 and hybrid
2/3. Neither invalid-selection reliability nor general endpoint determinism is
resolved. The final fresh-set zero failures must not be used to hide these
known failures. See [regression results](results.regression.json) and
[individual reviews](reviews.regression.json).

## Verification and preservation

The final implementation passes **377 tests**, with **32 existing integration
skips** and two existing dependency deprecation warnings. Ruff and mypy pass.
Fourteen added regressions protect bounded candidate expansion and its opt-in
wiring, exact quotations/markers, default prompt preservation, shared endpoint
behavior, unique-ID schema hints, malformed selections, bounded validated retries,
no answer delta before a rejected retry, and configuration-aware evaluation audits.
A deliberately inverted overlap filter failed seven focused tests; the file was
restored byte-for-byte. No test was disabled or weakened.

Only the local API was rebuilt/restarted, using a clean context with the unchanged
Dockerfile/locked dependencies and current source. No unrelated service rebuild,
deployment, ingestion, PDF parsing/repair, reindex, model replacement/download,
commit, push or merge was performed. Corpus/index/model and frozen-file hash audits
are saved with the raw runs; the final audit is summarized below.

## Reproducible artifacts

- [Protocol](PROTOCOL.md), [development cases](development.json),
  [development runner](development_runner.py), [initial holdout](holdout.json),
  [final holdout](final_holdout.json), [inspected v1 subset](regression.json).
- [Baseline summary](results.before.json), [expanded summary](results.expanded.json),
  [final-default summary](results.final.json),
  [baseline semantic reviews](reviews.before.json),
  [expanded semantic reviews](reviews.expanded.json),
  [final-default reviews](reviews.final.json). Every review is bound to its
  exact answer hash and raw-record hash.
- Ignored raw responses, SSE, candidates, corpus snapshots, source snapshots,
model metadata, transport/prompt probes and preservation hashes:
  `test_output/quality_fixes/`. Baseline source revision:
  `f4113e4500598c74c9ad1ac32b6004d007e2266c`.

Reviewer: Codex source/semantic review, without independent human annotations.
Both holdouts are small convenience samples. Further optimization requires new
development examples and another fresh holdout; these questions are now inspected.
No larger model was chosen or downloaded. More selector capacity would consume
additional memory/CPU and requires its own measured comparison; it would not
restore evidence excluded by the lexical gate, sentence filter or candidate rank.

## Final preservation audit and Week 6 status

All eight before/after corpus snapshots across the four runs match: **58 papers,
2,775 v2 chunks**, alias `paper-chunks` → `paper-chunks-v2`, and **1,221 preserved
v1 chunks**. Stored-paper and v2 chunk text/metadata fingerprints are unchanged,
preserving the repaired paper text and chunks. The read-only snapshots exclude
embedding vectors and verify v1 by count, not a full v1 content hash. Both
installed model digests match baseline.
Every pre-existing evaluation file, including frozen benchmark and judgments,
matches its initial hash. Of 113 initially fingerprinted source/test/evaluation
and README/TESTING files, 104 are unchanged; the other nine are the scoped
implementation, regression tests and documentation updates. The two env templates
only add the conservative setting. Final runtime and fresh labels match their
pre-collection hashes, and container source hashes/default were verified.

Across **280 collection requests**, 134 of 140 answer attempts succeeded. All
**1,028 citation records** on successful answers matched indexed and stored
source text. No successful answer violated attribution or the 200-word limit;
maximum was 106 words (final fresh-set maximum 88). Every successful stream
passed event/delta integrity checks. All 44 corpus unsupported attempts abstained;
the failed medical-condition development control remains explicitly disclosed.
Machine-readable audit: [preservation.json](preservation.json).

The approved pass is measured and recorded, with conservative rollback of the
quality-regressing expansion. **It does not establish broad answer-quality
acceptance.** Selector failures, filler, incomplete multi-paper answers,
synonym-gate rejection and the AVE inconsistency remain. Week 6 remains planned;
no hardening or deployment has started. Its planning should inspect existing
observability, access control, rate limits, deployment and backup/restore controls
before adding anything, using this report as the outstanding quality record.
