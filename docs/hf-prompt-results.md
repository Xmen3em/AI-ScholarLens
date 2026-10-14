# Semantic HF/Groq prompt comparison results — 2026-10-14

All six explicitly approved synthetic calls completed. **No instruction passed
both its answering and unrelated-evidence check.** Three arms matched the expected
decision, one returned schema-valid JSON with an unexpected decision, and two
returned HTTP400 / `json_validate_failed` / `invalid_request_error` with empty
reported `failed_generation`. No candidate is promoted; application qualification
remains false and HF/agent defaults remain disabled.

| Instruction | Answering passage | Unrelated passage | Pair passed |
| --- | --- | --- | --- |
| concise | Expected decision matched | HTTP400/json_validate_failed | No |
| json-shape | Schema passed, expected decision mismatched | Expected empty list matched | No |
| per-passage | HTTP400/json_validate_failed | Expected empty list matched | No |

The schema-valid mismatch's actual JSON was deliberately not retained. Its value
cannot be reconstructed from token counts. Both400 error envelopes were complete
and reported empty strings; actual generation and failed usage remain unknown.
These observations do not establish token exhaustion, invalid local schemas,
stripped strict handling, or a root cause. Each case has one observation; this is
not a general model-quality benchmark or evidence of a reliable production prompt.

## Approved execution and budget

User explicitly replied **"Approve six additional calls"** to the frozen
six-attempt synthetic comparison. A fresh ignored approval receipt binds the exact
manifest, arm IDs, HF unified endpoint, `openai/gpt-oss-120b:groq`, no paper data,
and complete exhausted original allowance. Its status is approved; the older
pending proposals are retained unchanged as historical records.

Manifest:
`9dd2a1e2ad2c9cb678c683a4285208b6857fd07bce1a763be5bb36f371fbd3dd`.
All six exact public requests match the freeze. Original schema/maxItems30,
controller system, strict flag, temperature0,low reasoning and256 output tokens
were preserved. Expected objects were local labels, not target answers in messages.
The fixed predeclared order and one-attempt caps held; no retries/fallback.

**Extension6/6 used,zero remaining. Original13/13 used,zero remaining and
byte-unchanged. Total19 explicitly authorized attempts used.** All six arm
reservations settled at one in the fixed extension ledger. Fresh output folders
cannot repeat them. No further inference under either exhausted approval.

| Arm | Duration | Reported input/output tokens |
| --- | --- | --- |
| concise-positive | 539.75ms | 245 / 53 |
| concise-negative | 717.41ms | Unknown |
| json-shape-negative | 719.06ms | 256 / 62 |
| json-shape-positive | 839.03ms | 257 / 100 |
| per-passage-positive | 601.83ms | Unknown |
| per-passage-negative | 729.78ms | 253 / 65 |

Four completed responses report1011 input/280 output tokens total, including194
reasoning tokens within output. New known-usage estimate:$0.00036165 plus two
failed attempts with unknown cost. Cumulative known estimate:$0.00064710 plus ten
unknown-cost failed attempts. Frozen-rate estimates are not invoices or zero-cost
claims for failures.

Actual host admission1179.73MiB passed unchanged1024MiB. Minimum live RAM1084.97MiB
stayed above600MiB; there was no memory/quota/timeout stop. Six calls fit the
original six-generation window. The30-ID selector still rejected locally before
inference. No paper question/passages, evaluation app or production activation.

## Audit and continuation

All2604 protected pre-documentation hashes match: committed source, original
allowance bytes,private settings/API key,prior trials/frozen artifacts and recovery.
All15 retained container identities/images/states match,five running. All four
run preservation flags are true; live source hashes match the current source
checkpoint. Application prompts/guards/limits/corpus/indexes/models/defaults intact.

No application/source/dependency changes in this execution turn. The verified
implementation remains **915 tests passed,zero skips;mypy100**,80 focused checks,
lint/diff and caught/restored privacy/expected-decision mutations. Those checks
come from the unchanged c6e4f8f source checkpoint, not a repeated test run here.
The live audit independently revalidates hashes,schemas/work ledgers,known/unknown
usage,unique settled reservations,original exhausted binding and preserved state.

- [Audited result](../tests/test_output/hf-prompt-execution-20261014-01/audit.json).
- [Full content-free comparison](../tests/test_output/hf-prompt-live-20261014-01/comparison.json).
- [Run metadata](../tests/test_output/hf-prompt-live-20261014-01/metadata.json).
- [Local approved receipt](../tests/test_output/hf-prompt-execution-20261014-01/approval.json).

The authorized comparison is complete. Retain all failures; do not revise labels
or select a winner to obtain a passing result. Next offline work should review
whether the positive semantic fixture is sufficiently unambiguous and specify
bounded successful-output mismatch diagnostics for future studies. A new fixture
must be versioned, not substituted into old trials. Any later provider/transport
comparison must be separately frozen and explicitly budgeted; neither the failed
prompt pairs nor the exhausted allowances authorize switching providers.

Exact-schema qualification, reviewed development and locked holdout remain
pending before enabling HF or continuing the research-interface/server launch.
No production prompt change is supported by this run. No push,merge,deployment,
replacement,selector tuning,support contact or publication. Missing backup
hardware does not block offline/source development.
