# Answer-quality fix evaluation, 2026-10-08

Development uses the eight synthetic examples in `development.json` and focused
regressions. None is a v1 benchmark question. Candidate coverage counts the
prewritten complete synthetic fact sentences made selectable, independently of
whether the model selects them. Synthetic answer coverage counts those same
sentences in rendered quotations. Two paraphrases and three unsupported controls
measure the unchanged lexical policy and selector abstention separately.

The 12 questions in `holdout.json` were authored and source reviewed before the
baseline collection or runtime edits. Eight are supported (including two
paraphrases and one two-paper question); four are unsupported. Four primary papers
are outside the seven v1 primary papers. Expected facts and complete stored source
locators were fixed before collection. Baseline answer bodies are deliberately
not inspected until the implementation is finalized on development examples.
No runtime tuning is permitted after reviewing these holdout answers. A further
iteration requires a new holdout. Reviewer: Codex source review, not independent
human annotation. This small convenience sample cannot establish general quality.

Use the existing read-only `evaluate_retrieval` runner and v1 metric definitions:
separate k=3/5 retrieval, BM25/hybrid, both answer endpoints at top_k=3, serial
requests, 240-second timeout, no client retry. Freeze facts before collection;
score failures and abstentions as zero coverage. Review relevant excerpts and
complete facts semantically, separately from exact quotation attribution. Include
partial useful details as relevant even when an entire compound fact is missing.
Record failures, unsupported substantive answers, false abstentions, endpoint
agreement, the 200-word limit, streaming event integrity and latency. Latencies
are order dependent local observations; /stream follows /ask and benefits from
model and prompt cache warmth. No intrinsic speedup claim is allowed.

Collect before and after to distinct output directories under
`test_output/quality_fixes/`. Audit paper/chunk hashes, both indexes, alias and
model digests before/after. Record baseline source hashes and permit changes only
to the scoped RAG implementation and its tests. Frozen v1 data and judgments are
untouched. A rerun of inspected v1 would be regression evidence, not unseen data.

The paraphrase gate remains at 60%; no semantic substitution or lower threshold
is approved by these measurements alone. Long sentences are still omitted whole,
not cut. Invalid model selections must be rejected, never deduplicated, truncated
or repaired. Both endpoints buffer validation before exposing quotations. /ask
retains one bounded retry; the shared selection path gives /stream that same
bound. Failure injection tests cover invalid retries and ensure no answer delta
escapes before validation.

Report results and remaining limitations before starting Week 6. No deployment,
ingestion, reparsing, repair, reindex, model replacement, commit, push or merge.

## Conservative rollback and final validation

The initial holdout rejected default candidate expansion: relevance decreased
in both modes. Expansion is retained as an explicitly opt-in experiment (2 or 3
sentences per passage), with a default of 1. The default prompt retains its
original wording: even adding "distinct" caused a development abstention
regression. Structured generation still receives a uniqueness hint, and the
unchanged server validator enforces uniqueness. The shared transport and bounded
validated retry remain enabled. This is a conservative rollback, not further
optimization to the inspected holdout questions.

`final_holdout.json` fixes seven further questions from two additional primary
papers, before collecting any endpoint output with the final default. Five are
supported, including one paraphrase and one two-paper question; two are
unsupported. Use the same metrics and complete semantic review, without further
tuning. `regression.json` copies four inspected v1 cases unchanged to check the
previous sizing failure, AVE endpoint inconsistency, multi-paper lexical
abstention and unsupported abstention. These are regression data, not unseen data.
