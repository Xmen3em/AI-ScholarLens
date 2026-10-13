# Versioned HF qualification and provider-error diagnosis

Current continuation: [the explicit route comparison](hf-route-comparison.md)
is implemented and executed. Both scheduled HF/Groq routes return400 with
json_validate_failed for the same frozen synthetic request; no paper cases.
787 tests pass,zero skips. **7/13 approved attempts used,6 remain**. The fixture,
failed trials and allowance are retained. This report records the earlier
qualification/diagnosis checkpoint and its historical attempt balance.

Implemented on2026-10-13 after the user said "go". The failed
[trial04](hf-pilot04.md), original hosted v1/local v2 freezes and all previous
evaluations are retained. Application HF/agent defaults and active Week6 runtime
remain unchanged. No selector or production controller prompt is tuned.

## Frozen inputs and shared allowance

The [additive fixtures](../evaluation/week7_hf/qualification-v2/fixtures.json)
freeze exact prompt/system/schema/expected objects. Controller probes use the
existing production instructions, `CONTROLLER_SYSTEM` and JSON data serialization;
the relevance input explicitly contains marker string`"[1.1]"`. Synthetic
selector probes include an evidence catalog and exact target JSON. All five
canonical schemas and expected values, generation controls, quotas, deadlines,
memory/usage/quality gates remain unchanged. The original30-ID diagnostic still
rejects locally without a paid call. Fixture manifest SHA256:
`762bbc82e159bd873d41185059bcb838a641b4fa81d8636805b1eec1417a6464`.

`--qualification-v2` selects this explicit revision and restricts execution to the
approved one-case BM25/JSON Groq pilot. Metadata, per-check hashes, reviews and
scoring bind its manifest. Bounded diagnostics expose expected-match,
supplied-marker-membership and duplicate-marker booleans plus a marker count;
they never expose raw decisions or reasoning. The existing failed v1 pilot cannot
be rerun through the old default path. Metadata now records terminal status too.

A fixed ignored SQLite allowance, independent of output folders, atomically
reserves capacity against the user's13-total-attempt approval. Trial04 consumes2;
its complete evidence fingerprints seed the allowance. Pending runs reserve
their whole ceiling, unknown completion consumes that reservation, and repeated
settlement/changed prior evidence/simultaneous overspending fail closed. The new
pilot received11, not a reset13. A per-run client cap blocks a twelfth request.

## Observed revised trial and one-call diagnosis

Trial05 passed unchanged1024MiB BM25 admission, with1655.48MiB free recorded.
Scope passed with190 input/63 output tokens,44 reasoning tokens within output,
832.40ms duration and minimum1657.05MiB free. The next relevance call returned
HTTP400 in685.49ms, without usage. Qualification stopped before rewrite/selectors,
case collection or a temporary app. Its two attempts settled against the shared
allowance, leaving9. Known-usage estimated cost for scope is$0.00007575 at frozen
rates; the failed call's usage/cost is unknown, not zero.

Because HTTP400 alone was inconclusive, a separately
[frozen one-attempt diagnostic](../evaluation/week7_hf/qualification-v2/DIAGNOSTIC.md)
reproduced only that exact synthetic relevance request. It always reports
qualification_accepted=false and cannot open paper collection. Diagnostic SHA256:
`f6dbb28536907fdefa4240f93e62cb93c354e21112c8bb5cbe31287133b4b1b5`.

The HF adapter now reads at most8192 decoded error-body bytes within its existing
30s attempt deadline and retains only fixed allowlisted error code/type strings.
Unknown labels, error messages, failed generations and malformed/duplicate/
oversized error objects are discarded. API errors remain generic; no retry,
redirect, proxy, schema fallback or content logging was added. Failed attempts
retain the requested schema hash as well as the fixture hash.

The diagnostic returned HTTP400 with code`json_validate_failed` and
type`invalid_request_error`, in865.61ms; usage remains unknown. Minimum host free
RAM was1922.57MiB. The label identifies a provider-reported JSON validation
failure; it does not establish whether the underlying problem is generation,
schema support or how the intermediary forwards strict-mode options.

