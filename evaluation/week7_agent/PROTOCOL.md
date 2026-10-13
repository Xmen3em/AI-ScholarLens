# Week 7 optional agent evaluation protocol

Fixed 2026-10-13, Africa/Cairo, before question labels and before any model runs.
This protocol covers preparation and a later resource-aware comparison. The agent
remains disabled in application defaults and the active Week 6 runtime stays intact.

## Split, provenance and freeze

Prepare eight development cases and 24 evaluation-only holdout cases. Development:
three literal/paraphrase pairs, one related unsupported question and one unrelated
question. Holdout: six literal/paraphrase pairs, two two-paper questions, two numeric
questions, four related unsupported questions and four unrelated questions.
Expected scope is independent of answerability: unsupported paper questions remain
in scope; unrelated tasks are out of scope. Positive labels depend on stored source
content, not on current retrieval, the lexical guard or sentence eligibility.

Use a new read-only snapshot of all 58 papers and 2,775 indexed v2 passages, with
the preserved v1 count and actual alias targets. Record sorted paper/chunk content
digests and existing evaluation-file hashes. Do not ingest, reparse, reindex, replace
models or copy/update the frozen recovery bundle. Keep full snapshots locally ignored;
tracked labels contain short support excerpts, locators and full-passage hashes.

Use papers outside the 18 support papers in prior saved case arrays. Development
and holdout use different papers, including paper-scoped negatives. Reject repeated
normalized queries from all prior saved case arrays and between new splits. Review
close semantic overlap with earlier questions; exact novelty is not sufficient.
Literal/paraphrase pairs share prewritten required facts but use different wording.
Two-paper cases require separately attributed support from both named papers.
Numeric facts specify original units and paper-reported rounding; do not infer
unreported values or confuse approximate abstract figures with detailed tables.

Author/reviewer: Codex, inspecting stored source sections and indexed passages.
This is a convenience sample, not an independent human annotation study. The
author sees source and labels; "fresh" means no prior model outputs or tuning on
these questions. An evaluation-only holdout is not blind to its author. After freeze,
do not use holdout questions/results to edit prompts, graders, selectors or rewrites.
If a label must change, retain the original freeze and record a versioned erratum
before scoring; invalidate the affected acceptance run. Future tuning uses new
development data and another fresh holdout.

Each negative records the bounded review scope, section inventory, relevant section
review and full stored-corpus lexical scans. Absence claims concern the requested
fact in this preserved corpus, not the scientific literature. Keyword absence alone
is not a semantic proof. Preserve ambiguous labels as unresolved and exclude them
before collection rather than deciding from model behavior.

Freeze `development.json`, `holdout.json`, this protocol and review notes in
`manifest.json` using SHA-256 after source validation. Validation verifies every
support excerpt against both indexed text and its stored section, recomputes
negative scans, checks scope/answerability consistency and disjointness, compares
all older evaluation hashes, and checks frozen file bytes. No model calls occur.

## Later collection, with preserved baseline

Use unchanged RAG/search/model/selector helpers and candidate default one. Do not
compare the active cached API against an uncached agent: later use a separate
temporary one-worker local evaluation process, both paths uncached, with private
test-owned quota/event files. Keep the original API/key, Redis, dependency containers
and rollback container untouched. Read-only access to existing search/model resources
is sufficient; activation of this temporary process and live trials are later work.
No deployment, builds of the active API or broad Compose commands are needed.

Before a live run, verify actual model digests, source hashes, corpus digests and
configuration. Sample host RAM before/during inference; use the existing 600 MiB
minimum acceptance margin and 384 MiB emergency stop floor. Require at least 3 GiB
initial available host RAM for a cold pilot, based on retained Week 6 observations;
this is a conservative trial admission condition, not a server sizing claim. If
capacity is insufficient, defer live collection without altering user applications,
system memory settings, containers, models or this protocol. Keep heavyweight stacks
stopped. One outstanding request at a time, no retries, model downloads or warm-up
generations. First run a development pilot, verify attribution/cancellation/budgets,
and unload only a test-loaded model from RAM if required by its approved trial plan.

