# Selector reliability continuation — 2026-10-08

Preserve all existing files, corpus repairs, indexes, models and Week 5 guards.
Default candidates stay 1; 60% lexical gate, whole 7–55-word sentences, exact
server attribution, three-excerpt/200-word bounds and one validated retry remain.
No invalid selection is deduplicated, truncated or repaired. No Week 6 work
begins before results are saved and reported; no deployment is authorized.

First replay the inspected AVE hybrid case with identical evidence, prompts,
schemas, options and ordinary transport. Record exact payload hashes and raw
Ollama results; alternate distinct prompts and repeated prompts to observe
runtime/prompt-state variation. Test batch size separately; runtime differences
are observations, not a proof of a particular floating-point mechanism.

Development uses separate synthetic calibration, scheduling and detector facts;
none is a corpus evaluation question. The proposed structured contract is a
sparse map of known IDs to literal true, with each property available once in
the grammar. Strict server parsing rejects duplicate JSON keys (including
escaped equivalents), wrong values/types, arrays, unknown IDs and extra fields.
At most three entries; empty map is valid abstention. Plain-ID retry is unchanged.
Compare old/new on development before reviewing fresh holdout answers.

Fresh holdout: nine source-reviewed questions from Fast Weight Attention,
Load-Bearing Context and CG4AI, none primary papers in prior sets. Six supported:
three literals, two paraphrases and one two-paper question. Three unsupported:
two related absent details and one unrelated. Complete facts and source chunks
are fixed in holdout.json before collection. Primary papers' complete stored
text is reviewed for absent facts. Use the existing read-only evaluation runner
for BM25/hybrid, retrieval k=3/5, ask/stream top_k=3, serial calls, 240-second
timeout, no client retry, default candidates 1. Collect old API baseline before
rebuild and final API to separate directories. Do not inspect baseline answer
bodies until the runtime change is finalized on development. No runtime tuning
after holdout review; a further iteration requires a new holdout.

## Rejected keyed experiment and second iteration

The nine-question holdout rejected the sparse map: six of 36 answer attempts
failed, and complete-fact coverage decreased. All its outputs, source/test
snapshots and judgments are preserved; the set is now inspected regression data.
The model/runtime did not enforce maxProperties. A map alone is insufficient.

Replacement: structured answer is a string, NONE or one to three known IDs in
increasing numeric order with single spaces. A basic anchored regex represents
this complete language in Ollama's grammar, using compact numeric ranges rather
than enumerating every subset. The server independently checks the same language
and rejects duplicate JSON keys before parsing. Plain-ID retry retains the
existing order-insensitive distinct/known/count validator and single retry bound.
No candidate or model selection is repaired, reordered, truncated or dropped.
Keep generation options unchanged; batch size 1 was rejected for false abstention
and extra prefill cost. Measure synthetic grammar width at 4/9/27/90 candidates.

Finalize runtime on synthetic development, exhaustive independent regex tests
and runtime probes before collecting final_holdout.json. Seven further questions
from Diff Mining and SF-GNN are fixed and source reviewed before collection:
five supported (two literals, two paraphrases, one two-paper), two unsupported
related details. Neither primary paper appears in any earlier holdout. Use all
the original metrics, modes/endpoints and source audits. This is final-only
unseen validation, not a paired improvement estimate. Also collect the original
nine questions with the replacement as explicitly inspected regression data,
and the existing four v1 regressions, without tuning afterward.

Use existing v1 metric definitions: reviewed locator hit/recall/MRR/nDCG
(non-exhaustive), semantic complete-fact coverage, relevant selected quotations,
supported false abstention including paraphrases, correct unsupported abstention,
failures, two-paper fact coverage, exact attribution and source audits, 200-word
limits, SSE ordering/delta integrity, endpoint equality and latency. Failures
score zero coverage. Review every successful answer with answer-bound hashes;
report raw counts and denominator differences. Convenience sample, Codex source
review, no independent human annotation. Latency is local and order-dependent.

Re-run the four inspected regression cases after the final change; do not tune
on them. Preserve before/after paper and chunk hashes, index alias/counts, model
digests, all prior evaluation artifacts and scoped source hashes. Run meaningful
strict-parser/retry/stream regressions and the repository's full tests, Ruff,
mypy and diff checks. Verify running container/source parity after API-only
rebuild. Save failures and rejected experiment artifacts.
