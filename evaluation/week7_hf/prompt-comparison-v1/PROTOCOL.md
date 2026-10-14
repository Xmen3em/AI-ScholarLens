# Semantic relevance prompt comparison v1 — 2026-10-14

Objective: test semantic relevance selection and abstention after a minimal
exact-output prompt passed while the original grading prompt failed. No claimed
root cause, qualification, application change or model selection from this study.
Three separately frozen instruction variants, each with positive and negative
public synthetic data, six proposed one-attempt arms. Expected answers appear
only in local metadata, never in the sent instruction or as target objects.

The positive data is the original qualification-v2 relevance question/passage;
the negative changes only the passage evidence to an unrelated cover-color fact.
Same supplied marker, original relevance schema including maxItems:30, controller
system, HF unified router/openai/gpt-oss-120b:groq, strict mode, temperature0,
low reasoning, max_tokens256 and original conservative context admission8192.
Only diagnostic user instructions and negative evidence differ. Application
prompts/limits/guards/defaults and all older frozen protocols/trials remain intact.

Fixed order: concise-positive,concise-negative,json-shape-negative,
json-shape-positive,per-passage-positive,per-passage-negative. Each variant must
pass both expected objects and report usage before its pair is marked passed.
The pair result is a synthetic observation, not acceptance/qualification or a
production prompt selection. Empty lists are expected on unrelated evidence.

Offline by default; plan reads no private settings, allowance or services.
An explicit proposed-approval operation may read the exhausted original allowance
in read-only mode and write a pending proposal; it cannot create a funded grant.
Execution requires a separate explicit user approval of at most six additional
attempts, pinned to this manifest/endpoint/model/arms. The original13-attempt
SQLite allowance remains exhausted and byte-unchanged. A fixed extension ledger
binds the complete old allowance and approval receipt; fresh output folders cannot
reset it. Each frozen arm may reserve once, including failed/zero/uncertain work.
Unknown completion consumes its reserved ceiling. No approval is recorded now.

Admission1024 MiB/live600/emergency384 MiB, original quotas/deadline, fresh owned
output/quota files, one-attempt client cap, exact payload hash and source/corpus/
model preservation checks. All six calls fit the original six-generation window.
No retries,redirects,proxy,fallback,provider/model switch,app activation or paper
data. Complete HTTP400 json-validation observations may continue to independent
predeclared arms. Resource/quota stops,timeouts,uncertain transport,response
errors,other provider statuses or preservation failures stop remaining work.

Retain only fixed categories,allowlisted status/code/type,booleans/nulls/counts,
usage/timing/work and hashes. Existing8192 decoded error observer and original
local schema/marker guards apply. No generated/error text,reasoning,credentials
or arbitrary exception messages retained. No repair or raw provider inspection.
Failed/absent usage remains unknown; frozen-rate estimates are not invoices.

Success criteria: six exact credential-free requests frozen and validated;
offline/approval/allowance/privacy/expected-decision boundaries tested; no new
live call until an explicit additional budget is approved. Full canonical schema
qualification and paired paper pilot remain separate later decisions. A compatible
diagnostic prompt cannot silently replace the application prompt or old fixtures.
