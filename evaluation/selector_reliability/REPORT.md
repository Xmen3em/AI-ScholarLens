# Selector reliability measured — 2026-10-08

The retained selector prevents duplicate IDs in its structured grammar and
rejects malformed output independently on the server. UndoBench now succeeds
in **4/4** measured attempts, and AVE's answer/abstention mismatch did not recur
in the final identical-payload replay or paired endpoint collection. This is a
selector-validity improvement with material answer-quality limitations:
incomplete facts, filler and false substantive answers remain. **Week 6 has
not started.** No broad quality acceptance or deployment is claimed.

## Retained change and rejected alternatives

The internal structured contract is now `{"answer":"E1 E3"}` or
`{"answer":"NONE"}`. A basic anchored regex admits one to three known IDs in
strictly increasing numeric order. The server independently checks that language,
rejects duplicate JSON object keys before dictionary parsing (including escaped
equivalents), and renders exact server-owned quotations. It never sorts,
deduplicates, truncates or repairs a model selection. The public response shape
is unchanged. The existing single plain-ID retry remains independently validated;
its existing order-insensitive acceptance is unchanged.

Preserved: candidate default **1**, per-paper **60%** lexical gate, whole
**7–55-word** sentence filter, exact citations, at most **three excerpts/200
words**, fail-closed validation, buffered streaming and at most **one** retry
against the same evidence. Retrieval, generation options, models and corpus were
not changed. Opt-in candidate expansion remains available under its prior limits.

An intermediate sparse keyed-map contract was rejected. Although it prevented
repeated keys under ordinary generation, the installed runtime did not enforce
`maxProperties`: six answer attempts failed on its fresh holdout, and coverage
regressed. Its source, tests, build context, raw results and judgments are all
retained under `test_output/selector_reliability/rejected-map/` and the separate
map artifacts. Batch size 1 was also rejected: all six AVE replay requests
abstained, with approximately 43–44 seconds of initial prefill versus 9–11
seconds using the original batching. The original generation options remain.

## Exact-payload AVE diagnosis

The ask/stream preparation produced identical UTF-8 evidence, prompts, schemas,
system prompts and generation options. Each six-request experiment has one exact
payload hash. A distinct prompt preceded requests 1 and 4; the following two
requests repeated the identical AVE payload. Ordinary Ollama generation was used
throughout, matching both endpoints' existing transport.

| Contract/options | After distinct prompt | Immediate repeats | Accuracy sentence |
| --- | --- | --- | --- |
| Original array, original options | Answer on 2/2 | Abstain on 4/4 | Present only in answers |
| Original array, batch size 1 | Abstain on 2/2 | Abstain on 4/4 | Absent |
| Rejected map, original options | Same answer on 2/2 | Same answer on 4/4 | Omitted |
| Retained string, original options | Same answer on 2/2 | Same answer on 4/4 | Included |

