# Cerebras paced comparison v4

This additive profile grants no inference calls or application activation.
It inherits every evidence-v3 field and gate; only its version changes.
The source-bound collector admits at most six requests in every rolling
61-second interval, preserving the API quota and stopping on unexpected 429.
It waits 61 seconds after qualification completes. Admission waits are outside
request latency, as before. No request retries or quota increases are allowed.

Historical validation reuses only pure frozen inputs within one synchronous
operation, checks frozen bytes before and after that operation, and discards
all memoized values afterward. Source, receipts, registration, SQL accounting,
resource and history checks remain fresh. No TTL or stat-only proof cache.

Keep the model openai/gpt-oss-120b:cerebras, three sentences per passage and
ten total candidates; all five canonical qualification payloads and controller
system stay unchanged. Keep native input/schema caps, quality/latency gates,
RAM admission/live/emergency floors, work bounds and complete 64/192 matrices.
No holdout labels are used for tuning. Offline timings are not acceptance.

A separate source/history-bound development ceiling is at most 261 attempts:
five fresh qualifications and the full 64-job comparison. Failed or uncertain
attempts count; failed checks stop. All 249 past attempts remain used:
28 historical schema/prompt, 97 completed development, 124 stopped development.
The old 164 and 137 unused slots are not transferred, replayed or reset.
This scope requires fresh explicit approval and its own fixed ledger.
A separate holdout ceiling of 773 and accepted full holdout precede explicit
private PC/owner Telegram activation and a real owner bot test.
