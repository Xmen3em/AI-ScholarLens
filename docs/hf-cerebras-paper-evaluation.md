# Cerebras paper evaluation and private PC runtime

The selected provider is absent from the original frozen Groq/Fireworks evaluation
profile. `evaluation/week7_hf/cerebras-evaluation-v1/` adds a separate data-only
profile. Original profile bytes, labels, quality gates and resource limits stay
unchanged. Only version, explicit model/provider registration and dated token rates
differ. Collector, scoring, call accounting and acceptance integration are prepared.
Execution still requires a new explicit approval; no paper run is funded.

The implementation binds profile identity through planning,
collection, per-run qualification, semantic reviews, scoring, development selection
and holdout locks. Corruption and replay checks reject profile/model/manifest
mismatches. The old CLI defaults and existing quality gates remain. A complete run
uses the same model for baseline and agent. Development has 64 jobs and a maximum
of 261 outbound attempts; holdout has 192 jobs and a maximum of 773, including five
fresh qualifications in each. These are future ceilings, not authorizations.

`src.commands.evaluate_hf_papers` defaults to an offline plan. `--propose-approval`
writes a pending receipt without loading credentials, initializing funding or
contacting services. `--execute --approval PATH` requires the exact approved
source, full matrix, snapshot and historical 28-attempt accounting. Development
and holdout have separate fixed ledgers and registration files; missing registered
state requires recovery. A reservation is durable before every provider attempt.
Failed and uncertain attempts count; a stopped run cannot restart or fall back to
another provider. No automatic inference retry is implemented.

Paper execution sends the frozen evaluation questions and bounded excerpts from
the retained public papers to HF/Cerebras. It does not send local credentials,
Telegram identifiers, provider reasoning or unrelated documents. Admission stays
1,024 MiB for BM25 and 1,536 MiB for the full comparison containing hybrid jobs;
live margin is 600 MiB, emergency floor 384 MiB. The model runs remotely.

Scoring uses the explicit `--profile hosted-cerebras-v1`. Semantic reviews bind
each response and its supported facts to the records. `lock` requires accepted
64-job development evidence; holdout revalidates that lock before spending. After
the separately approved 192-job holdout passes, `accept` creates an application
lock that rechecks the complete evidence, funding and current source. Schema
compatibility alone never enables the application.

Offline plan and proposal (choose fresh ignored output directories):

```powershell
.venv-win/Scripts/python.exe -m src.commands.evaluate_hf_papers --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/cerebras-paper-plan-new
.venv-win/Scripts/python.exe -m src.commands.evaluate_hf_papers --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/cerebras-paper-proposal-new --propose-approval
```

The initial proposed scope is **at most 261 development attempts**, including
five fresh synthetic checks and the complete 64-job comparison. Failed or
uncertain work counts. It stops on qualification, schema, attribution, accounting,
source, usage or resource failure. This does not authorize holdout spending,
runtime activation or Telegram messages. At the frozen rates and native token
ceilings, 261 attempts have an estimated upper usage cost below USD 0.81; this is
not an invoice, and provider pricing is checked before execution.

The candidate runtime source is prepared before evaluation to keep source binding
intact. `run_pc_api --check-app --acceptance PATH` validates offline;
`--execute-app --acceptance PATH` serves only loopback port 8002, one worker,
with a separate quota file and read-only PostgreSQL sessions. It validates the
accepted corpus/models at startup and revalidates acceptance before each model
call. Each API request has at most six model attempts; only the accepted Cerebras
pair and canonical schemas are admitted. Cache and tracing stay off in this
isolated configuration. The original API8000 and private `.env` are preserved.

`run_telegram --check --acceptance PATH` validates the already paired owner
configuration offline. With explicit activation, `--execute --acceptance PATH`
uses the authenticated candidate API8002 and verifies its acceptance identity
before Telegram polling. Only the configured owner can ask questions. Existing
offset state prevents replay; question inference is never automatically retried.
No runtime or Telegram process has been started by this preparation.

The approved two-case selector check is complete. Its initial admission stopped
at 674.26 MiB free RAM before any attempt. RAM recovered naturally; a fresh second
run reused the registered ledger and passed both cases. The counter is exhausted
and immutable. The strict combined report verifies all five cases on checkpoint
`1f7af96`; paper/app acceptance remains false. All 28 approved attempts are used.
No paper evaluation or extra schema execution is currently funded.

The model runs remotely. Local RAM is still needed by the collector and retained
services; Ollama's read-only loaded-model list was empty during the schema audit.
Model task and app acceptance remain incomplete; the private bot is paired and
disabled. Current verification results are recorded in `session-checkpoint.md`.

Prepared source checkpoint: `16af44a`. All **1,307 unique tests** have passed:
the full run passed 1,275 and initially skipped 32 database cases while Docker was
stopped; all 33 database integration tests then passed after restoring the retained
services. No skips remain unresolved. Ruff and mypy (124 source files) pass. All
352 protected files match, as do all 15 retained container IDs/images/states, with
five running. The original 58-paper/2,775-chunk corpus and installed model digests
match the frozen snapshot. No new inference or Telegram traffic occurred.

The exact pending development proposal is stored locally at
`tests/test_output/hf-cerebras-development-proposal-20261016-01/proposed-approval.json`,
byte SHA-256 `b73ec5c5a9d5176b64262d03cac1d7b4821d956a385281c503c7950ef499f357`.
Its source-map digest is
`708210a9f1e64942020b3972bfd279d75adc2ee0a0088e1b5bb615ca82ae7a78`.
Both proposed task ledgers and registrations remain absent. The final read-only
preflight measured 1,905.8 MiB free RAM after Docker restoration; admission must
be rechecked immediately before any future execution. No user RAM action is
currently needed.
