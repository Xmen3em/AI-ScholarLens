# Bounded Cerebras evidence development proposal — 2026-10-16

The previous development comparison failed answer-quality gates. The prepared
replacement tests the clarified research scope and a larger, bounded sentence
catalog using `openai/gpt-oss-120b:cerebras`. **No new inference is approved and
the application and private Telegram bot remain disabled.**

## Frozen change and preserved gates

Source checkpoint `984735a` follows the scope/catalog correction in `acf9ddf`.
Source-map digest:
`a5aa4ad496a324c69ccbce8a42584fea2b899a317319238920d642813944cb26`.
The additive profile is `hosted-cerebras-evidence-v3`, manifest SHA256
`2dc8ab7bb2dd98c544d06b80d5b41873a7e3399e04af9375d332829719c6c23b`.
Its files are in `evaluation/week7_hf/cerebras-evidence-v3/`.

The profile offers up to three whole sentences per passage and at most ten
candidates overall, preserving breadth across passages. Scope includes the
ingested robotics category and distinguishes subject membership from whether
the requested fact is available. Selector guidance asks for the requested fact.
The default catalog, older profiles, frozen controller system message and all
five canonical qualification payloads stay unchanged.

Every inherited quality, attribution, abstention, latency, resource, input,
schema, work and quota gate is retained. Admission needs 1,024 MiB for BM25 and
1,536 MiB for hybrid; live and emergency floors remain 600/384 MiB. Context is
8,192 tokens with the same template/output reserves and byte caps. The
thirty-candidate schema must still reject before reserving or sending a call.
The collector, scorer, acceptance revalidation and private launcher use the
explicit profile identity; the launcher cannot enable generation without an
accepted full holdout lock on the current source.

## Proposed authorization

One **new ceiling of 261 additional attempts** covers five fresh synthetic
qualifications and the complete **64-job development comparison**: eight cases,
BM25/hybrid, JSON/SSE and baseline/agent. It sends only bounded questions and
public excerpts from the retained papers. It does not include holdout or
application/Telegram activation. Failed or uncertain attempts count. Failed
checks stop the run; no replay of a stopped run or provider fallback is allowed.

The completed old development grant used 97 calls; the earlier 28 remain used,
for **125 historical attempts**. Its 164 unspent slots remain tied to that
completed source-bound scope. They are not transferred. The new receipt binds
both histories, including the sealed failed result and all 97 settled rows.
Old accounting and evidence are opened read-only and are never reconstructed.

The concrete pending receipt is
`tests/test_output/hf-cerebras-evidence-development-proposal-20261016-01/proposed-approval.json`;
its adjacent `metadata.json` binds the complete job matrix and current source.
Receipt byte SHA256:
`79f1875b101ffc13a664693c2a48fc2e79e59b4d87690a03d723f46efe4c59f3`.
The proposal grants zero calls until the user explicitly approves this scope.
The separate fixed ledger would be
`tests/test_output/hf-cerebras-evidence-development-allowance-20261016/allowance.sqlite3`
with its `.registered` marker. Both must remain absent before approval.

The public [HF router catalog](https://router.huggingface.co/v1/models), checked
at 05:04:59 UTC on 2026-10-16, advertises Cerebras as live with structured output
at USD 0.35/0.75 per million input/output tokens. A conservative 261-call bound
at those rates is **USD 0.801792**, under USD 0.81; this is an estimate, not an
invoice. Availability, rates, source, credentials and RAM are rechecked before
execution. The model runs remotely; local retrieval and services still use RAM.

## Verification and limits

**All 1,354 tests pass, zero skips**, in 939.68 seconds, with the two existing
Typer dependency warnings. No test or acceptance threshold was removed or
weakened. The full report is `full.xml` in the preparation evidence directory.
Focused checks cover profile immutability, separate funding/history validation,
pending-approval rejection before allocation, source/profile/schema failures,
collection dispatch, scoring, acceptance and private launcher policy. Ruff and
mypy for 126 source files pass. The final audit verifies **419 protected files**
unchanged, all 15 retained container IDs/images/states matching, five running and
no extras. API8000, 58 papers/2,775 chunks and installed model digests match.
API8002 is closed; HF, agent and Telegram flags remain false. Old accounting is
unchanged and the new development/holdout ledgers and registrations are absent.
The final preflight had 2,750 MiB free and passed hybrid admission; execution
must measure again. The audit ran after pytest cleaned up its temporary database
containers; an earlier concurrent inventory check saw those test-owned extras.

The local first-pass rehearsal checks **32 cells and 60 native payloads** using
real retained search, installed embeddings and the service/LangGraph paths.
Maximums are 4,573 input tokens, 13,651 payload bytes and 947 schema bytes, within
the unchanged limits; the oversized schema rejects. Admission had 2,900 MiB free
and the lowest sampled availability was 1,966 MiB. Source, corpus and model
digests match afterward. The helper forbids HF generation and external HTTP.

These are synthetic scope=true, relevance=all and selector=NONE decisions. The
rehearsal does **not** establish model correctness, rewrites, HTTP transport
equivalence, latency acceptance or improved answers. The earlier saved-citation
replay separately established literal name availability in 16 affected catalogs.
Only fresh inference followed by honest reviewed scoring can establish quality.

Evidence is in `tests/test_output/hf-cerebras-evidence-profile-prep-20261016-01/`,
including reproducible rehearsal/audit helpers and red/green test reports. No
HF inference, Telegram polling, new ingestion, reindex or service replacement
is part of preparation. Private configuration and completed evidence stay intact.

## After approval

Keep the source/profile/proposal unchanged, preserve the exact user answer in
an ignored execution directory, and create the approved receipt from the pending
one without changing its scope. Recheck admission, then execute the collector
with `--profile hosted-cerebras-evidence-v3`, this receipt and a fresh output
directory. Never mark a pending proposal approved without the explicit answer.

Review actual answers against the frozen development judgments, score all
64 jobs and create a selection lock only if every required gate passes.
Accepted development permits a separate 192-job holdout proposal, at most 773
attempts with five fresh qualifications. Full accepted holdout precedes separate
private PC/API and owner Telegram activation and an actual end-to-end bot test.
The bot token and private owner pairing are already configured; no repeat setup
or token sharing is needed.
