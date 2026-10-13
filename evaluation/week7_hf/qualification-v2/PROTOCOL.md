# Qualification fixture revision v2

Frozen before new inference on 2026-10-13. Parent hosted-agent-v1 manifest:
3b42fccb34bc542e91ccdd3df0d8acb85c0bc86f7237eebdb214e6e9dbfc37a1.
Keep all original local/hosted protocols, failed trial04 and guard/prompt files.

This additive revision freezes exact synthetic prompts, systems, schemas and
expected objects in fixtures.json. Controller checks use existing production
instruction/system and JSON data serialization, including marker "[1.1]".
Selector probes use the original RAG system and exact synthetic answer objects.
Original canonical schema/expected values, temperature0, output256/512, input
admission, concurrency, deadlines, quotas, memory and quality gates are unchanged.
Fixture ambiguity in the earlier trial remains a hypothesis. No task selection,
selector tuning or holdout-derived changes. Failed trials are retained.

Persist only fixture/schema/request hashes and diagnostics: expected-match,
supplied-marker-membership, duplicate-marker boolean and marker count. Never
persist raw decisions, rewrites, reasoning, prompts or provider response bodies
in run records. Static synthetic inputs reside only in this frozen public fixture.
Stop at the first failed qualification; no within-run retry/downgrade/failover.
The 30-ID selector continues to reject locally without any HF attempt.

The approved pilot is exactly development case
week7-development-narrative-rubrics-literal, BM25/JSON baseline and agent,
openai/gpt-oss-120b:groq, HF router HTTPS. Total approval is13 outbound attempts;
trial04 consumed2. Reserve remaining capacity atomically in the fixed ignored
tests/test_output/hf-approved-pilot-20261013/allowance.sqlite3, seeded from
trial04 fingerprinted qualification/completion/records/metadata. A fresh output
directory does not reset allowance. Pending/interrupted work reserves its entire
ceiling; unknown completion burns that reservation. Verify exact scope before
claiming. Current run is capped at11, even though all theoretical job ceilings
sum to13. Stop before any outbound call beyond that capped budget.

No paper cases before all five synthetic checks pass with known usage/memory.
Any collected pilot remains incomplete development evidence and cannot pass
development/holdout acceptance. Bind metadata, qualification, review and scores
to this revision's manifest hash. Keep the parent full-matrix quality gates.
No production activation, deployment, push, merge, model/data replacement.
