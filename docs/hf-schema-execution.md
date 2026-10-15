# Five-case HF schema qualification

The two clearer-question relevance cases passed. All **21 approved HF attempts
are used**: the original 13, the prompt comparison 6 and the clarity pair 2. They
remain in their original persistent counters with their receipts and results.
No further inference call is approved yet.

The next proposed scope is **up to five additional public synthetic HF/Groq
attempts**, one for each unchanged `qualification-v2` case: scope, relevance,
query rewriting, selection with one candidate and selection with ten candidates.
The model is `openai/gpt-oss-120b:groq`, through the fixed HF router. The original
question, systems, expected values, strict JSON schemas and selector patterns
stay frozen. The clearer-question diagnostic does not substitute for relevance
qualification. A failed check stops the run; no case retries, even in a fresh
output directory. Failed or uncertain attempts count toward the allowance.

The new execution manifest is
`51a6c389b97a4668439bfa2ecdf12258ecb866a164c610829d20c03ef11af32c`.
Its protocol and exact outgoing payloads are in
`evaluation/week7_hf/schema-execution-v1/`. It references the unchanged hosted,
qualification and clarity execution manifests. Controllers use 256 output tokens;
selectors use 512. Temperature 0, low reasoning, context 8,192, deadlines, quotas and
the 1,024/600/384 MiB host-memory gates are retained. The schema with 30 candidates must
fail local admission without sending a request.

`qualify_hf_schema` defaults to an offline plan, with no credential reads, service
access, funding or inference. Proposal mode additionally reads the completed
allowances and successful clarity evidence through closed read-only SQLite
connections. Its receipt remains pending. Execution verifies explicit approval of
the exact scope before reading private Settings or contacting dependencies.

The new fixed counter would be
`tests/test_output/hf-schema-allowance-20261015/allowance.sqlite3`, with a retained
registration marker. It binds all three exhausted allowances, the clarity result,
the model, endpoint and frozen payloads. Each arm reserves before outbound work;
missing registered evidence requires recovery. Existing counters cannot fund it.
Both generation APIs apply the same persistent reservation and five-attempt cap.

Only public synthetic prompts are sent. No paper data, Telegram traffic, task
evaluation, provider change or app activation is included. Saved evidence contains
hashes, bounded flags/counts, usage, timing, memory and allowlisted error labels;
provider generated text and reasoning are discarded. Complete source, frozen
input, corpus and model preservation checks are required for acceptance.

Passing establishes schema qualification only. Reviewed development, locked
holdout and private PC/Telegram acceptance remain required. HF, agent and Telegram
application settings remain disabled, and the read-only API preview is not started.

```powershell
.venv-win/Scripts/python.exe -m src.commands.qualify_hf_schema --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/hf-schema-new-offline-plan
.venv-win/Scripts/python.exe -m src.commands.qualify_hf_schema --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/hf-schema-new-proposal --propose-approval
```

After explicit approval, the guarded command would add `--execute --approval`
with the approved receipt path and a fresh output directory. Preparation evidence
is under `tests/test_output/hf-schema-qualification-prep-20261015-01/`.

Preparation verified **1,146 tests pass, zero skips**, including 38 new tests and
80 focused checks. Mypy checks 114 source files; Ruff passes. The two existing
Typer/Click warnings remain. All 316 protected files match, including private
configuration, pairing, all old freezes, receipts, exhausted counters, the successful
clarity run and recovery evidence. All 15 retained container IDs/images/states
match, with five running and no extras. The full live snapshot still matches:
58 papers, 2,775 chunks and unchanged model fingerprints. No additional HF or
Telegram calls, new funded ledger, server startup or application activation.
