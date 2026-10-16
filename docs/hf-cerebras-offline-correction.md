# Offline scope and evidence correction — 2026-10-16

The failed development run showed incorrect topic rejection and a sentence catalog
that omitted answering evidence. This source change clarifies scope and adds an
opt-in, bounded catalog. **It does not establish improved live model quality or
enable the app.** The existing frozen HF profile still admits one sentence per
passage and rejects the new catalog option.

## Changes

- The scope instruction lists the actual ingested arXiv categories, including
  robotics, and separates topic membership from answer availability. Questions
  about a paper's experimental details or resource usage remain in scope even
  when the requested fact is unsupported. The frozen controller system message
  and synthetic qualification inputs remain unchanged.
- Experimental expansion can offer up to three whole sentences per passage, with
  an optional total cap of 1–10. When capped, it offers first candidates across
  passages before second/third candidates. It keeps the existing lexical admission,
  sentence-length filters and exact source wording. The default remains one
  sentence per passage with no new total cap.
- `PreparedRAG.excerpts()` gives the prompt, schema and rendered answer the same
  deterministic catalog. The LangGraph relevance-filtered context retains its
  limit. Unknown IDs, extra quotations and changed wording still reject.
- Expanded-selector guidance distinguishes requested facts from topic mentions,
  method descriptions and evaluation criteria. This is an instruction change;
  its effectiveness still requires model evaluation.
- Signed answer-cache keys include the total candidate limit. Different catalog
  settings cannot share cached answers. HF admission and the funded client reject
  a limit absent from their frozen profile. No profile or quality gate was changed.
- `.env.example` documents the opt-in cap; `.env.test` explicitly leaves it blank.
  Blank means the unchanged default. The private `.env` was not edited.

## Offline evidence

Final source-map digest:
`66626db90a270820b19e1d9e1fc78693fae21c399b790aefc4c08c0f2e9ec420`.
The final replay reconstructs **64 saved citation contexts** and checks **52
native selector/scope payloads** with networking forbidden. Maximums: 10 offered
candidates, 1,842 input tokens, 6,721 payload bytes and 947 schema bytes. The
oversized 30-candidate schema still rejects under the unchanged byte cap.

All **16 affected benchmark-task/clustering-index contexts** now contain the
required literal names; none of their old one-sentence catalogs did. This is
literal evidence availability, **not semantic scoring**. The replay uses saved
citations: it does not test fresh retrieval, changed controller decisions,
rewrites, or provider output. Robot cases previously rejected before retrieval
cannot acquire new evidence through this replay.

The new regressions first failed on absent catalog support, catalog/schema/render
drift, cache collisions and unregistered HF policy. Focused verification passes:
86 RAG/agent tests, 42 cache/HF tests and eight configuration checks. Ruff and mypy
for 126 source files pass. The **full suite passes all 1,334 tests, zero skips**,
in 881.91 seconds, with the two existing Typer dependency warnings. JUnit:
`tests/test_output/hf-cerebras-evidence-fix-20261016-01/full-02.xml`.

An initial full run was stopped after two configuration-documentation failures:
the new setting was missing from the environment templates. Both templates and
blank-value parsing were corrected; the checks passed before the fresh full run.
No test or acceptance threshold was removed or weakened.

The final preservation audit verifies **400 protected files**, including the
earlier live-run evidence and all settled ledgers. All 15 retained container
identities/images/states match, five running; API8000 is listening. The corpus
remains 58 papers/2,775 chunks and installed model digests match. API8002 is not
listening; the global HF, agent and Telegram flags remain false.

Local evidence:
`tests/test_output/hf-cerebras-evidence-fix-20261016-01/`, including
`catalog-replay-verified.json`, its reproducible `replay_catalog.py`, red/green
JUnit reports and the preservation baseline. Earlier exploratory replay reports
are retained; only `catalog-replay-verified.json` binds the final source above.

## Remaining boundary

The app and owner-only bot stay disabled. No HF calls, Telegram polling, paper
ingestion or container replacement were performed for this correction. The failed
64-job run and its approved receipt/97 settled attempts remain immutable. The
earlier 28 attempts remain exhausted: **125 total used, no new calls**. The 164
unspent calls in the completed grant cannot fund this changed source or catalog.

Next, freeze a separately reviewed candidate profile and execution scope that
explicitly admits three sentences per passage and at most ten candidates. Bind
it to the unchanged quality/resource/input/work gates and complete call history.
Only then request approval for fresh live qualification/development. Holdout and
Telegram activation still depend on accepted evidence; neither is authorized here.
