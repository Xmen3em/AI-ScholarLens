# Final minimal array prompt control — 2026-10-14

The final approved synthetic call **passed** with the original relevance schema,
including `maxItems:30`, strict mode, original controller system, low reasoning
and256 output tokens. Only the user prompt changed to a short exact-output
instruction. The response passed canonical local validation and matched the
expected marker array. Earlier relevance trials remain failed and preserved.

This supplies a successful minimal case for the same schema. A general inability
to return this array-shaped object is not supported by these observations.
Prompt interaction is a hypothesis for further investigation, not an established
cause: the comparison is historical, each arm has one observation, and successful
JSON alone does not demonstrate strict enforcement or correct HF forwarding.
The exact application prompt remains unqualified. No guard or application prompt
was changed and no paper question/passages were sent for inference.

**13 of13 approved attempts are used; zero remain.** The final one-attempt
reservation settled at one in the original retained SQLite allowance. No more
inference is authorized by this allowance. Never reset or reconstruct it.

## Frozen experiment and observation

[Protocol](../evaluation/week7_hf/array-prompt-v1/PROTOCOL.md),
[public request](../evaluation/week7_hf/array-prompt-v1/requests.json), manifest:
`d445f845434f469a39e3e06715ae7fc4d92333f08b691293ccfab4ba64b6e7d9`.
The freeze binds the original qualification-v2 and reproduction-v1 manifests.
All earlier frozen payloads/protocols and local failure records remain unchanged.

| Measurement | Observed |
| --- | --- |
| New outbound attempts | 1 |
| Schema / expected object | Passed / matched |
| Input / output / reasoning tokens | 199 / 37 / 11 within output |
| Duration | 551.16ms |
| Initial admission / minimum live free RAM | 1563.29 / 1412.07MiB |
| Qualification / paper collection | False / none |

The unchanged1024MiB admission and600MiB live margin passed. The30-ID selector
still rejected locally without inference. Only fixed categories, booleans,
counts, allowlisted labels, usage/timing/work and hashes are retained. No model
response text, provider messages, reasoning or credentials are saved/emitted.

Known cost estimate for this call:$0.00005760. Cumulative known-usage estimate:
$0.00028545 plus eight failed attempts with unknown usage/cost. These estimates
use the frozen rates and are not invoices.

The isolated command now requires explicit `--experiment array-prompt-v1` and
`--arm minimal-array-prompt-256`; default reproduction-v1 behavior remains.
Cross-experiment arms and unknown experiments reject before private settings or
network access. The exact selected payload and one-attempt cap remain enforced.
No provider fallback, retries, schema downgrade or application activation.

Offline inspection is still available with fresh ignored output:

```powershell
.venv-win/Scripts/python.exe -m src.commands.reproduce_hf_groq --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/hf-array-plan-new --experiment array-prompt-v1 --arm minimal-array-prompt-256
```

The paid allowance is exhausted; `--execute` cannot obtain another slot. Further
live work requires a separately specified, explicitly approved additional budget.
Do not contact support, publish the reproduction or switch providers without a
user request. Offline diagnosis/source development can continue independently.

## Verification and preservation

**876 tests passed, zero skips; mypy98 source files; lint/diff checks pass.**
The41 focused reproduction tests include11 new array/experiment checks: frozen
prompt-only isolation, original marker cap, mismatch/error privacy, offline
planning, explicit experiment binding and complete command help. Review caught
and fixed help output hidden by preliminary argument parsing. An inverted
expected-answer condition was caught and exact source bytes restored. Two existing
Typer/Click warnings remain. Test-owned PostgreSQL resources were removed.

Before documentation updates,1318 of1321 protected hashes matched. The three
intentional changes are the two isolated diagnostic source files and one retained
command test's optional experiment argument. Existing application source,
private settings/API key, original prompts/limits/defaults, previous evaluation
and trial evidence, frozen files and recovery are unchanged. All15 retained
container identities/images/states match; five running. Original64 prior freeze
checks, eight development/24 holdout cases and corpus/index/model state validate.
All four final-run preservation flags are true.

Earlier runs' saved source fingerprints refer to their collection checkpoint;
the additive experiment selector changes diagnostic source afterward. Those
historical bindings are retained, not rewritten to match newer source. The final
run's source fingerprints match current source. No push, merge, deployment,
runtime activation, data/model replacement or selector tuning.

Evidence: [audit](../tests/test_output/hf-array-prompt-20261014-01/audit.json),
[final verification](../tests/test_output/hf-array-prompt-20261014-01/verification-final.json),
[mutation](../tests/test_output/hf-array-prompt-20261014-01/mutation.json),
[live result](../tests/test_output/hf-array-live-20261014-01/diagnostic.json).

The authorized minimal reproduction work is complete. Exact-schema qualification,
reviewed development and locked holdout remain pending before the interface/server
roadmap. This successful control does not authorize application prompt changes
or establish model quality. Missing backup hardware does not block source work.
