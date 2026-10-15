# Private Telegram token verified; owner pairing prepared — 2026-10-15

The user created `@AIScholarLensbot` and saved the token privately. Read-only
Telegram identity/webhook requests verified the expected bot and no webhook.
The new `setup_telegram` command provides an offline check, a one-hour random
private start link and explicit verification/renewal. No first-sender adoption:
only the fresh exact code from an ordinary matching private non-bot account can
establish the owner. Forwarded/group/expired/ambiguous proofs fail closed.

Verification reads one bounded batch without confirming/dropping updates or
changing their subscriptions. It saves only the proven numeric owner ID in the
private `.env`, preserves every other byte, consumes the ignored local challenge,
and leaves runtime flags off. No messages, webhook changes, polling offset writes,
HF credentials or inference in this setup command. See
[setup and constraints](telegram-langgraph.md).

**1,047 tests pass, zero skips**, 36 new setup tests, 91 focused Telegram checks,
mypy106 and Ruff pass. Missing-module and null-state regression failures were
reproduced before implementation/fix. All35 audited private/evaluation/ledger/
recovery files match the pre-setup snapshot; source scan found no private secrets.
Five read-only Telegram requests succeeded (two preparation, three verification).
The verification found no matching proof; **owner pairing is pending**.

Original13/13 +extension6/6 HF calls remain exhausted, zero remaining. No new
budget, model qualification, runtime activation, push or deployment. Original
running API/rollback remain untouched. Next user sends the private start code,
then verify/safely save the owner; independently prepare the separately approved
HF study and candidate API8002 before live app acceptance. Existing roadmap retained.

# Previous LangGraph and private Telegram source checkpoint — 2026-10-14

The user chose LangGraph like the course, a bot private to their own Telegram
account, and initial use on their PC. [Integration and setup](telegram-langgraph.md).
The real StateGraph now runs scope/retrieve/grade/rewrite/answer/abstain nodes with
unchanged controller prompts, evidence guards, public contracts and work limits.
Graph status preserves backpressure; cancellation joins background work; external
tracing stays off without changing the caller's tracing context.

The separate disabled-by-default private polling bot supports /start,/help,/ask
and plain questions, exact owner/private-chat checks, validated cited replies,
bounded Unicode splitting, API-key/token isolation and generic errors. A durable
offset/registration and OS lock prevent concurrent/replayed admitted requests.
No question/answer history, automatic startup, API retry or provider fallback.
Both configuration templates and their strict reader/isolation tests are updated.

**1,011 tests pass,zero skips**,62new since432c5d6,128focused,mypy105,Ruff. Owner
and durable-admission mutations caught/restored. 953-test LangGraph checkpoint
7308a56 precedes the final bot/context/compatibility fixes. Installed dependencies
pass uv checks; only old jsonpointer version changes. Added optional zstandard
exposed a local HTTPX audit negotiation failure; identity encoding fixes only the
snapshot helper. The original application search driver still works. Actual full
corpus/index/model state and64 frozen checks match;15 retained containers and
private settings/API key,all old trials/freezes/recovery and both ledgers preserved.

**No paid HF calls or live Telegram calls. Original13/13 +extension6/6 exhausted,
zero remaining,19total approved attempts used.** Original running Week6 API/rollback
and HF/agent defaults remain unchanged. Old source fingerprints stay historical.

User has not created the bot. Next create it with BotFather, save token privately
and configure a verified owner ID. Prepare/review a separately bounded HF live
study and qualify the chosen model before activation. Then prepare isolated
candidate API on8002, keeping original8000 intact, and run the owner acceptance
test. These source checks do not complete live HF/app acceptance. Research UI,
quality evaluation and later server/recovery work remain. No push/merge/deployment.

# Previous offline fixture review and success diagnostics — 2026-10-14

Read [the fixture review and verified implementation](hf-fixture-review.md).
The old positive label remains plausible; "which passages" has a possible
interpretation ambiguity. It does not explain the negative-case HTTP400. Original
fixtures, labels and discarded-output results remain intact. Two separately frozen
prospective controls use "what kind of passages" with original instruction/schema/
system/limits and unchanged positive/negative evidence. No target object in prompts.

Bounded success diagnostics now retain nine fixed flags/counts after canonical
relevance validation. Requests, expected-answer guards and application controls
are unchanged. Invalid/error/non-relevance responses keep null diagnostics; no
generated strings/reasoning are saved or old records backfilled. Separate hashed
measurement contract binds future records. The fixture planner is offline-only,
reads no settings/credentials/allowances, and cannot execute inference.

**949 tests pass, zero skips**, 34 new/114 focused checks; mypy102; lint passes.
Privacy/expected-answer mutations caught and exact bytes restored. 2,622 of2,623
protected pre-documentation hashes match, with one intentional diagnostic source
change. All15 retained containers, actual corpus/index/model state,64 existing
frozen checks,private API/settings,prior evidence/freezes/recovery remain intact.

**No new paid calls. Original13/13 and extension6/6 exhausted,zero remain,19total
authorized attempts used. Both ledgers remain byte-unchanged.** No new budget or
receipt. HF/agent disabled and HF unqualified. Saved prior source hashes remain
historical; they are not rewritten for the new diagnostic source. Existing exact
qualification/development/holdout/interface/server roadmap remains pending.
Further live study requires a new concrete explicit budget and guarded runner;
the new fixtures are unavailable to existing live experiment selection.
Same local checkpoint branch; no push/merge/deployment/activation/replacement.

