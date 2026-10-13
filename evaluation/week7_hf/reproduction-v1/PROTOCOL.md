# Minimal HF/Groq compatibility and limit reproduction v1

Diagnostic only, frozen before inference on 2026-10-14 (Africa/Cairo).
Four predeclared independent arms, one attempt each, same approved HF unified
route and openai/gpt-oss-120b:groq. All inputs are public synthetic data.
Offline planning does not read credentials, query services or open the allowance.

1. minimal-boolean-256: bare required boolean object, short exact-output prompt,
   original controller system, temperature zero, low reasoning, strict schema.
2. exact-relevance-512: exact qualification-v2 relevance fixture/schema/system,
   changing only max_tokens from 256 to 512 relative to the retained failed trial.
3. without-maxitems-256: exact relevance fixture except the outbound schema omits
   its maxItems:30 keyword; local original canonical validation remains mandatory.
4. without-maxitems-512: same outbound schema control at 512 instead of 256.

Arms 3/4 form a contemporaneous output-limit pair. Arms 2/4 isolate maxItems at
512 tokens. Historical exact relevance at 256 is retained as a noncontemporaneous
reference; it is not rerun unchanged. The minimal boolean arm checks basic strict
object handling, not application relevance semantics or general provider quality.
No arm qualifies the provider or starts a paper job, even on expected success.

Each arm is explicitly selected, fresh evidence only, original host admission
1024 MiB, live floor 600 MiB/emergency384 MiB, original quotas, deadline and context
admission. Exactly one slot reserved/settled per execution in the existing fixed
13-attempt SQLite allowance. Four arms consume at most four of the five remaining
attempts, retaining one. Uncertain work consumes its reservation; no retries,
redirects, proxies, fallback, model/provider switch or automatic follow-up arm.
Resource/quota stops and uncertain transport failures suspend remaining live arms.
Complete provider 400 responses are observations and do not invalidate independent
arms, but still have unknown usage/cost. The 30-ID selector rejects locally.

Only fixed categories (passed, expected_mismatch, schema_invalid,
provider_json_validation, provider_error, timeout, transport_or_response_error,
resource_stop, quota_rejected), booleans/nulls/bounded counts, existing allowlisted
code/type/status, usage/timing/work and hashes are retained. Existing bounded8192
decoded error observer is reused; no provider message/generated text/reasoning,
arbitrary exception labels or credential values are persisted. No repair.

One observation per arm cannot prove causality, universal compatibility, billing,
or limit sufficiency; both tested budgets may remain insufficient. Any successful
relaxed schema is a diagnostic control, never authorization to weaken application
guards. Original application source/defaults/prompts/limits/evaluations preserved.
No support contact, publication, runtime activation, deployment, push or merge.

Sources checked 2026-10-14: Groq structured outputs advertises strict GPT-OSS120B
and requires required fields/additionalProperties:false; reasoning docs describe
low reasoning. Advertised behavior is not evidence of HF forwarding.
https://console.groq.com/docs/structured-outputs
https://console.groq.com/docs/reasoning
