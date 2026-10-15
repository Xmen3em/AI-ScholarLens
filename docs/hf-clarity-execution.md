# Two-call HF/Groq clarity diagnostic — 2026-10-15

The user requested an active goal to finish the private PC app with LangGraph,
HF generation and the verified Telegram owner. Both existing HF allowances are
exhausted (13+6=19 attempts). A goal request grants no additional paid attempts.

This next diagnostic proposes **at most two new HF/Groq attempts**: one answering
and one unrelated public synthetic passage for the previously frozen clearer
question. No paper data is sent. The model/provider, system/instruction, strict
relevance schema, temperature, reasoning and256-token limit stay unchanged.
All old fixtures, labels, source fingerprints and results remain historical.

The old `hf_fixture_clarity` command/protocol stays offline-only. A new separately
frozen `clarity-execution-v1` contract references its exact request bytes and the
bounded successful-response diagnostics. Its manifest is
`aef8ff44f41dc662dcbe032755d0af014c4c590f98f9b54be79514d206190672`.
The new command reuses the existing guarded collector and reproduction client;
the older six-call runner retains its default experiment and unchanged scope.

## Approval and accounting

The proposal binds the complete exhausted original13-call ledger and six-arm
extension, including their evidence/receipt/registration. Both are read-only.
No receipt, funded ledger or paid call is created by preparation or by `--propose-approval`.
Default offline planning reads neither credentials nor allowances/services.
Pending/missing approval blocks execution before private settings/service access.

After explicit approval of this exact scope, create its receipt once and use the
fixed ledger `tests/test_output/hf-clarity-allowance-20261015/allowance.sqlite3`.
Reserve an arm before inference; unknown work counts as one. Failed, interrupted
or zero-attempt admitted arms cannot be repeated in a fresh output. Missing or
corrupt registered state requires recovery. Changed parent ledgers/receipts block
new reservations. The new signature comparison distinguishes JSON false from0.
There is no CLI override for the model, arms, endpoint, ledger, budgets or schema.

Admission retains1024MiB,600MiB live margin,384MiB emergency floor, original quotas,
full live corpus/index/model checks and source/payload hashes. No provider/model
switch, retries, paper collection, prompt replacement, qualification, bot/API
activation or Telegram traffic. One request per arm; timeout/uncertainty and
authentication/credit/throttle/service failures stop the pair. Settled HTTP400
`json_validate_failed` remains a diagnostic observation; it is never retried.

Retain only existing flags/counts, usage/cost metadata and bounded error structure.
Provider reasoning/generated text/marker strings are discarded. Both cases can
pass only with original equality/schema checks, complete usage and preservation.
`qualification_accepted` remains false even then. The exact-schema qualification,
reviewed development, locked holdout and live owner acceptance gates still apply.

## Commands and evidence

Prepared pending proposal:
`tests/test_output/hf-clarity-approval-proposal-20261015-01/proposed-approval.json`.
The actual rejection probe used that pending proposal and returned
`not_started/approval_required`, without a funded ledger or network work.

```powershell
.venv-win/Scripts/python.exe -m src.commands.compare_hf_clarity --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/hf-clarity-new-offline-plan
```

The explicit live command requires a separately approved receipt and fresh output:

```powershell
.venv-win/Scripts/python.exe -m src.commands.compare_hf_clarity --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/hf-clarity-live-20261015-01 --execute --approval tests/test_output/hf-clarity-execution-20261015-01/approval.json
```

Read-only SQLite validation now uses `contextlib.closing`: connection contexts
commit/rollback without closing, which left Windows recovery files locked. The
regression retains live handles and verifies they close without garbage collection.
No counter/approval rules change. See the official
[Python connection-context documentation](https://docs.python.org/3.12/library/sqlite3.html#how-to-use-the-connection-context-manager).

Current primary documentation lists the model as supporting strict outputs:
[Groq strict mode](https://console.groq.com/docs/structured-outputs#supported-models).
HF advises selecting a specific provider/model for schema compatibility:
[HF structured outputs](https://huggingface.co/docs/inference-providers/guides/structured-output).
These claims do not establish that this routed application is qualified or explain
the earlier HTTP400s; local admission/response validation stays mandatory.

Ignored preparation evidence is under
`tests/test_output/hf-clarity-execution-prep-20261015-01/`. No new HF/Telegram calls
or runtime activation occurred in preparation. Owner pairing is already complete.

Verification: **1,090 full tests pass, zero skips**,43new since the owner checkpoint,
56 focused checks,mypy109,Ruff. All303 protected private/pairing/evaluation/ledger/
receipt/snapshot/recovery files match. Both old allowances are exhausted unchanged;
the new fixed funded ledger is absent. Source secret scans pass. Full suite191.18s,
with only two existing Typer/Click deprecation warnings. The pending execution
probe blocks as designed. Original running API/rollback are untouched.

The user subsequently approved **two additional calls**. Receipt/confirmation are
in `tests/test_output/hf-clarity-execution-20261015-01/`; its fixed ledger stays
at `tests/test_output/hf-clarity-allowance-20261015/allowance.sqlite3`.
First run `hf-clarity-live-20261015-01` stopped below1024MiB before any provider/
corpus/inference request. User could not free RAM. After it recovered naturally,
run `hf-clarity-live-20261015-02` used the same receipt/counter, and both answering
and unrelated cases passed. Complete usage,original expected/schema checks and
all four live preservation flags passed; only bounded successful diagnostics saved.

**Two new attempts used,zero remaining;21 cumulative attempts used.** No retries
or paper data. The pair establishes a small diagnostic observation for the clearer
question,not a fix for old400s,provider strict enforcement or model/app qualification.
HF/agent/Telegram remain disabled. Next prepare the full exact-schema qualification
with a separate new approval. Keep all old fixtures/labels/results and counter bytes.