**Total approved attempts used:5 of13;8 remain.** This turn made3 synthetic
attempts, with2 unknown-usage failures. Across both trials and the diagnostic,
known-usage estimated cost is$0.00018090 plus unknown failed-attempt cost. These
are estimates, not invoices or credit-balance verification. **No paper question
or corpus passages were sent for inference**, no paper response/semantic review
exists, and the current model/provider remains unqualified. The saved scorer
rejects trial05. All four preservation checks passed for trial and diagnostic.

## Source-grounded next step

Our request uses the nested JSON-schema name/schema/strict structure shown in
[HF's official guide](https://huggingface.co/docs/inference-providers/guides/structured-output).
The [official SDK input type](https://raw.githubusercontent.com/huggingface/huggingface_hub/main/src/huggingface_hub/inference/_generated/types/chat_completion.py)
also includes the strict field. These references validate the intended envelope;
they do not prove the hosted router's internal forwarding behavior.

Groq currently lists GPT-OSS120B for strict mode, requires required fields and
closed objects, and distinguishes schema compliance from semantic accuracy.
[Groq structured-output documentation](https://console.groq.com/docs/structured-outputs).
Thus the prior wrong expected decision and the new provider-reported validation
failure are different observations. There is no evidence-based reason to remove
the existing schemas/limits to obtain passing qualification.

Next prepare an explicit, separately versioned provider-route comparison for
the same synthetic schema before choosing another model. HF's
[public common provider helper](https://raw.githubusercontent.com/huggingface/huggingface_hub/main/src/huggingface_hub/inference/_providers/_common.py)
supports HF-token provider proxy routing and retains non-null request parameters;
its [Groq helper](https://raw.githubusercontent.com/huggingface/huggingface_hub/main/src/huggingface_hub/inference/_providers/groq.py)
uses the provider's chat-completion route. Comparing that separately specified
route with the current `/v1/` router could isolate an intermediary difference;
this is a hypothesis, not a measured result. Pin reviewed source and public
model mapping before coding any additional route. Keep the same schemas,
prompts, controls, existing token billing and cumulative8-call remainder;
do not add an automatic fallback or rerun failed qualifications in place.
No alternative route/provider call occurred in this checkpoint.

Only a complete successful qualification permits paper pilot work. Complete
reviewed development and a locked same-pair holdout still precede acceptance,
research-interface work and server preparation. Missing backup hardware does
not block source development; deployment/push/merge remain outside scope.

## Verification and evidence

**770 tests passed,zero skips**, including disposable PostgreSQL.29 new tests
cover frozen inputs, diagnostic privacy, concurrent/pending cumulative allowance,
exact scope, collector TCP cleanup, stale revision reviews and one-call bounds.
Mypy92 source files and changed-file Ruff/diff pass. Mutations omitting the prior
two attempts or allowing arbitrary provider error strings were detected; exact
source bytes restored before passing full checks. The final source has no
dependency, lockfile, private environment, Compose or production route changes.

Before/after audit verifies173 of177 prior protected files unchanged; four
approved source files changed for evaluation/error diagnostics. Original
controller/selector guards/prompts, old labels/trials, data/models and recovery
manifest match. Both older freezes and the new fixture/diagnostic freezes verify;
64 frozen/prior local checks pass. All15 retained container IDs/images/states
match,5 running, after disposable test cleanup. Source remains uncommitted on
master at a597f23; no push,merge,deployment,activation or replacement.

Evidence: `tests/test_output/hf-qualification-v2-20261013-01/final-audit.json`,
mutation/containers/preservation files in that directory,
`hf-development-pilot-20261013-05/`,
`hf-development-diagnostic-20261013-01/`,
`hf-pilot05-review-template-20261013-01.json`,
`hf-pilot05-score-20261013-01.json`,
`hf-revision-final-full-20261013-01/`, and fixed
`hf-approved-pilot-20261013/allowance.sqlite3`. Keep this allowance intact.
