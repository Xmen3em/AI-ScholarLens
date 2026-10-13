# Hosted Week 7 evaluation protocol v1

Frozen before hosted inference on 2026-10-13, Africa/Cairo. This is an additive
hosted profile, not a replacement for `week7_agent` v2 or its local 3 GiB gate.
Default application HF/agent flags and the retained Week 6 runtime remain intact.

## Cases, identity and selection

Reference the untouched local manifest
`58b099eead49d8fd22d96be7a7ceba3142de9524ce6f80846e2e8ddee884b0db` and its
eight development/24 holdout cases, source facts and hashes. Validate the complete
local source/freeze before planning or collection; do not copy/relabel questions.
All old evaluations, corpus/indexes, embedding/model files and recovery bundle
are preserved. No holdout outputs are used for provider/model selection.

Initial registered candidates: GPT-OSS-120B through Groq, and through Fireworks.
The first pilot targets Groq. Fireworks is a separately qualified development
candidate if needed; there is no automatic request-time failover. Qwen/Kimi/GLM
remain outside this profile pending provider-specific contracts.

Baseline and agent always use the SAME explicit model/provider pair, code,
source snapshot, controls and resources in a run. Default development matrix:
64 jobs (8 cases x 2 modes x 2 transports x 2 paths). Pilot subsets are allowed
only for development. Holdout: all 192 jobs in the existing counterbalanced order,
without subset/reordering/retries. Each run uses one candidate pair. A holdout
requires a locked selection artifact referencing a complete, semantically reviewed
64-job development run with passing hosted development gates. Comparison trials
and rejected qualifications are retained; selection precedes holdout collection.

## Qualification and limits

Five synthetic calls precede any case collection: original scope, relevance and
rewrite schemas plus selector patterns for 1 and 10 IDs. Validate strict JSON,
types, bounds, expected synthetic scope/markers and exact expected selections.
Keep only validation outcome/schema hashes and usage/timing, never controller
text or reasoning. Failure blocks collection and is not retried. A separate
30-ID diagnostic must reject locally before any outbound attempt because its
9,303-character original regex exceeds this profile. Do not remove constraints.
Qualification establishes limited compatibility, not full request-range parity.

Fixed router `https://router.huggingface.co/v1/`, pinned provider, temperature 0,
reasoning effort low, controller output256/selector512, context admission8192,
schema-inclusive UTF8 bytes <=8192-output-512, response65,536bytes/content8192chars.
No client retry/redirect/proxy/tool/schema fallback. Existing selector retry and
all server quote/lexical/citation validations remain unchanged. One worker and
one active request. Baseline <=2 generation calls/1 retrieval/1 embedding; agent
<=6 generations/2 retrievals/2 embeddings/1 rewrite/8 stages with90s overall/30s
stage deadlines. HF attempt <=30s; collector HTTP attempt <=150s.

Count application generation calls, attempted outbound HF requests and successful
completions separately. Count every failed attempt; preflight rejection records
zero outbound work. Persist only a bounded metadata ledger: ordinal, requested
pair, elapsed time, outcome/error class, outbound count and available token counts.
Validate completed structured content against its ORIGINAL canonical contracts
without altering what the application receives. Native schema violations stop
the run even when a server selector retry could later produce valid output.

The maximum outbound budget is five qualification calls plus the sum of each
job's unchanged generation ceiling (2 baseline/6 agent): full development261,
holdout773. Enforce before work. Six generation request slots/minute use a fresh
test-owned quota file, with smoke calls reserving those same slots. Wait a full
61-second window after smoke and after each six scheduled jobs, counting failed
requests too. Do not charge the production generation quota or retry a rejected job.

## Resource and preservation admission

Engineering starting budgets, to be verified by observations: host free RAM
>=1024 MiB for BM25-only, >=1536 MiB when hybrid is scheduled. This reserves
space for the collector and existing local query embedder; hosted generation
loads no local language model. It does not establish sustained capacity or relax
the original local 3072 MiB gate. Keep >=600 MiB free during/after each attempt;
cancel at <384 MiB or unavailable memory inspection. Stop before further work
if headroom falls below600 MiB. Report all failures/minimum headroom.

Execution requires the existing API key/six-generation quota, server-side HF
credential, unchanged candidate1/agent deadlines/embedding model, credential-free
loopback local service origins, pinned local model digests and matching live
paper/chunk/alias snapshot. Provider availability must be checked via a public
catalog read; advertised flags do not replace qualification. Do not start the
temporary loopback app or paid inference until admission passes. No production
lifespan, DB migrations/cache/tracing backend, container changes or index writes.

Fingerprint all source before/after collection and verify source, local models,
corpus/aliases and both frozen protocols afterward. Stop on integrity/attribution/
schema/budget/resource breach or uncertain inflight work. Timeout/cancellation may
leave remote computation/billing running; do not infer remote termination or retry.
Failed qualifications/pilots and partial holdouts are retained, never accepted.

## Review, usage and acceptance

Reuse original response/quotation-bound manual relevance/fact judgments and
coverage/abstention/failure comparisons. Bind hosted reviews additionally to the
hosted manifest, selected pair and complete records digest. Report every attempt,
including errors and admission rejection. Errors are not correct abstentions;
source attribution is not semantic relevance. Missing usage stays unknown, never
zero. Acceptance requires known input/output usage for every outbound attempt
and no recorded work/schema breaches. Failed/unknown billed attempts are counted
separately and prevent cost-completeness claims.

Frozen indicative rates per million input/output tokens: Groq0.15/0.75USD and
Fireworks0.15/0.60USD from the dated research snapshot. Report known-usage cost
estimate separately from unknown attempts; this is not an invoice. Actual HF
credits/custom-provider-key billing must be checked independently. No credentials,
provider bodies, raw controller decisions, rewrites or reasoning are persisted.
Validated final answers/citations and request/source hashes may be retained locally.

Development lock and holdout acceptance require complete expected matrices and
preservation, no agent failure/scope/hybrid/work/resource regression, no coverage/
relevance/false-abstention regression against the same-pair baseline, and correct
negative abstention under the unchanged scoring gates. Absolute empirical nearest-
rank p95 targets: <=10000ms baseline and <=20000ms agent per mode/transport,
including failed attempts. Holdout collection additionally uses a development
lock; partial/stopped/unreviewed or unknown-usage results never pass.
Record sample counts/maxima alongside p50/p95; small samples do not establish an
SLA, population quality or deployment readiness. There is no statistical speedup
claim against historical local observations or across different models.

After hosted acceptance follow research browse/detail/search/citation inspection,
ownership before history/feedback, then server preparation. Missing backup hardware
does not block source/evaluation development; deployment/push/merge remain outside
this protocol.
