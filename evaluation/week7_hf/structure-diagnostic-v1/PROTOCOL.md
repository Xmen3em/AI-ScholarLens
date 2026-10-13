# Bounded failed-generation structure diagnostic v1

Specified on 2026-10-14 before inference. This is one diagnostic-only attempt,
not qualification or paper collection. Preserve all earlier trials and freezes.
Parent qualification-v2 manifest:
762bbc82e159bd873d41185059bcb838a641b4fa81d8636805b1eec1417a6464.
Prior paired-route manifest:
d68d2a7e37bead8df18de30dab7033fa3b6fd208bb7187202097bdc6a6ae963c.

Send only the exact frozen synthetic relevance case through the original HF
unified route https://router.huggingface.co/v1/chat/completions with
openai/gpt-oss-120b:groq. Preserve prompt/system/schema/expected decision,
strict=true, temperature0, low reasoning, output256, context8192/reserve512.
No direct provider key, custom endpoint, redirect, proxy, retry, fallback,
provider/model switch, schema relaxation or application activation.

The diagnostic-only transport observer reads at most8192 decoded error bytes,
within the unchanged30-second attempt deadline. Inspect HTTP400 bodies only;
other responses retain original handling. Close the upstream stream on complete,
oversized, malformed, interrupted or failed reads. Replay bounded decoded bytes
through the original allowlisted label parser, without copying upstream headers
that would incorrectly decode the body a second time. An oversized body is
discarded and replayed empty. No whole-body unbounded read or persistence.

Parse outer JSON and an error.failed_generation string transiently. Require
UTF8, reject duplicate fields at any depth and nonfinite JSON constants. Do not
repair JSON, strip code fences/reasoning, coerce types or relax schemas. Original
canonical validation determines schema validity. Only fixed booleans/nulls and
bounded counts listed in profile.json may be retained. Counts cap properties
and markers at31 (meaning at least31), generated characters at8192. Prefix/
suffix flags describe fixed JSON/code-fence/reasoning tokens without storing
content. Missing/inapplicable fields stay null. No arbitrary keys/types/values,
error messages, failed generations, raw decisions, reasoning or credentials
are emitted, returned in exception messages, or saved. No usage inferred from
failed-generation text; a provider failure retains unknown usage/cost.

One active request, one-attempt client cap, same owned six-per-minute quota,
1024MiB host admission,600MiB margin/384MiB emergency stop and original30-ID
local admission rejection. Unavailable/nonfinite memory stops before inference.
Atomically reserve exactly one slot from the existing fixed
hf-approved-pilot-20261013/allowance.sqlite3: seven of13 used before this
experiment,six remain. Never reset it in a fresh output directory. Unknown
completion consumes the reservation. A cancelled/failed attempt is not retried.

The result always has qualification_accepted=false, even on HTTP200 with a
schema-valid expected decision. Do not open application/case work. Retain exact
fixture/schema/payload/source/protocol hashes, bounded structural observations,
original status/code/type/timing/available usage ledger, and preservation checks.
Inspecting a rejected generation does not establish strict forwarding, serving
revision, task quality, application speed or root cause by itself. Report the
actual structure and any limits to interpretation.

Implementation uses the documented HTTPX custom asynchronous transport boundary:
https://www.python-httpx.org/advanced/transports/ and
https://www.python-httpx.org/async/ . Runtime HTTPX is0.28.1; delegate the existing
client transport without changing application source/settings or dependencies.
Keep original API/key,selector/controller guards/prompts,corpus,indexes,models,
evaluations,runtime/rollback containers and recovery bundle. No deployment,push,
merge,data/model replacement or existing selector tuning. Follow acceptance and
research-interface/server roadmap; missing backup hardware is not a source-work
blocker.
