# Offline fixture clarity and mismatch diagnostics

The original positive question asks "Which passages does neural AI retrieval
select?" and the evidence says "Neural AI retrieval selects indexed passages."
Its expected marker is defensible: the evidence names a passage category. The
question can also be read as asking for particular passages. This is a potential
ambiguity, not evidence that the label is wrong or the cause of provider400s.

The unrelated cover-color passage is a clear negative. Its400 failure in the
concise arm remains unexplained by positive-question ambiguity. Native structured
validation failures and schema-valid semantic mismatches remain separate outcomes.
The one saved semantic mismatch cannot be inspected retrospectively: generated
JSON was discarded. Its marker count/value cannot be inferred from token usage.

Retain original qualification-v2, prompt-comparison-v1 and all trial labels/bytes.
No production prompt replacement or winner is supported by the existing results.

## Separate prospective control

New wording: "What kind of passages does neural AI retrieval select?" The positive
evidence and supplied marker remain unchanged; the negative remains the unrelated
cover-color statement. This aligns the question explicitly with the category
named in the positive evidence. The instruction is the original qualification-v2
production-format instruction; schema/system/strict/temperature/reasoning/token
limits remain original. No expected object is included in sent messages.

Two public synthetic request candidates are frozen separately. They are
offline artifacts, not new qualifications or substitutions into historical runs.
One positive/negative pair could provide a diagnostic observation, not broad
quality or proof of a root cause. It would not establish provider strict enforcement.

## Content-free successful-response diagnostics

After original canonical relevance validation, retain exactly these fields:

- expected_match, expected_empty, returned_empty.
- supplied_marker_membership and duplicate_markers.
- marker_count and expected_marker_count, each0–30.
- missing_expected_marker_count and unexpected_marker_count, each0–30.

Only booleans and bounded counts are retained. No generated marker strings,
reasoning, arbitrary property names, raw content, repair or content-derived hashes.
The fields distinguish empty decisions, valid known-marker selections, duplicates
and unknown/unexpected markers without recovering generated text. Invalid schema,
HTTP errors and non-relevance decisions keep null diagnostics; original failure
categories and expected-answer guards remain mandatory. Old decision metadata
is not backfilled. A separately hashed measurement contract binds future records.

## Authorized scope

The diagnostic helper, offline planner and separate frozen contracts are complete.
Original13/13 and extension6/6 allowances remain exhausted and unchanged. This
step made no paid calls and created no new grant or receipt. Future live work
needs a separately defined explicit scope/budget and guarded execution path.
Existing exact-schema qualification,development/holdout and interface/server
roadmap remains pending. Missing hardware does not block this source work.

## Verified implementation

`hf_success_diagnostics` validates its frozen measurement contract before the
diagnostic client is created. `hf_reproduction` adds the separately identified
measurements after original canonical validation; outbound requests and existing
expected-answer checks are unchanged. The original qualification diagnostics
remain unchanged. Past source fingerprints identify their collection checkpoints;
they are preserved, not rewritten to match new diagnostic source.

`hf_fixture_clarity` produces only a fresh local offline metadata file. It reads
no settings, credentials or allowance and has no `--execute` option. Its two
fixtures are unavailable to the existing live experiment loader. Run locally:

```powershell
.venv-win/Scripts/python.exe -m src.commands.hf_fixture_clarity --output tests/test_output/hf-clarity-offline-plan-20261014-02
```

Frozen measurement manifest:
`48b46935a42a5dd7931c8a36c5b7bcfefe5f405c62791667d14ba251190169b7`.
Prospective fixture manifest:
`8cdf31dc0c6e2947ff9e6de2e021a3a7c15b1957d1ec9e1e85a5b2bf2f7c57d1`.

Verification: **949 tests passed, zero skips**, including 34 new tests and 114
focused checks; mypy passes for 102 source files; lint passes. Deliberate raw-marker
leak and reversed expected-answer mutations were detected, then exact source
bytes restored. Before documentation updates, 2,622 of 2,623 protected hashes
matched; the sole change was the diagnostic reproduction helper integration.
Both exhausted allowance files, prior evidence/freezes, private API/settings,
all 15 retained container identities/images/states, live corpus/index/model state,
64 existing frozen checks and recovery remain intact. HF and agent defaults off.

Ignored evidence: `tests/test_output/hf-success-prep-20261014-01/` contains
verification, mutation, protected-file/container and live-preservation records;
`tests/test_output/hf-clarity-offline-plan-20261014-01/metadata.json` binds the new
offline plan to source/request/measurement hashes. There is no new cost. Root
cause and qualification remain unresolved. The next live comparison would need
its own concrete approval and bounded allowance; this planner cannot perform it.
