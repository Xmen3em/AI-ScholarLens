# Local implementation checkpoint — 2026-10-14

The accumulated Week7 agent, disabled HF adapter, evaluation tooling and bounded
diagnostics are saved on local branch `codex/week7-agent-hf-checkpoint`, based on
Week6 `a597f23`. Use the latest commit on that branch as the source checkpoint.
No push, merge, deployment or runtime activation is authorized.

Verification: **835 tests passed, zero skips**, mypy96 source files, focused
lint/diff checks. The latest slice has48 new isolated tests and a detected,
restored privacy mutation. All203 protected pre-turn file hashes and the live
run's source hashes matched. All15 retained containers/images/states, the
corpus/index/model state and recovery manifest were preserved. Agent and HF
defaults remain disabled; original API/key and selector/controller guards,
prompts and limits remain intact.

HF/Groq remains unqualified. The latest one-call structural diagnostic returned
HTTP400 / json_validate_failed / invalid_request_error and reported an empty
failed_generation string. This does not establish a token-limit, schema or
forwarding root cause. No paper question/passages were sent for inference.
Read [the full result](hf-structure-diagnostic.md) before new experiments.

**Eight of13 approved outbound attempts are used; five remain.** The explicit
approval is scoped to the HF unified router, openai/gpt-oss-120b:groq and the
one frozen public-paper development question/passages with synthetic checks.
Keep using the fixed cumulative allowance; never reset it in fresh folders.
Five remaining calls cannot cover five qualification calls plus the original
eight-call paired paper pilot.

The following are intentionally ignored and remain in this workspace:

- Root `SESSION_HANDOFF.md`, containing the complete chronological handoff.
- Private `.env`, including the existing API key and locally configured HF token.
- `tests/test_output/`, including snapshots, failed trials, verification evidence
  and `hf-approved-pilot-20261013/allowance.sqlite3`.
- `test_output/`, including the retained recovery bundle and operational evidence.

Continue in this existing workspace. A source checkout alone does not include
these local resources. Do not rebuild an allowance from partial trial evidence
or overwrite failed records; recover the complete retained state before paid
work. Frozen evaluation/provider metadata retain exact bytes across checkouts
through explicit Git attributes.

Next implement a local minimal reproduction and separately freeze a diagnostic
experiment that distinguishes provider compatibility from generation-limit
issues. Use public synthetic inputs and fixed privacy-safe failure categories.
Preserve the exact-contract failed trials; avoid unchanged paid repetition.
Any experimental control variant must be explicit and cannot silently change
application prompts, limits or selectors. Do not contact support or publish
the reproduction without a user request.

Then complete exact-schema qualification, reviewed development and locked
holdout acceptance, followed by the existing research-interface/server roadmap.
Missing backup hardware does not block source work. Preserve all existing
runtime/rollback containers, corpus, indexes, models, evaluations and recovery.

Start the next session with:

> Read SESSION_HANDOFF.md, docs/session-checkpoint.md and
> docs/week7-continuation.md. Continue from the local committed Week7 checkpoint.
> Start with the minimal HF/Groq reproduction and frozen compatibility experiment.
> Preserve the original API/key, guards, corpus/indexes/models, evaluations,
> containers and recovery. Keep defaults disabled and the cumulative HF allowance
> at eight used/five remaining. No deployment, push, merge, replacement or selector
> tuning. Do not block source development on missing backup hardware.
