# Cerebras selector checks

The selected `openai/gpt-oss-120b:cerebras` route passed the original scope,
relevance and rewrite cases, followed by both selector cases. All **28 approved
attempts are now used; none remain**.
Those results and every old grant, receipt and allocation remain immutable.

The user approved **two additional public synthetic calls**, for the original
selector-1 and selector-10 fixtures. It uses the same Cerebras route and HF token,
strict canonical JSON schemas, expected selections, patterns, 512 output tokens,
temperature 0, low reasoning, context 8,192, deadlines, quotas and RAM gates.
The schema with 30 candidates must fail local admission without an outbound call.
Failed or uncertain attempts count, and the first failed check stops the pair.
No retry, prompt change, provider fallback, paper data or application activation.

Manifest: `b633c44720e1d4cc0820529bf1eafe38a7be63671b79103a0515b18872a85630`.
Frozen inputs are in `evaluation/week7_hf/cerebras-selectors-v1/`. A new fixed
two-arm counter would be `tests/test_output/hf-cerebras-selectors-allowance-20261015/allowance.sqlite3`.
Its exact new approval binds the full completed controller history: the three-case
receipt, allocation, counter, successful result and preserved metadata, including
all original grants. Old SQLite connections are read-only and explicitly closed.
No old counter can fund this pair, and no reserved arm repeats after a fresh output
or restart. Missing registered evidence requires recovery.

Default and proposal modes are offline: no credentials, service access, allowance
initialization or inference. Pending proposal:
`tests/test_output/hf-cerebras-selectors-proposal-20261015-01/proposed-approval.json`.
The approved receipt and exact user confirmation are preserved under
`tests/test_output/hf-cerebras-selectors-execution-20261015-01/`.
The fixed counter and registration are retained with both arms settled at one
attempt. The first run stopped at 674.26 MiB before reserving an arm. RAM recovered
naturally; the fresh second run passed both selectors with 1,436.60 MiB admission
and at least 1,161.17 MiB live headroom. Approval review and offline verification pass.
Saved diagnostics contain
bounded flags/counts, hashes, usage, latency, memory and safe error labels; provider
generated text and reasoning are discarded. All four preservation checks apply.

```powershell
.venv-win/Scripts/python.exe -m src.commands.qualify_hf_schema --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/hf-cerebras-selectors-new-plan --experiment cerebras-selectors-v1
```

The pair remains a diagnostic with `app_accepted=false`. A full five-case schema
summary must validate both the completed controller evidence and this selector
evidence. Reviewed development/locked holdout and private PC/Telegram acceptance
still follow. Global HF, agent and Telegram flags remain disabled; no preview or
bot process is started. Preparation evidence is under
`tests/test_output/hf-cerebras-selectors-prep-20261015-01/`.

Verification: **1,193 full tests pass, zero skips**, nine new selector tests;
mypy 117 and Ruff pass. Earlier focused 33 checks passed before the final two
CLI checks, which the full suite covers. All 340 protected files match; private
value scans and diff checks pass. The actual pending proposal was rejected before
Settings, funding or network. No selector ledger or registration was created.
No new inference, paper transfer, Telegram traffic or runtime activation.

## Completed approved pair

The historical preparation result above preceded live execution. The successful
pair is in `tests/test_output/hf-cerebras-selectors-live-20261015-02/`. All four
preservation flags pass, both calls have complete usage, and the strict combined
verifier confirms all five canonical Cerebras cases. Its report and summary are
under `tests/test_output/hf-cerebras-five-case-summary-20261015-01/`; report SHA-256
`3c4e2045f46c4d21ac30f50ffdec4d3da7880068498319dc9f459bd3a0caef0d`.
The pair's known usage estimate is USD 0.00066735; five-case total USD 0.00112975,
not an invoice. All 28 approved attempts are used. No paper or Telegram traffic.

To inspect the actual completed pair, use its explicit run path:

```powershell
.venv-win/Scripts/python.exe -m src.commands.hf_schema_evidence --selector-run tests/test_output/hf-cerebras-selectors-live-20261015-02
```

The report is bound to source checkpoint `1f7af96`; later source changes require
fresh qualification before paper execution. This compatibility result alone does
not accept paper answers or enable the app.

The offline verifier, `src.commands.hf_schema_evidence`, now checks
both retained runs, exact five-case order and fixture/schema hashes, approved
read-only counters, complete recomputed token/cost accounting, semantic flags,
memory margins and preservation. It compares all runtime and canonical measurement
source files with the current tree; four explicitly named diagnostic orchestration
files may differ between runs. It always leaves task and app acceptance false.
**1,219 full tests pass, zero skips**, including 26 new verifier checks; Ruff and
mypy (118 source files) pass. The retained controller evidence revalidates, missing
selectors fail closed, and all 340 protected files match. The suite uses a verified
fresh workspace fixture directory; the default Windows temp directory is inaccessible.
Current evidence is under `tests/test_output/hf-schema-evidence-prep-20261015-01/`
and the full JUnit result is `tests/test_output/hf-schema-evidence-full-results-20261015-01.xml`.
