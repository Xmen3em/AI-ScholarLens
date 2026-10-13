# Explicit HF/Groq route comparison v1

Frozen before route-comparison inference on2026-10-13. Parent qualification-v2:
762bbc82e159bd873d41185059bcb838a641b4fa81d8636805b1eec1417a6464.
Keep all earlier local/hosted freezes and failed trial/diagnostic evidence intact.

Purpose: compare the same exact frozen synthetic relevance prompt,system,schema
and expected decision through two HF routes,without changing model/provider.
Fixed order: unified,then provider-relay. Each arm is one independent scheduled
attempt and runs regardless of the other's valid JSON/semantic result. Do not
retry an arm,change strict mode,remove schema fields or fallback on a user request.
Never grant qualification or start an application/case collector from this result.

Unified endpoint:https://router.huggingface.co/v1/chat/completions,
wire model openai/gpt-oss-120b:groq.
Provider relay:https://router.huggingface.co/groq/openai/v1/chat/completions,
wire model openai/gpt-oss-120b,as verified by the public Hub mapping.
Both use the same configured HF token and fixed HF HTTPS host. No direct Groq
key,custom endpoint,redirect,proxy or model/provider switch. Public SDK sources
and model mapping are pinned in sources.json; compare live mapping before work.
Inherit the existing HF adapter,one active request,response/usage/timeout/privacy
guards. Only fixed URL and public wire-model name differ between arms. Hash the
entire payload with model omitted to verify identical remaining request content.
Original output256,temperature0,reasoning-low,context8192/reserve512 and exact
canonical schema remain. Large30-ID preflight still rejects with zero HF calls.

Maximum two new outbound attempts. Atomically reserve both from the same fixed
ignored hf-approved-pilot-20261013/allowance.sqlite3;five of13 approved attempts
are already used,eight remain before this comparison. Abort before paid work if
two slots cannot be reserved. Fresh directories must never reset allowance.
Unknown completion consumes the whole reservation. Each arm's client allows
one attempt and closes before the next arm. A single owned6/min quota is shared.

Host admission1024MiB,live margin600MiB/emergency384MiB,attempt timeout30s.
Stop before the next arm on unavailable/low RAM,quota denial,cancellation,timeout
or uncertain transport work. A completed HTTP400 response permits the second
predeclared arm; no failed call earns semantic/usage credit. Missing usage remains
unknown and prevents complete cost claims. No paper question/passages are sent.

Persist static route/model IDs,source/protocol/fixture/payload hashes,bounded
diagnostic booleans/counts,attempt timing/status and available token usage. Retain
only allowlisted error code/type strings;never error messages,failed generation,
prompts,rewrites,raw decisions,reasoning or credentials. Use the original dated
price estimate for known usage,report unknown paid attempts separately.

One paired observation can suggest a route difference but cannot establish a
reliable rate,causality,internal strict forwarding,task quality or serving revision.
Do not infer the router strips strict merely from a difference. Any subsequent
route qualification needs its own frozen protocol before case work,unchanged
guards/limits and the remaining cumulative allowance. Keep defaults/runtime,
API/key,corpus/index/models/evaluations/recovery unchanged;no deployment,push,
merge,model/data replacement or selector tuning. Follow interface/server roadmap
after hosted acceptance;backup hardware is not an implementation blocker.
