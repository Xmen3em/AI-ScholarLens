# Cerebras paper evaluation preparation

The selected provider is absent from the original frozen Groq/Fireworks evaluation
profile. `evaluation/week7_hf/cerebras-evaluation-v1/` adds a separate data-only
profile. Original profile bytes, labels, quality gates and resource limits stay
unchanged. Only version, explicit model/provider registration and dated token rates
differ. This profile does not yet have collector/scorer integration or funding.

The next implementation slice must bind profile identity through planning,
collection, per-run qualification, semantic reviews, scoring, development selection
and holdout locks. Add corruption/replay tests for profile/model/manifest mismatch,
preserve the old CLI defaults, and verify the full existing gates. A complete run
uses the same model for baseline and agent. Development has 64 jobs and a maximum
of 261 outbound attempts; holdout has 192 jobs and a maximum of 773, including five
fresh qualifications in each. These are future ceilings, not authorizations.

The approved two-case selector check is complete. Its initial admission stopped
at 674.26 MiB free RAM before any attempt. RAM recovered naturally; a fresh second
run reused the registered ledger and passed both cases. The counter is exhausted
and immutable. The strict combined report verifies all five cases on checkpoint
`1f7af96`; paper/app acceptance remains false. All 28 approved attempts are used.
No paper evaluation or extra schema execution is currently funded.

The model runs remotely. Local RAM is still needed by the collector and retained
services; Ollama's read-only loaded-model list was empty. Source tests pass:
1,219 full checks, zero skips, Ruff and mypy for 118 source files. Model and app
acceptance remain incomplete; the private bot is paired and disabled.
