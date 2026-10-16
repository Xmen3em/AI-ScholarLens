# Full Cerebras holdout execution — 2026-10-16

Update: the user explicitly approved the 773-call scope. All five checks and
192 jobs completed using 345 calls, but quality acceptance failed in all four
comparisons. The remaining 428 cannot fund a retry; the app and bot remain
disabled. See the [sealed result and next development work](hf-cerebras-paced-holdout-result.md).
The proposal below records the exact historical scope before that approval.

The complete 64-job development comparison is accepted and its selection is
locked. The next step is the frozen **192-job holdout** using the identical
source/profile and `openai/gpt-oss-120b:cerebras`. **No holdout calls are approved;
the application and private Telegram bot remain disabled.**

Development results and limitations are recorded in
[hf-cerebras-paced-development-result.md](hf-cerebras-paced-development-result.md).
All 1,386 tests, zero skips, Ruff and mypy127 pass on the unchanged source.
The new scope changes no implementation, prompt, profile, label or quality bar.

## Source, selection and gates

Application source checkpoint `ba1f168`, collected at documentation checkpoint
`e0fe52e`, has source-map digest
`8baa1a6e12e3e14e7c061dfec03653e3670dee929fde5340aa889b944c950487`.
The profile is `hosted-cerebras-paced-v4`, manifest
`a289b0f75fdf6af2da9687e9e0ecd8df281598cb69b235141704515a34f31ca7`.
The selected development lock's byte SHA256 is
`9ddebd299671abfe932f225c1aaf2a9df172a6863d833afa8cccc0b71a09335e`.
The pending holdout receipt binds that selection, the current source/snapshot,
all prior accounting and the complete ordered matrix.

Keep three sentences per passage/ten total candidates, the unchanged controller
system and five canonical qualification payloads, native input/schema byte caps,
work/deadline limits and rolling six-request/61-second admission. The controller
and selector output limits remain 256/512 tokens, context 8,192 with the same
template reserve. All quality, coverage, relevance, abstention and attribution
gates remain frozen. Baseline/agent p95 limits remain 10/20 seconds.
RAM admission is 1,024 MiB for BM25 and 1,536 MiB for hybrid; live/emergency
floors remain 600/384 MiB. The oversized schema must still reject locally.

The full 24-case holdout runs BM25/hybrid, JSON/SSE and baseline/agent: 192 jobs,
including 96 agent and 96 baseline requests. No subset, reordering for tuning,
prompt adaptation, stopped-run replay or provider fallback is allowed. Results
must be reviewed against the frozen judgments and all required gates must pass.
Any failed check stops collection; a partial result cannot authorize activation.

## Proposed separate authorization

One **new maximum of 773 additional HF/Cerebras attempts** covers five fresh
synthetic schema checks and the complete matrix: at most six generations per
agent job and two per baseline job. Only bounded questions and public paper
contexts from the retained corpus are sent. Failed or uncertain attempts count.
Source, schema, usage, accounting, attribution or resource failure stops the run.
It includes neither application/Telegram activation nor a live owner bot test.

**374 attempts remain used:** 28 historical schema/prompt, 97 first development,
124 stopped development and 125 accepted development. The completed latest
grant's unused 136 and earlier unused 164/137 stay bound to those scopes. None
funds holdout. Historical evidence and accounting remain read-only; registered
state is never reconstructed.

Pending metadata and receipt:
`tests/test_output/hf-cerebras-paced-holdout-proposal-20261016-01/`.
Receipt byte SHA256:
`dd33e8d9c5a87216f86869ef7dcd90bb5deaa799284cb8bff7da0d7b1c39fd43`.
It grants zero calls until explicit approval. The separate fixed ledger would be
`tests/test_output/hf-cerebras-paced-holdout-allowance-20261016/allowance.sqlite3`,
with its `.registered` marker. Both remain absent. The actual pending-receipt
execution is rejected before credentials, networking or funding allocation.

The credential-free [HF router catalog](https://router.huggingface.co/v1/models),
checked at **09:19:24 UTC on 2026-10-16**, lists the route as live with structured
output at USD 0.35/0.75 per million input/output tokens. The conservative full
773-call bound is **USD 2.374656**, under USD 2.38; this is an estimate, not an
invoice. The preparation check has **1,973.74 MiB free** and passes admission.
Current source, selection, accounting, provider prices and resources must pass
again immediately before any approved execution.

## Execution after approval

Retain the exact user question/answer in a fresh ignored holdout execution
directory, bind an approved copy of this receipt, verify the expanded protected
baseline and retained services, and pass current admission before inference.
Do not modify the pending receipt, source, profile or selection.

```powershell
.venv-win/Scripts/python.exe -m src.commands.evaluate_hf_papers `
  --snapshot tests/test_output/week7-source-review-20261013-01 `
  --split holdout --profile hosted-cerebras-paced-v4 `
  --selection tests/test_output/hf-cerebras-paced-development-live-20261016-01/selection-lock.json `
  --output tests/test_output/hf-cerebras-paced-holdout-live-20261016-01 `
  --execute --approval <fresh-approved-holdout-receipt-path>
```

Review actual saved responses and quotations, preserve all failures honestly,
then score the entire matrix with the explicit profile. Only a fully accepted
holdout permits the source-bound application acceptance lock. After the final
preservation/accounting audit, explicit private PC/API and owner Telegram
activation and the real owner question/reply test are still required. The bot
token and owner pairing already exist; no repeated setup or secret sharing is
needed. The development acceptance alone does not complete the application.