# Previous completed semantic prompt comparison — 2026-10-14

Read [the audited live results](hf-prompt-results.md). User explicitly approved
six additional synthetic HF/Groq calls;all six frozen arms completed. Three
expected decisions passed,one schema-valid decision mismatched,twoHTTP400
json_validate_failed errors reported empty failed_generation. **No instruction
passed both its positive/negative case.** No winner,prompt replacement or
qualification. Root cause remains unresolved;no paper data sent.

**Original13/13 exhausted and byte-unchanged;extension6/6 exhausted;zero remain.
Total19 explicitly authorized attempts used.** All six unique extension arm
reservations settled at one. Do not reset/reconstruct or repeat paid arms. The
approved receipt binds the same manifest/endpoint/model and original complete
allowance;older pending records remain historical. Further paid work needs a
new concrete,explicitly approved scope and budget.

All2604 pre-documentation protected hashes,15 container identities/images/states,
private settings/old API key,prior trials/freezes,recovery and all four live
preservation flags match. Actual RAM1179.73MiB admission/minimumlive1084.97MiB
passed original1024/600 gates. Current source unchanged fromc6e4f8f:verified915
tests/zero skips,mypy100,80 focused;no test rerun/source edits this execution.
Original app/controller/selector guards/prompts/limits,corpus/index/models/defaults
intact. Known cumulative estimate$0.00064710 plus10unknown-cost failures,not invoice.

Next offline fixture clarity review and bounded mismatch diagnostic specification,
then separately frozen/budgeted provider/transport comparison if requested.
No prompt promotion supported. Exact qualification/development/holdout and
interface/server work remain pending. Same local branch,no push/merge/deployment.

# Previous semantic prompt preparation checkpoint — 2026-10-14

Read [the prepared semantic comparison](hf-prompt-comparison.md). Three diagnostic
relevance instructions each have answering/unrelated public synthetic passage
pairs. Six exact requests frozen with original schema/system/strict/256-token
controls. Expected targets are local labels,not supplied answers in messages.

**Original allowance13/13 used,zero remain,byte-unchanged.** No new live call or
funded extension. A pending proposal requests **at most six additional synthetic
HF/Groq attempts**,one per arm. Explicit approval of that new scope is required.
The prepared fixed extension ledger binds the original complete exhausted state
and this manifest;unique arms/unknown work/durable registration prevent resetting
in fresh folders or recreating a missing funded counter. Pending execution blocks
before private settings/service work. No approval receipt has been created.

915 tests pass,zero skips;mypy100;39 new tests/80 focused;privacy and expected-
decision mutations caught/restored. Original application/guards/private settings,
prior trial evidence/freezes,15 containers,actual live corpus/models and recovery
intact;64 prior checks pass. Only isolated diagnostic tooling and current planning
notes change. All older source-bound records stay historical. Default HF/agent off.
Next approve/execute/audit the six-call comparison,then separately prepare any
production prompt change and exact qualification/development/holdout work.
Same local checkpoint branch,no push/merge/deployment/activation/replacement.

# Previous completed reproduction checkpoint — 2026-10-14

Read [the final minimal array control](hf-array-prompt.md). The prompt-only control
passed the original relevance schema/expected marker array at256 tokens; earlier
exact relevance requests remain failed. A successful minimal case is retained;
prompt interaction is a hypothesis,root cause unresolved,application unqualified.

**13 of13 approved attempts used; zero remain** in the same fixed allowance.
Never reset/reconstruct. No further inference under this approval. Source/offline
work can continue; additional live work needs a separately approved bounded budget.

876 tests pass,zero skips;mypy98;41 focused checks. Frozen array-prompt-v1 request,
protocol and manifest,explicit experiment selector,local marker cap,privacy and
allowance gates verified.1318 protected pre-documentation hashes unchanged,three
intentional diagnostic source/test changes.15 retained containers,64 prior checks,
private API/settings,corpus/index/models/recovery intact. Final-run source hashes
and all four preservation flags match; older run source bindings remain historical.
Default agent/HF remain off. Same local checkpoint branch,no push/merge/deployment.
Minimal reproduction complete;exact qualification/development/holdout and
interface/server work remain pending.

The prior checkpoints below retain their historical balances.

# Previous local reproduction checkpoint — 2026-10-14

Read [the minimal reproduction and results](hf-reproduction.md). The four
separately frozen synthetic arms are complete: minimal boolean passed; exact
relevance at512 and relevance without outbound maxItems at256/512 all returned
HTTP400/json_validate_failed with empty reported failed_generation. Root cause
unresolved, no qualification or paper work. Application controls remain intact.

**12 of13 approved attempts are used; one remains**, in the same fixed retained
allowance. Never reset or reconstruct it. Preserve the final slot for a new
separately frozen minimal array/prompt control; no unchanged paid repetition.

865 tests pass, zero skips; mypy98,30 focused checks,lint/diff and two detected,
restored mutations. All1034 protected hashes matched before documentation
updates;15 retained containers/images/states,64 prior checks,corpus/models,
private settings and recovery match. All four live preservation flags true.
Continue on the same local checkpoint branch; no push/merge/deployment/activation.
Original acceptance and interface/server roadmap remain pending.

The implementation checkpoint below is historical; its eight-used/five-remaining
balance is superseded by the current12-used/one-remaining balance above.

# Previous local implementation checkpoint — 2026-10-14

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
