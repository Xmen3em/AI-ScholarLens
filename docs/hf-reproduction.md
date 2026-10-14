# Minimal HF/Groq reproduction — 2026-10-14

Current continuation: [the final minimal array prompt control](hf-array-prompt.md)
passed with the original relevance schema at256 tokens. The diagnostic is complete;
**13/13 approved attempts used,zero remain**. Current verification:876 tests,
zero skips,mypy98. The four-arm report and its12-used/one-remaining balance below
are historical. Root cause and exact application qualification remain unresolved.

The minimal required-boolean request passed. All three synthetic relevance
variants failed with HTTP400 / `json_validate_failed` / `invalid_request_error`
and empty reported `failed_generation`. Neither the tested output-limit increase
nor removing outbound `maxItems` resolved these observations. Root cause remains
unresolved; Groq is unqualified and no paper collection ran.

**12 of13 approved attempts are used; one remains.** Four new one-attempt
reservations settled in the same retained SQLite allowance. No reset, retry or
automatic continuation. Preserve this final slot for a separately frozen new
experiment; it cannot fund full qualification or the paired paper pilot.

## Frozen reproduction

The [public requests](../evaluation/week7_hf/reproduction-v1/requests.json) contain
complete credential-free wire payloads and synthetic expected objects. They can
be inspected locally without sending anything. The [protocol](../evaluation/week7_hf/reproduction-v1/PROTOCOL.md)
and requests were frozen before inference, bound to the original qualification
and structural-diagnostic manifests. Manifest SHA256:
`7e5768ae0713b9d91d19d5faf0f5a62c6941ac25deef55b43ae014c31566a4cf`.

The [isolated helper](../src/commands/hf_reproduction.py) and
[command](../src/commands/reproduce_hf_groq.py) reuse the retained HF client,
canonical local validation, quota/memory handling and bounded error observer.
They cannot change application settings, grant qualification or start paper jobs.
The exact frozen arm is enforced before outbound work; each client independently
caps execution at one attempt. Missing retained allowance stops execution without
creating one. Unknown completion consumes its reservation.

| Arm | Explicit diagnostic change | Result | Duration |
| --- | --- | --- | --- |
| minimal-boolean-256 | Bare boolean schema and short exact-output synthetic prompt | Passed schema and expected object | 658.36ms |
| exact-relevance-512 | Original relevance contract; output256 →512 | HTTP400/json_validate_failed | 886.38ms |
| without-maxitems-256 | Original relevance request; outbound maxItems omitted | HTTP400/json_validate_failed | 812.85ms |
| without-maxitems-512 | Same outbound keyword control; output256 →512 | HTTP400/json_validate_failed | 732.26ms |

All arms use the approved HF unified router and `openai/gpt-oss-120b:groq`, strict
schema, temperature0 and low reasoning. The relevance prompts/system and other
schema fields stay exact. Omitting `maxItems` is an isolated wire control: the
original local30-marker limit and all application guards remain enforced.

Arms2/4 compare only `maxItems` at512 tokens. Arms3/4 compare only output limit
with the same schema and inputs. Retained exact relevance at256 is a historical
reference, not a contemporaneous arm or another unchanged paid repetition.
The minimal boolean result supports only this observed simple strict-object
request; prompt/schema differences prevent attributing relevance failure to
arrays alone. One observation per arm is not causal proof, and both tested
token budgets may remain insufficient. No evidence establishes stripped strict
handling, malformed local schema, zero actual model generation or model quality.

[Groq's structured-output documentation](https://console.groq.com/docs/structured-outputs)
advertises strict GPT-OSS120B support with required fields and closed objects.
[Its reasoning documentation](https://console.groq.com/docs/reasoning) describes
low reasoning effort. Those advertised capabilities do not verify HF forwarding.

## Admission, privacy and cost

All four actual initial admissions passed unchanged1024MiB:1413.00,1296.66,
1408.73 and1492.06MiB, respectively. The lowest live sample was1230.23MiB,
above600MiB. Initial admission is recorded separately from pre-request/live RAM.
The30-ID selector rejected locally with zero inference attempts. No evaluation
app/server started or paper questions/passages were sent for inference. Original
model and runtime state was preserved.

Only fixed outcome categories, allowlisted provider code/type/status,
booleans/nulls/bounded counts, timing/usage/work and hashes are saved. The existing
8192-decoded-byte error observer is reused; provider messages, generated text,
reasoning and credentials are not saved or emitted. All three failures report a
complete error envelope with an empty string; actual model generation is unknown.

The boolean call reports163 input/30 output tokens, including11 reasoning tokens
within output. Its frozen-rate estimate is$0.00004695; the other three calls have
unknown usage/cost. Cumulative known-usage estimate:$0.00022785 plus eight failed
attempts of unknown cost. These estimates are not invoices; zero known cost on a
failed row does not mean zero billing.

## Commands and verification

Offline plan, with a fresh ignored output directory:

```powershell
.venv-win/Scripts/python.exe -m src.commands.reproduce_hf_groq --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/hf-reproduction-plan-new --arm exact-relevance-512
```

`--execute` performs the selected arm only after original live source/model,
advertised provider, admission, quota and allowance checks. The completed arms
must not be repeated unchanged; the remaining slot needs a separately frozen
experiment. No support contact or publication is authorized.

**865 tests passed, zero skips; mypy98 source files; focused lint/diff checks pass.**
Thirty new isolated tests cover exact wire requests, privacy, failures, canonical
marker cap, memory admission, offline operation, missing/exhausted allowance and
actual/uncertain settlement. Both a deliberate content leak and an inverted
expected-answer condition were detected; exact source bytes were restored.
Two existing Typer/Click deprecation warnings remain. The Windows sandbox blocked
asyncio socket-pair initialization before test code; offline tests and the full
suite were verified outside it, including disposable test-owned PostgreSQL.

Before documentation updates, all1034 protected file hashes matched, including
private settings, committed source/evaluations, prior trial evidence and recovery.
All15 retained container IDs/image digests/states match, five running. All four
run preservation flags and source hashes match. Original64 prior freeze checks,
eight development/24 holdout cases and corpus/index/model state validate.
Agent/HF defaults remain disabled; API/key, prompts, limits and rollback retained.
No push, merge, deployment, replacement or selector tuning.

Evidence: [audit](../tests/test_output/hf-reproduction-20261014-01/audit.json),
[verification](../tests/test_output/hf-reproduction-20261014-01/verification.json),
[privacy mutation](../tests/test_output/hf-reproduction-20261014-01/mutation.json)
and [guard review](../tests/test_output/hf-reproduction-20261014-01/review.json).
Live records are in `tests/test_output/hf-reproduction-*-live-20261014-01/`.

Next prepare, offline first, a minimal array-valued exact-output prompt control
to separate prompt complexity from simple array handling, using the final slot
only after its protocol/request/privacy tests are separately frozen. Do not
infer a fix or change application controls. Exact-schema qualification, reviewed
development and locked holdout remain prerequisites to the interface/server
roadmap; missing backup hardware does not block source development.