This reproduces variation below the endpoint transport layer and associates it
with prompt state/batching. It does **not** prove a particular numerical or cache
mechanism. The llama.cpp server documentation describes batch-dependent logits
under prompt caching; that is supporting context, not identification of the
exact implementation inside the installed Ollama **0.11.2** runtime.
[llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).
Ollama documents schema-constrained output, but observed enforcement must still
be checked on the installed runtime.
[Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

Final replay selected `E1 E3` on **6/6** calls: the accuracy fact plus an
irrelevant baseline fine-tuning sentence. Reproducible format and local replay
agreement do not establish semantic relevance or general determinism. Initial
PowerShell-decoded replay files lacked explicit UTF-8; they are preserved but
excluded. Only `replay-utf8-*` and `payload-utf8-*` support these conclusions.

## Evaluation design and development

[PROTOCOL.md](PROTOCOL.md) records both iterations. Synthetic development uses
six separate calibration, scheduling and detector examples. Original array
generation failed 2/12 attempts and covered 3/5 supported synthetic facts per
endpoint; retained string generation succeeded 12/12 and covered 4/5. Its
two-paper example still omitted one paper. Both versions falsely selected general
detector accuracy for the absent underwater-sonar accuracy request. That negative
control is a known semantic failure, not a valid abstention.

The first source-reviewed nine-question holdout used Fast Weight Attention,
Load-Bearing Context and CG4AI: six supported questions, including two paraphrases
and one two-paper question, plus three unsupported controls. Baseline was
collected before API rebuild; answers were inspected after the map was frozen.
That set rejected the map and is now inspected regression data.

The final seven-question holdout used two further papers, Diff Mining and SF-GNN,
absent as primary papers from all earlier holdouts: five supported questions
(two literal, two paraphrase, one two-paper), two related unsupported controls.
Complete facts, metrics and source locators were fixed before collection. A
source locator for the already-declared linear warm-up fact was corrected
**before** final collection; the preceding label snapshot is retained. Final
runtime and labels match pre-collection hashes. No tuning followed final answer
inspection. This final-only holdout cannot supply a paired quality-improvement
estimate.

All runs used BM25/hybrid, retrieval k=3/5, ask/stream top_k=3, candidate default
1, serial calls, 240-second client timeout and no client retries. Facts require
complete support; partial but useful excerpts can count as relevant without
earning a complete fact. Failures and false abstentions receive zero coverage.
Reviews bind every successful answer and full record file by SHA-256. All
distinct successful answers were inspected. These are small convenience samples
reviewed by Codex, without independent human annotation.

## Measured quality and failures

Coverage is the mean complete-fact fraction over supported questions. Relevance
is relevant selected excerpts divided by all selected excerpts, including false
substantive unsupported answers. Each coverage/relevance value below applies
equally to ask and stream in that run; failures are counted across both.

| Set/contract | Answer successes | BM25 coverage | Hybrid coverage | BM25 relevance | Hybrid relevance | Exact paired answers |
| --- | --- | --- | --- | --- | --- | --- |
| First nine, original array | 36/36 | 75.0% | 66.7% | 10/17 (58.8%) | 8/18 (44.4%) | 18/18 |
| First nine, rejected map | 30/36 | 44.4% | 52.8% | 5/8 (62.5%) | 6/13 (46.2%) | 15/15 successful; 18 total |
| First nine, retained string; inspected regression | 36/36 | 58.3% | 50.0% | 6/12 (50.0%) | 5/13 (38.5%) | 18/18 |
| Final seven, retained string; fresh | 28/28 | 50.0% | 70.0% | 6/11 (54.5%) | 7/13 (53.8%) | 14/14 |

The apparent map relevance increase has fewer successful outputs in its
denominator and does not offset its failures. The retained string eliminates
those failures but **does regress coverage and relevance versus the array on
the inspected first nine**. In particular, BM25 omits the Question Damage Score
definition, hybrid omits complete CG4AI weight/pricing details, and both modes
leave a two-paper component unanswered. Numeric ordering/format changes can
alter model choices; prevention of duplicates does not preserve semantic choices.

Final fresh details:

- **Unsupported abstention: 4/8 attempts correct.** The subscription-price
  control abstained in all four attempts. The SF-GNN kilowatt-hour energy-cost
  control produced irrelevant accuracy/fairness or dataset quotations in all
  four attempts, despite correct source attribution. It is a semantic failure.
- Supported false abstention: BM25 **1/5** questions per endpoint, hybrid **0/5**.
  Neither mode falsely abstained on the two paraphrases, but complete paraphrase
  facts were still omitted (BM25 linear warm-up; hybrid base/fine logit differences).
- Two-paper complete-fact coverage: BM25 **0/2**, hybrid **1/2** per endpoint.
  Neither mode fully answered the two-paper question.
- Zero successful-answer attribution, citation-audit or word-limit failures;
  maximum fresh answer **80 words**. Exact endpoint answers, abstention choices,
  citation coordinates and effective mode matched in **14/14** pairs.

On the four previously inspected v1 regressions, final string succeeds **16/16**
attempts and matches **8/8** endpoint pairs. UndoBench succeeds **4/4** (previous
quality-pass run failed all four); BM25 covers all three counts, hybrid two of
three. AVE answers **4/4**, including the accuracy/no-fine-tuning fact, but omits
the complete learned-classifier fact; hybrid also includes baseline filler.
The supported multi-tokenizer question still falsely abstains **4/4** because
the conservative lexical gate excludes evidence. Unsupported AVE abstains **4/4**.
Regression mean coverage is **50.0% BM25 / 38.9% hybrid**. This is a narrow
regression check, not evidence that paraphrase or multi-paper quality is solved.

## Retrieval and latency

Fresh retrieval metrics use only reviewed source locators, which are not
exhaustive relevance judgments. Values are identical at k=3 and k=5:

| Mode | Hit | Recall | MRR | nDCG | Supported questions |
| --- | --- | --- | --- | --- | --- |
| BM25 | 0.80 | 0.70 | 0.70 | 0.677 | 5 |
| Hybrid | 0.60 | 0.50 | 0.50 | 0.477 | 5 |

Fresh end-to-end seconds, including abstentions and reloads:

| Mode/endpoint | Median | p95 |
| --- | --- | --- |
| BM25 ask | 7.032 | 91.510 |
| BM25 stream | 1.278 | 3.314 |
| Hybrid ask | 7.082 | 11.150 |
| Hybrid stream | 1.472 | 2.442 |

The first BM25 ask included model reload; the first hybrid search took 23.136
seconds. Ask preceded stream on each question, so streaming benefited from
warm prompt state and is still buffered. Small-sample p95 is effectively the
maximum here. These order-dependent local measurements do not establish a
speedup from the change. Separate grammar probes at 4/9/27/90 candidates produced
valid selections; regex sizes were 81/491/6,873/142,376 bytes, with a roughly
19-ms Python build time at 90. Live calls were 4.47/1.77/1.15/1.38 seconds under
different warm states, not isolated grammar overhead estimates. Four deliberately
invalid requested sequences (duplicate, unknown, reversed, excessive IDs) were
constrained to valid outputs. Those are synthetic runtime checks, not relevance
tests or universal enforcement proof; server rejection remains authoritative.

## Verification, preservation and artifacts

Full repository verification: **427 passed, 32 existing integration skips**, two
existing warnings; Ruff and mypy (68 source files) passed. Independent contract
tests exhaust all 341 selections over four IDs, check 90-ID numeric boundaries,
strict JSON shape/duplicate keys, exact rendering, bounded same-evidence retry,
NONE handling and no stream leakage after rejected retry. Disabling duplicate
JSON-key rejection caused the two expected test failures; source was restored
byte-for-byte and matches the final pre-collection snapshot.

[collection_audit.json](collection_audit.json) validates **336 collection
requests**, **168 answer attempts**, **162 successes**, all **1,228** successful
answer citation records and **81** successful stream sequences. The six failures
belong solely to the rejected map; its three failed streams emitted sources and
error, with no answer delta or done. Overall maximum successful answer was
118 words. Final contract runs total **80/80** successful answer attempts and
**40/40** exact endpoint pairs. All twelve before/after corpus snapshots match.

[preservation.json](preservation.json) records the final read-only preservation
audit: 58 papers, 2,775 v2 chunks, alias `paper-chunks` to `paper-chunks-v2`, and
1,221 v1 chunks. Stored-paper and v2 chunk text/metadata hashes, installed model
digests, frozen v1 benchmark/judgments, prior evaluation files and 7,503 prior
raw artifact fingerprints remain unchanged. Snapshots exclude embedding vectors
and verify v1 by count, not full content hash. Final API source matches all 70
saved container file hashes and candidate default 1. Only the local API was
rebuilt/restarted. No commit, push, merge, ingestion, corpus repair, reindex,
model download/replacement or external deployment occurred.

The initial final-source audit compared differently spelled Windows path keys
and falsely reported a mismatch. Direct content hashing found no changed files;
the helper now preserves snapshot key spelling. The preliminary audit is retained
as `test_output/selector_reliability/preservation.path_mismatch.json`.

Reproduce scoring without model calls:

```powershell
.venv-win/Scripts/python.exe -m evaluation.selector_reliability.collection_audit
.venv-win/Scripts/python.exe -m src.commands.evaluate_retrieval --benchmark evaluation/selector_reliability/final_holdout.json --output test_output/selector_reliability/final --score
```

Tracked artifacts: protocol, synthetic development, both source-reviewed
holdouts, explicit annotations, answer-bound reviews and results for every run.
Raw records/SSE, corpus snapshots, payload replays, model metadata, rejected
source/build contexts, mutation outputs and API logs remain under
`test_output/selector_reliability/`. Baseline revision:
`cc45901`. New continuation changes remain uncommitted. Every evaluated set is
now inspected; further optimization requires new development and fresh holdout
questions. The outstanding semantic defects and measured regression must remain
visible before Week 6 planning; no Week 6 implementation has begun.
