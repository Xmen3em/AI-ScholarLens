# Semantic relevance prompt comparison

Current result: [all six approved calls completed](hf-prompt-results.md).
Three arms passed,one returned schema-valid unexpected JSON,and two returned
HTTP400/json_validate_failed. **No positive/negative pair passed.** Extension6/6
and original13/13 are exhausted;zero remain. No candidate promoted,qualification
false,application/defaults preserved. Preparation/pending-approval notes below
are historical;the explicit new approval is retained in the live audit.

The last minimal array prompt copied an explicitly requested object successfully.
The next comparison tests selection and abstention without supplying the answer
in the instruction. Three diagnostic instructions share the original relevance
schema, controller system and limits. Each gets the same positive passage and an
unrelated negative passage. Six proposed calls; no live result is available yet.

| Variant | Instruction emphasis | Positive expectation | Negative expectation |
| --- | --- | --- | --- |
| concise | Select passages answering the question | Supplied marker | Empty list |
| json-shape | Name the required JSON field and array type | Supplied marker | Empty list |
| per-passage | Judge the question-answer relation per passage | Supplied marker | Empty list |

The positive question/evidence stays exactly qualification-v2. The negative uses
the same question/marker and an unrelated statement about a synthetic cover's
color. The schema/system, strict flag, model/provider, temperature0,low reasoning,
output256 and conservative context admission8192 are unchanged. Expected objects
are local test labels; no target answer object is included in sent messages.

This is an isolated diagnostic. Application prompts, guards/defaults, old trials,
corpus/indexes/models, runtime containers and recovery stay intact. One positive
and one negative per variant cannot establish broad quality, strict enforcement,
forwarding correctness or a root cause. Pair success never grants qualification
or automatically replaces the production relevance instruction.

The old allowance remains **13/13 used,zero remaining**. The proposed new scope
is **at most six additional synthetic HF/Groq attempts**, one per frozen arm,
including failed and uncertain attempts. No paper data, qualification/pilot calls,
retries or automatic fallback are included. A separate fixed extension ledger
must bind an explicit approval receipt to this exact freeze and the exhausted old
allowance. A pending proposal is not approval and cannot initialize that ledger.

Implementation tasks extend the existing HF plan:

- [x] Freeze the six public requests and privacy-safe comparison protocol.
- [x] Verify semantic labels and exact original schema/system/control isolation.
- [x] Implement offline planning, pending approval proposal and guarded execution.
- [x] Test immutable approval binding, unique arms, unknown completion and budgets.
- [x] Run privacy/expected-decision mutations and full regression/type/lint checks.
- [x] Complete concrete review; the six-attempt additional allowance is ready for review.
- [x] Obtain explicit approval of the six-attempt additional allowance.
- [x] Execute and audit the approved comparison; retain all results without promotion.

Source remains in src/commands; synthetic tests in tests/unit; protocol/requests
in evaluation/week7_hf/prompt-comparison-v1; local evidence in ignored
tests/test_output. Reuse the existing diagnostic transport and original admission.
The command stays offline by default. Read-only inspections never start inference.
No new dependencies,public API changes,deployment,push,merge or runtime activation.

After observations, prepare any proposed production prompt change as a separate
reviewable diff. It needs exact-schema qualification, reviewed development and
locked holdout before enabling HF. The current diagnostic budget does not include
those later calls. Offline/source work remains independent of backup hardware.

## Ready for review — 2026-10-14

The [protocol](../evaluation/week7_hf/prompt-comparison-v1/PROTOCOL.md) and
[complete public requests](../evaluation/week7_hf/prompt-comparison-v1/requests.json)
are frozen. Manifest SHA256:
`9dd2a1e2ad2c9cb678c683a4285208b6857fd07bce1a763be5bb36f371fbd3dd`.
The fixed order counterbalances positive/negative presentation across variants.

[The runner](../src/commands/compare_hf_prompts.py) defaults to offline planning.
[The extension ledger](../src/commands/hf_prompt_allowance.py) binds this manifest,
six exact arm IDs, endpoint/model and the complete exhausted old allowance.
Each arm reserves once; pending/interrupted work consumes one slot and cannot
repeat in fresh folders. A durable registration marker prevents silently
recreating a missing funded ledger. Original allowance is read-only.

Offline command:

```powershell
.venv-win/Scripts/python.exe -m src.commands.compare_hf_prompts --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/hf-prompt-plan-new
```

An explicit `--propose-approval` operation additionally reads the old allowance
in read-only mode and writes a pending proposal. A pending/missing receipt
rejects `--execute` before credentials, service preflight or funded-ledger creation.
The approved receipt will be recorded only after an explicit user reply approving
this exact additional scope. No approval has been recorded and no live call made.

Execution after approval retains original1024MiB admission,600/384MiB live/emergency
floors, quotas/deadline, one-attempt clients and exact request enforcement. Complete
HTTP400 JSON-validation errors may continue to other independent declared arms;
timeouts/uncertain work/resources/quotas and other provider statuses stop. A
JSON-validation label on401/402/429/5xx cannot override this stop. Pair success
needs both expected objects, known usage and preservation, but remains diagnostic
only. No automatic winner, qualification, prompt replacement or paper job.

**915 tests passed, zero skips; mypy100 source files; lint/diff checks pass.**
There are39 new tests and80 combined focused reproduction checks. Expected-decision
and raw-output privacy mutations were caught and exact source bytes restored.
Tests cover answer/abstention semantics, immutable requests, pending/missing approval,
scope tampering, concurrent reservations, repeated/uncertain settlement, deletion
recovery protection, non400 stop rules and partial/failed pair rejection. Two
existing Typer/Click warnings remain.

Before final documentation updates,1761 of1762 protected hashes match: the only
changed retained file is the isolated diagnostic loader adding the new frozen
experiment. Original allowance bytes/private settings/prior trial records/freezes
and recovery are intact. All15 container identities/images/states match; actual
live corpus and installed model digests match. Original64 prior checks and
eight development/24 holdout cases validate. No original application source,
guards/prompts/defaults/dependencies/runtime activation changed. Old source-bound
records remain historical; no fingerprints were rewritten.

Local evidence: [verification](../tests/test_output/hf-prompt-prep-20261014-01/verification.json),
[mutations](../tests/test_output/hf-prompt-prep-20261014-01/mutations.json),
[offline plan](../tests/test_output/hf-prompt-offline-plan-20261014-02/metadata.json),
[pending proposal](../tests/test_output/hf-prompt-approval-proposal-20261014-02/proposed-approval.json).
The local `hf-prompt-pending-denied-20261014-01` attempt records `not_started /
approval_required`, zero inference and no funded extension. Known cumulative
cost estimate stays$0.00028545 plus eight prior unknown-cost failures; no new billing
is claimed. No push,merge,deployment,replacement,selector tuning or support contact.