Holdout matrix: 24 cases x two retrieval modes x two paths x two transports =
192 answer attempts. `top_k=3`, categories unset, original configured local model,
same options and candidate policy. Counterbalance baseline/agent order by case
index; alternate JSON/SSE order on the next case. Respect the same six-request
generation quota; do not raise it to accelerate evaluation. Retry-After waits occur
between attempts; any 429 attempt remains recorded and receives no client retry.
Record policy/source/dataset hashes, configuration, case identity, actual mode,
request ID, cache bypass, wall time, first status/event/delta, HTTP/SSE failure,
validated response, stages, retrievals, generation calls/tokens/durations and RAM.
Counters must count selector retries and unsuccessful calls. Hybrid adds one query
embedding per retrieval; report those separately from generation calls. A fallback
to BM25 must remain labeled and must not be scored as genuine hybrid operation.

Client timeout 150 seconds, no retry. Agent total/stage defaults stay 90/30 seconds;
baseline retains its original provider timeout, with the client cap reported as a
collection constraint. Report timeout asymmetry, cold/warm order and stopping
conditions explicitly. Do not change timeouts after viewing holdout outputs.

## Scoring fixed before collection

- Attribution: validate quotations/markers/200 words with existing helpers, then
  verify each supplied citation against the indexed chunk and stored section.
  Exact quotation validity earns no semantic relevance credit.
- Coverage: prewritten fact IDs covered / required facts per positive case. Average
  these case fractions; errors and false abstentions receive zero. Report literal,
  paraphrase, numeric and two-paper strata independently, by mode/path/transport.
- Relevance: independently review each substantive quotation against the original
  question, count relevant / total quoted excerpts. Also report case-averaged
  relevance and the substantive-response denominator; do not hide abstentions by
  reporting relevance alone. Unjudged passages are not automatically irrelevant.
- Abstention: fixed abstention response on a negative, successful transport and
  validated output. Errors/timeouts do not count as correct abstentions. Report
  unsupported and out-of-scope negatives separately. Agent scope rejection is
  appropriate only for out-of-scope cases; it is a false abstention on positives.
- Reliability: HTTP/SSE errors and model/validation failures / all attempts. SSE
  requires only fixed status operations before one sources event, delta events,
  one terminal done, exact concatenation equality and no raw model selections.
  Error/interruption must have no done and cannot store output. JSON/SSE agreement
  is measured, not assumed to be deterministic.
- Latency: nearest-rank p50/p95 of all attempts including failures, by path/mode/
  transport; include first-event and first-validated-answer latency. Compare paired
  attempts and report cold/warm/resource effects. No universal SLA or speedup claim
  follows from this small single-host sample.
- Work: generation calls, tokens and duration; query embeddings; retrieval attempts,
  rewrites and stages. Verify <=6 generations, <=2 retrievals/embeddings, <=1 rewrite,
  <=8 stages and configured execution deadlines for every agent attempt. No claimed
  billed cost for local Ollama. An abandoned synchronous read must retain its worker
  slot; HTTP cancellation does not prove remote inference termination.

Semantic reviews bind both the complete response hash and individual quotation/fact
judgments. Review by original question and prewritten labels, without using agent
outcome labels as ground truth. Review all substantive negative answers, all alternative
support and all uncertain fact matches. Source-review corrections are recorded
separately with locators, not silently patched into frozen questions.

## Acceptance and stopping

Isolated implementation acceptance is already recorded separately. Live pilot and
holdout cannot enable the feature unless all of these pass:

1. Zero source-attribution, word-limit, model/retrieval/stage or deadline breaches;
   auth/quota/cancellation/cache boundaries pass. Investigate any breach and stop
   collection before proceeding; retain the failed attempt and preservation checks.
2. Zero substantive unsupported/out-of-scope answers; no errors disguised as
   abstention; all negative attempts successfully abstain.
3. Agent case-averaged fact coverage and relevance are at least baseline in each
   mode/transport cell; paraphrase and two-paper coverage must also not regress.
   False-abstention and failure counts must not increase. Empty relevance denominators
   cannot pass. Report paired differences, numerator/denominator and uncertainty.
4. Resource floor is maintained during cold pilot and subsequent requests; original
   runtime/data/model/evaluation fingerprints remain unchanged. If a run stops,
   report partial results and preserve its evidence; do not call the holdout accepted.

These are observed-sample gates, not population-quality guarantees. Sustained-load
and server sizing need a separate resource plan with explicit latency/concurrency
targets before trials. No live results, semantic judgments or acceptance report are
fabricated during this preparation step. Next, after verified evaluation, follow
research browsing/source inspection and server preparation in the roadmap.

Pre-run correction: the original weather negative was semantically close to an
earlier Cairo forecast case. Freeze v2 replaces it with origami instructions;
`frozen-v1/` retains every first-freeze file. No model outputs were inspected.
See `ERRATA.md`.
