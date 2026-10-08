# Preserved-corpus evaluation v1

Fixed before endpoint collection on 2026-10-08 (Africa/Cairo). Evaluation only;
no ingestion, index writes, API rebuild, model changes, or guard changes.

## Dataset and review

24 source-authored cases: eight literal/paraphrase pairs, two two-paper questions,
four related but unsupported questions, and two unrelated questions. Expected
answerability means answerable from the stored corpus, independent of retrieval
and the current sentence/lexical guards. Each answerable case has required facts
and reviewed support units with arXiv ID, section index, chunk index, section title,
and a source excerpt. One unit can have alternative supporting passages. These
are deliberately small, non-exhaustive relevance judgments; unjudged passages
are not established irrelevant. No model output or citation marker establishes
relevance. Negative cases use scoped corpus text review; absence cannot establish
absence from all scientific literature. Reviewer: Codex source review, not an
independent human annotation study. The old eight Week 5 acceptance cases are
excluded. All 24 cases are evaluation-only; later tuning requires separate data.

## Fixed measurements

- Retrieve separately at size=3 and size=5: k counts paper groups, each with up to
  three passages. Hybrid candidate depth depends on size, so do not slice a
  size=5 response to estimate size=3. Record actual hybrid/fallback mode.
- For the 18 supported cases, evidence hit@k = any reviewed unit present;
  unit recall@k = fraction of required units with a reviewed alternative present.
  Evidence MRR@k uses the first paper group containing reviewed support. Binary
  evidence nDCG@k gives each supporting paper at most one gain; ideal ordering
  uses the distinct required supporting papers. All are judged-support metrics,
  not exhaustive passage recall. Retrieval failures receive zero and are also
  reported separately. Negative cases are excluded from these denominators.
- Exercise /ask and /stream, BM25 and hybrid, top_k=3, every case, sequentially
  to avoid CPU contention. Timeout 240 seconds, no client retry. Record full
  response, wall time, first event and first delta for streams. SSE must have one
  sources and one done, no error, and concatenated deltas equal done.answer
  (an abstention with no deltas is allowed). Endpoint failure is separate from
  abstention; failures never count as correct abstention.
- Count whitespace-separated words including markers, maximum 200. Audit each
  citation against preserved indexed text and stored paper section text. Validate
  quote attribution separately from meaning. Exact quote/marker validity earns
  no semantic relevance credit.
- Review every successful answer against the prewritten facts: list covered fact
  IDs, relevant excerpt count, total excerpt count, and a short semantic rationale.
  Coverage = covered facts / required facts (abstentions and failures score zero).
  Relevance = relevant / total excerpts for substantive answers only. A correct
  abstention requires an unsupported label and the fixed abstention response.
  False abstention = abstained / all supported cases; report paraphrases separately.
  Report irrelevant substantive responses to unsupported questions explicitly.
- Compare endpoint final answers, citation coordinates, abstention decisions, and
  effective modes. Equality is descriptive, not required model determinism.
- Latency: median and nearest-rank p95, including failed attempts; one local run,
  mixed warm/cold state, no statistical speedup or population-quality claims.

## Diagnosis and acceptance

Inspect actual returned citations. Attribute the earliest lost prerequisite:
retrieval (no reviewed support returned), context budget (support retrieved but
not supplied), lexical gate (support supplied but its paper is ineligible), sentence
filter/selection (required fact absent from server candidates), or model selection
(useful candidate offered but not selected). Multiple losses may coexist. Inspect
paraphrase and long-sentence cases explicitly; do not relax guards to improve scores.

Completion requires saved labels, reproducible collection/scoring, full semantic
review, comparison report, and unchanged corpus/Week 5 source fingerprints. Quality
limitations can remain: evaluation completion is not a broad quality acceptance or
production-readiness claim. Report before Week 6; leave Phase 6 planned.
