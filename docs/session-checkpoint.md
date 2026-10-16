# Private Telegram development mode running — 2026-10-16

The user explicitly requested live manual Telegram/HF testing while editing the
agent, with quick RAM handling. This supersedes earlier instructions to leave
the bot disabled for development testing. A separate opt-in development mode is
now running on localhost8002 with the paired owner and `@AIScholarLensbot`.
It reports `accepted:false`; the rejected holdout and normal acceptance guards
remain unchanged. No old evaluation grant is reused and no automated paid smoke
question was sent. Owner questions now trigger remote HF/Cerebras inference.

Run `./Telegram.ps1`, `./Telegram.ps1 -Restart` after edits, or
`./Telegram.ps1 -Stop`. The API and bot share one Python process and use BM25
retrieval, requiring no local model inference or SQL startup. RAM admission
remains 1,024 MiB/live 600, with 3,117.15 MiB free at the final audit. Local SQL
credentials failed during the first attempt; this test mode no longer depends
on SQL, and no credentials/data/containers changed. Global private flags stay
false; the process uses isolated enabled copies. Original API8000 is preserved.

152 targeted tests pass, zero skips, plus Ruff, mypy on two source files and
PowerShell parsing. Actual scripted restart, authenticated status, unauthorized
401 and bot polling are verified. All 585 historical protected paths and all 15
retained containers match. Runtime/log pointers:
`data/pc-app/development-process.json`. Verification:
`tests/test_output/telegram-development-launch-20261016-01/verification.json`.
Usage and design: [telegram-development.md](telegram-development.md).
Known answer-quality limitations remain; a real owner question/reply is still
the user's manual test. No new full evaluation or production acceptance claimed.

# Historical: Full Cerebras holdout completed; quality rejected — 2026-10-16

The user explicitly approved up to 773 additional calls in
`call_b003f7dbf66a4b71a4568fa76fd020bf`. All five fresh checks and **192 jobs
completed** on unchanged paced-v4 source. **345 calls used, all settled/known;
719 cumulative.** Remaining 428 stay bound to this completed holdout, as do
earlier unused 164/137/136. No retry or transfer. App and Telegram remain disabled.

Holdout acceptance is **false**: all four comparisons fail the regression gate.
Each agent cell falsely abstains on three positives versus two for baseline.
Agent BM25/hybrid fact coverage is 68.75%/78.13%, baseline 70.83%/78.13%; agent
multi-paper coverage is zero. All 64 negatives abstain correctly; no scope,
request, attribution, schema, usage or hybrid-fallback errors. Agent p95
9.307–10.070 s and baseline 2.681–3.935 s pass unchanged limits. Codex reviewed
108 responses/170 quotes (26 unique,154 relevant); not independent human review.
Known-usage estimate USD 0.20357985 is not an invoice.

Saved-output diagnosis identifies the 0.60 per-paper lexical filter excluding
the retained SpeechGym abstract at 0.50 and the TTPO half of a combined question
at 0.545. No parameter, source, prompt, label or gate changed; no holdout tuning.
This inspected holdout cannot become unseen acceptance for a tuned replacement.
Next: generic synthetic development regressions, evidence-filtering/multi-paper
correction, offline verification and a separately versioned evaluation scope
with fresh unseen holdout before any new calls or private Telegram activation.
Token/owner pairing already exist; nothing new is needed from the user now.

Result and limits: [hf-cerebras-paced-holdout-result.md](hf-cerebras-paced-holdout-result.md).
Run: tests/test_output/hf-cerebras-paced-holdout-live-20261016-01/.
Execution: tests/test_output/hf-cerebras-paced-holdout-execution-20261016-01/.
Seal32files SHA32928bd5969ab1ce09324dee5aa51bb56dac59c9a33072bd8609b0dc0242c0bf;
next protected-expanded baseline585paths. Preserve all sealed files/ledgers.
Final audit:552 old paths/15 container identities-images-states/5running,
58papers2775chunks/model digests/source intact. API8000up,8002closed, all flagsfalse.
Minimum request RAM1130.41MiB exceeds live600; admission2599.09MiB passes1536.
Source digest8baa1a6e12e3e14e7c061dfec03653e3670dee929fde5340aa889b944c950487
stillba1f168; collection296835a. Last1386tests0skips/Ruff/mypy127 stillpass;
no source changes or unnecessary suite reruns. Collector63481/audit91459 finished.

# Historical: Cerebras development accepted and locked; holdout pending

The complete paced-v4 comparison passes **all 64 jobs and five fresh schema
checks**, with no failed gates. All 48 positive answers cover both required
facts, all 82 quotations are relevant and all 16 negative answers abstain.
Agent p95 is 9.74–11.27 seconds; baseline 2.67–6.44 seconds, against unchanged
20/10-second limits. Zero scope/attribution/request errors, unknown usage or
hybrid fallbacks. Review is Codex development annotation, not independent
human or holdout acceptance. The app and private Telegram bot remain disabled.

**125 new calls used**, all settled/known; **374 cumulative** (28+97+124+125).
The latest completed grant's unused 136 and earlier unused 164/137 cannot
transfer or replay. Returned-usage estimate USD 0.07434775 is not an invoice.
The user approved this completed scope in call_ac6574a5a0e749d4ae647ff98af4c1f1.
Exact approval, receipts, full source/corpus/model preservation and accounting
are in tests/test_output/hf-cerebras-paced-development-execution-20261016-01/.
Its post-run audit preserves **520 paths**, all 15 retained containers/images/
states, five running/no extras, 58 papers/2,775 chunks and model digests.
API8000 stays up; API8002 is closed; global HF/agent/Telegram remain false.
Minimum sampled request RAM is 1,739.98 MiB. Admission rebounded to 2,193.96 MiB
and passed after earlier zero-call low-RAM checks; thresholds are unchanged.

The accepted full development selection is
 tests/test_output/hf-cerebras-paced-development-live-20261016-01/selection-lock.json,
byte SHA256 9ddebd299671abfe932f225c1aaf2a9df172a6863d833afa8cccc0b71a09335e.
Source remains ba1f168, collected at e0fe52e; source-map digest
8baa1a6e12e3e14e7c061dfec03653e3670dee929fde5340aa889b944c950487.
Profile hosted-cerebras-paced-v4 manifest
 a289b0f75fdf6af2da9687e9e0ecd8df281598cb69b235141704515a34f31ca7.
All **1,386 tests, zero skips**, Ruff/mypy127 remain passing; no source change.
Details: [development result](hf-cerebras-paced-development-result.md).

The separate **full 192-job holdout** proposal is now concrete. It needs one
fresh ceiling of **up to 773 additional calls**, including five fresh checks;
no holdout calls are approved. Metadata/receipt:
 tests/test_output/hf-cerebras-paced-holdout-proposal-20261016-01/,
receipt byte SHA256 dd33e8d9c5a87216f86869ef7dcd90bb5deaa799284cb8bff7da0d7b1c39fd43.
It binds the accepted selection, current source and all 374 previous attempts.
The actual pending-receipt execution rejects before credentials/network/funding.
Both fixed holdout ledger and registration are absent. Provider catalog checked
09:19:24 UTC: live/structured, unchanged .35/.75 rates. Conservative bound USD
2.374656 is not an invoice. Current preparation RAM 1,973.74 MiB passes; check
again at execution. Scope: [holdout execution](hf-cerebras-paced-holdout-execution.md).

Next: explicit approval, admitted full holdout collection, honest reviewed
scoring and source-bound app acceptance only if all gates pass. Separate
explicit private PC/API/owner Telegram activation and an actual bot test follow
accepted holdout. Token and owner pairing are already configured. No further
setup is required now; older proposal/balance sections below are historical.

# Paced HF/Cerebras fixes verified; fresh approval pending — 2026-10-16

Source checkpoint `ba1f168` follows `dca1a18` (quota pacing), `8582a96`
(operation-scoped validation), and `6a59c56` (additive immutable profile).
The source-map digest is
`8baa1a6e12e3e14e7c061dfec03653e3670dee929fde5340aa889b944c950487`.
`hosted-cerebras-paced-v4` preserves every inherited gate and uses manifest
`a289b0f75fdf6af2da9687e9e0ecd8df281598cb69b235141704515a34f31ca7`.
Complete scope and evidence: [hf-cerebras-paced-execution.md](hf-cerebras-paced-execution.md).

**All 1,386 tests pass, zero skips**, in 946.66 seconds, with two existing
Typer dependency warnings; Ruff and mypy127 pass. The final JUnit report is
`tests/test_output/hf-cerebras-local-runtime-fix-20261016-01/full-final.xml`.
The initial two failures were preserved-output collisions from a reused test
basename; the clean full rerun uses a globally unique name. No source or test
assertion changed between these runs. Initial evidence is retained.

Same-input historical validation improves 3,629.608 ms -> 373.998 ms (9.7x),
with identical output and networking forbidden. Fresh v4 additionally verifies
the stopped history and averages 911.974 ms. Current-source local rehearsal
passes 32 cells/60 native payloads using real retained retrieval/LangGraph and
synthetic decisions, with HF transport forbidden. These are offline checks,
not fresh answer-quality, live-latency or application acceptance.

The final audit preserves **480 protected paths**, 15 containers/images/states,
five running/no extras, the same 58 papers/2,775 chunks and model digests.
API8000 remains up; API8002 is closed; HF/agent/Telegram remain disabled.
All historical accounting is unchanged. No new inference or Telegram traffic.

**249 historical attempts remain used**: 28 + 97 + 124. The stopped v3 grant's
137 and older grant's 164 unused slots are not transferred or replayed. The
new pending proposal in
`tests/test_output/hf-cerebras-paced-development-proposal-20261016-01/`
binds the current source and all histories. Receipt SHA256:
`1db8bf7374eb94f72b5873d47912e76f58063a2fb78cbe015dbe4c2fb888ea6d`.
It proposes one fresh maximum of 261 calls: five qualifications/full 64-job
development. An actual pending-receipt execution rejects before Settings,
networking or ledger allocation. New fixed ledgers/registrations and an
approved receipt are absent. The checked cost bound is USD 0.801792, not an
invoice; rates/resources/source/accounting must be checked again at execution.
The audit had 1386.74 MiB free and returned
`insufficient_memory` for hybrid admission (requires 1,536 MiB).
No threshold was lowered; collection must wait for a passing current check.
A later collector-only probe also rejects at 1,293.56 MiB. No grant or call is
created. The preparation seal contains 39 files and the expanded baseline has
520 protected paths, in the same preparation directory. Seal SHA256:
`e5c0222dd1baf91598b713694ba4d1334482e59df93c036b1890c29b6ce0bb1e`.

Next: explicit approval of this concrete new ceiling, admitted collection,
honest review/scoring and a selection lock only if the full development passes.
A separate full 192-job holdout/up-to-773-call approval and accepted result
precede explicit private PC/owner Telegram activation and the real bot test.
Token and owner pairing are already configured; no repeated setup is needed.
The preparation is complete; the app remains unaccepted and disabled.
Older approval/balance sections below are historical.

# Approved evidence comparison stopped; local fixes next — 2026-10-16

The user approved the new 261-call scope. Five fresh schema checks passed and
63 of 64 jobs were recorded; the local API returned HTTP 429 at job 63, so the
collector stopped before the last baseline job. **124 new attempts used, all
settled/known; 249 total used.** No retry or transfer of the remaining 137 slots.
The earlier 164 remain bound to their old completed grant. No holdout or app/bot
activation. Collection stayed on source `50ab668`, digest
`a5aa4ad496a324c69ccbce8a42584fea2b899a317319238920d642813944cb26`.

Review finds 100% fact coverage and relevance across all positive baseline/agent
cells, all 82 selected quotations relevant, and zero scope errors. All 14
successful negatives abstain; the failed/missing negatives earn no credit.
**Development acceptance is false** because the matrix is incomplete, the 429
fails its cell, and agent p95 is 32.85–34.54 seconds against the unchanged 20-second
target. This is development evidence with Codex review, not independent holdout.

The final audit preserves all 449 protected paths, all 15 retained containers,
58 papers/2,775 chunks/model digests and disabled flags. API8000 stays available;
API8002 is closed. Minimum sampled paper-request RAM was 1,222.04 MiB. Source and
all preservation checks pass. Known-usage estimate USD 0.07419595 is not an invoice.
Full evidence and limitations:
[hf-cerebras-evidence-development-result.md](hf-cerebras-evidence-development-result.md).

Read-only profiling identifies repeated historical validation: about 3.6 seconds
per check, 834 qualification loads / 4,170 schema builds / 10,159 opens in one
profile. The collector's batch timer also drifts from the API's actual fixed
window after slow requests. Next: offline regression-led scheduling and validation
fixes, measure, verify and prepare any new execution scope before a fresh approval.
The source has not been changed yet; all 1,354 source tests remain the last full
passing baseline. No live test process remains; collector37713, review3733,
profile64798 and audit40300 completed. Older pending-approval text below is historical.

# Bounded evidence profile prepared; fresh approval required — 2026-10-16

The user asked to commit the current work and continue. The scope/catalog
correction was already committed as `acf9ddf`; subsequent local commits are
`d2bdf7a` (additive profile), `b126a8c` (separate history-bound funding) and
`984735a` (collection/scoring/acceptance/private runtime integration).
The current source-map digest is
`a5aa4ad496a324c69ccbce8a42584fea2b899a317319238920d642813944cb26`.

The new `hosted-cerebras-evidence-v3` profile explicitly admits three sentences
per passage and ten total candidates. Every other frozen quality/resource/input/
schema/work gate is preserved; older profiles/defaults remain unchanged.
The complete implementation and concrete approval scope are in
[hf-cerebras-evidence-execution.md](hf-cerebras-evidence-execution.md).

**All 1,354 tests pass, zero skips**, in 939.68 seconds, with two existing Typer
dependency warnings. Ruff and mypy126 pass. JUnit:
`tests/test_output/hf-cerebras-evidence-profile-prep-20261016-01/full.xml`.
The local rehearsal checks 32 first-pass cells and 60 native payloads with real
retained search/embedding and service/LangGraph execution; maximum 4,573 input
tokens, 13,651 payload bytes and 947 schema bytes, no fallback. HF generation is
forbidden and decisions are synthetic; this is not model-quality acceptance.

Final audit: **419 protected files** unchanged; all 15 retained containers and
their images/states match, five running/no extras. Original API8000, 58 papers/
2,775 chunks and installed model digests match. API8002 is closed; global HF,
agent and Telegram remain false. All earlier evidence/private setup is intact.
Full pytest session96051 and final audit13983 completed successfully; no test
process remains. An earlier audit saw pytest's temporary containers; the final
audit after cleanup passed. Final free RAM was 2,749.75 MiB, admission passed.

**No new HF calls or Telegram traffic.** Earlier 28 plus completed failed-run
97 attempts remain **125 used**. The old 164 unspent slots cannot fund this
changed source/profile. The fresh pending development receipt is
`tests/test_output/hf-cerebras-evidence-development-proposal-20261016-01/proposed-approval.json`,
SHA256 `79f1875b101ffc13a664693c2a48fc2e79e59b4d87690a03d723f46efe4c59f3`.
It proposes one separate maximum of 261 additional attempts: five fresh unchanged
qualifications plus all 64 development jobs, bounded public paper data. Failed
or uncertain work counts; failed checks stop. Both new ledgers/registrations and
an approved receipt remain absent. The public catalog still lists the route live
and structured at the frozen rates; the estimated bound is USD 0.801792, not an
invoice. Recheck source, provider, RAM and accounting before any execution.

Next: explicit approval of that concrete scope, fresh admitted execution, honest
review/scoring and a development lock only if gates pass. A separate full
holdout approval and accepted 192-job result precede private PC/owner Telegram
activation and the real bot test. The token and owner pairing are already done.
The preparation is complete; the application is not yet accepted or enabled.
Older checkpoint sections below retain their historical balances and outcomes.

# Offline scope/catalog correction — 2026-10-16

The source now clarifies scope using the ingested categories and adds an opt-in
catalog cap. The default remains one sentence per passage. A three-sentence,
ten-candidate experiment exposes the missing names in all 16 affected saved
contexts; its 52 constructed native selector/scope payloads fit the unchanged
input/schema limits. This is offline evidence availability, not improved model
quality. Existing frozen HF profiles reject the new candidate option.

**All 1,334 tests pass, zero skips**, with two existing Typer dependency warnings;
Ruff and mypy126 pass. The fresh full run follows correction of two environment
template documentation omissions. No tests or quality gates were removed.
JUnit: `tests/test_output/hf-cerebras-evidence-fix-20261016-01/full-02.xml`.
Final source-map digest:
`66626db90a270820b19e1d9e1fc78693fae21c399b790aefc4c08c0f2e9ec420`.
Details and remaining profile/approval boundary:
[hf-cerebras-offline-correction.md](hf-cerebras-offline-correction.md).

No HF calls or Telegram activity for this correction. Previous 125 attempts stay
used; 164 remain unspent in the completed source-bound grant. The app/bot remain
disabled. All 400 protected files and 15 retained containers match; API8000,
58 papers/2,775 chunks and installed model digests are preserved. The earlier
failed development result below remains authoritative for
its captured source; it has not been replaced with a passing model result.

# Approved Cerebras development completed; quality failed — 2026-10-16

The user approved the corrected **single 261-call scope**. All five fresh schema
checks and all 64 development jobs completed on source `005651b`, using **97 new
calls**, all settled with known usage; earlier 28 remain unchanged, 125 total used.
The other **164 are unspent**, bound to this completed scope, with no replay or
transfer to another run. Returned-usage cost estimate is USD 0.04131235.

Semantic review and scoring **reject development acceptance**: 12 incorrect scope
rejections and regression in all four BM25/hybrid × JSON/SSE comparisons. Agent
fact coverage is 33.3% versus baseline 66.7%. No selection lock, holdout or app/bot
activation. Offline catalog reconstruction found the one-sentence picker omits
the required benchmark-task/index names; the vague scope prompt also rejects
robotics questions despite the corpus's `cs.RO` policy. Correct these offline
before proposing fresh inference. No application source changed in this run.

All 382 protected files, all 15 retained container identities/images/states,
API8000, 58 papers/2,775 chunks and model digests match. Global HF/agent/Telegram
remain false; API8002 is closed. Holdout funding remains absent. Full result,
review limitations, accounting, evidence paths and next work:
[hf-cerebras-development-result.md](hf-cerebras-development-result.md).

The preparation and pending-approval text below is historical; the current
authorization and outcome above supersede its call balances and next steps.

# Current Cerebras token-admission correction — 2026-10-16

Source checkpoint **005651b** (tokenizer foundation `bb85d8d`, tokenized profile
`8bb7a7b`, funded stop-on-failure guard `005651b`). The local native
prompt rehearsal found that the first full relevance prompt cannot pass the old
schema-inclusive UTF-8 byte limit. The separate immutable
`evaluation/week7_hf/cerebras-tokenized-v2/` profile corrects counting with the
published GPT-OSS BPE vocabulary; old profiles and defaults retain byte admission.
Full passage text, schemas, questions, 8,192-token context, output/template reserves,
quality gates, work bounds and RAM thresholds remain intact. The 30-candidate
schema still rejects locally under an explicit schema byte cap.

The local first-pass development rehearsal passes 32 BM25/hybrid cells and 60
native payloads, maximum 4,573 conservative input tokens/13,651 bytes, no fallback,
with source/corpus/model preservation. It uses synthetic model decisions and no
HF transport; it does not qualify semantics, real model decisions or rewrites.
**All 1,323 current-source tests pass, zero skips**, in 865.49 seconds, with two
existing Typer warnings. Ruff and mypy for 126 source files pass. Full JUnit:
`tests/test_output/cerebras-tokenized-full-20261016-03.xml`.
All 367 protected files match, including the original 352. All 15 retained
container IDs/images/states match, five running and no extras. Original API8000,
58 papers/2,775 chunks and installed model digests match the frozen snapshot.
The tokenizer reference matches the pinned package on five synthetic Unicode/control-looking examples. Its 3.6 MB public table
is prepared explicitly in ignored storage; no model weights or implicit downloads.

The current pending proposal is
`tests/test_output/hf-cerebras-tokenized-development-proposal-20261016-02/proposed-approval.json`,
byte SHA256 `f324be5d4444af0c0ff970926f51e5def71e0256edf09bfb34cfcce7897206d1`.
Source-map digest `41fc2932e58fc53ecacd9bcabd83374bd92fa989ca0c5eb3704b4f04192d65c0`.
This supersedes the old unapproved proposal; maximum 261 remains a single proposed
allowance. All 28 old attempts remain exhausted. No new approved receipt, task
ledger/registration, HF attempt, paper transfer to HF, app startup or Telegram.

One initial regression run was stopped because the task dependency cache under
`tests/test_output` exposed 102 third-party regex test methods to discovery. The
cache was moved within the workspace to ignored `.cache/uv-tokenizer-20261016`;
no tests, quality thresholds or skip rules were removed. The project suite completed
with its intended discovery; no exclusions or skip rules were added. The final
read-only preflight measured 1,597.38 MiB free and passed the preserved 1,536 MiB
hybrid admission; recheck immediately before any execution. No current user RAM
action is needed. Global HF/agent/Telegram flags remain false. Verification and
expanded preservation baseline are saved under the pending proposal directory.

The funded collector now stops after any failed paper response. A fault-injected
unknown relevance marker previously allowed advancement to a queued job; the new
regression proves immediate stop, exactly seven mocked attempts and one record.
All 13 collector regression tests pass. Prompt-generation files are unchanged from
the successful local rehearsal. The final current-source full suite passed. No test process remains running.
The new allowance is still unapproved and both task ledgers/registrations are absent.
Next: explicit 261-call development approval, admitted execution, honest semantic
review/score and development lock; separately funded holdout of up to 773 calls follows, then
accepted source lock and actual private PC/owner Telegram activation/acceptance.
Goal ACTIVE; source preparation is not model-task or app acceptance.

# Cerebras paper evaluation and private runtime prepared — 2026-10-16

Source checkpoint **16af44a** on `codex/week7-agent-hf-checkpoint` prepares the
selected `openai/gpt-oss-120b:cerebras` route for full paper development/holdout,
reviewed acceptance and isolated private PC/Telegram activation. The source-map
digest is `708210a9f1e64942020b3972bfd279d75adc2ee0a0088e1b5bb615ca82ae7a78`.
Local commits: `92be5d4` profile/funding; `189583e` guarded collector; `c731d63`
scoring/acceptance; `16af44a` qualified runtime. No merge, push or deployment.

**All 1,307 unique tests verified; no unresolved skips.** The full suite passed
1,275 and skipped 32 PostgreSQL cases while Docker Desktop was stopped. After
restoring Docker and the exact three previously running containers, all 33
integration tests passed (one was already included in the full run). Two existing
Typer/Click warnings remain. Ruff and mypy for 124 source files pass. Full evidence:
`tests/test_output/cerebras-paper-full-20261016-01.xml` and
`tests/test_output/cerebras-paper-database-20261016-01.xml`.
All 352 protected files match. All 15 retained IDs/images/states match, five running,
zero extras. Original API8000, 58 papers/2,775 chunks and installed model digests
verify against the frozen source. Private configuration and recovery are intact.

The frozen Cerebras profile preserves every original quality/resource gate.
Development is 64 jobs/up to261 attempts; holdout192/up to773. Each run starts with
five fresh unchanged schema qualifications. Persistent split grants reserve before
every wire; failed/uncertain work counts. Registered missing state fails closed;
started grants cannot replay. Source/profile/usage/schema/resource failures stop
spending. Semantic reviews and a recalculated accepted development lock precede
holdout; full accepted holdout is required to create an app acceptance lock.

The new PC app source uses real LangGraph, the accepted HF pair, read-only DB,
loopback8002/one worker, separate quotas, owned cleanup and per-request six-call
bounds. Acceptance is revalidated before each model call. Telegram's qualified
launcher uses the paired owner and checks API acceptance before polling. Defaults
and `.env` remain disabled; no candidate API, bot or live owner message has run.

**All28 approved inference attempts remain used; zero active calls.** No new paper
transfer/inference or Telegram traffic. The exact pending development proposal is
`tests/test_output/hf-cerebras-development-proposal-20261016-01/proposed-approval.json`,
SHA256 `b73ec5c5a9d5176b64262d03cac1d7b4821d956a385281c503c7950ef499f357`.
It proposes up to261 additional calls, including fresh5 qualifications plus full64
comparison, sending only bounded questions/public paper contexts. Failures and
uncertainty count; no retry/fallback, holdout spending or activation. No approved
receipt, development/holdout ledger or registration exists. Actual unapproved
execution stops before credentials/services/funding; unaccepted holdout stops
before spending; both launchers reject missing app acceptance evidence.

Docker Desktop had stopped between sessions. It was reopened and only the three
verified existing cache/Ollama/API containers restored; IDs/images are unchanged.
Final free RAM was1,905.8MiB, above1,536MiB hybrid admission. Recheck at execution;
do not lower limits or repeatedly ask the user to close apps. No user RAM action
is currently needed. Goal ACTIVE. Next obtain explicit approval of the prepared261
scope, then execute only when admission passes, review/score development, and
prepare the separate holdout authorization. Full app/owner acceptance remains.
See [execution scope and commands](hf-cerebras-paper-evaluation.md).

# All five Cerebras schema cases verified — 2026-10-15

The approved selector-1 and selector-10 checks both passed on source checkpoint
`1f7af96`. The first output stopped at 674.26 MiB before any attempt. RAM later
recovered naturally; the same fixed registered allowance resumed in a fresh output
with 1,436.60 MiB free and minimum live headroom 1,161.17 MiB. Both arms settled
exactly one attempt. **All 28 approved attempts are used; zero remain.**

Successful result: `tests/test_output/hf-cerebras-selectors-live-20261015-02/`.
The strict combined controller/selector verifier confirms all five canonical cases,
schema/fixture identities, expected decisions, complete usage, source alignment,
read-only approval/accounting and preservation. Report and summary:
`tests/test_output/hf-cerebras-five-case-summary-20261015-01/`; report SHA-256
`3c4e2045f46c4d21ac30f50ffdec4d3da7880068498319dc9f459bd3a0caef0d`.
New known usage estimate USD 0.00066735; all five cases USD 0.00112975. These are
usage estimates, not invoices; earlier unknown-cost failures remain unknown.

Model schema compatibility is established for these five cases; task and app
acceptance remain false. All four live preservation flags pass. No paper data,
Telegram messages, original API change or bot/runtime activation occurred.
The user cannot free RAM now; no repeated app-closing request is needed.

Next integrate the separate data-only Cerebras paper-evaluation profile with the
guarded collector/scorer, preserving the original 64/192 matrices and every quality,
resource, privacy and accounting gate. Its new profile changes only version,
explicit pair and dated token rates. Existing profile bytes and all old grants
remain immutable; no paper execution is funded. Full source verification remains
**1,219 tests, zero skips**, Ruff and mypy 118. See
`docs/hf-cerebras-paper-evaluation.md`. Goal ACTIVE; private PC/Telegram acceptance
still follows paper evaluation.

# Previous approved selector preparation — 2026-10-15

The user answered **“Approve two additional calls”** for the exact scope in
`docs/hf-cerebras-selectors.md`. The separate approved receipt and confirmation
are saved under `tests/test_output/hf-cerebras-selectors-execution-20261015-01/`;
their contents match the frozen proposal and completed controller history.
At this preparation checkpoint, 26 attempts were used and two newly approved
attempts were unused. The newer result above supersedes that balance.

The offline five-case evidence verifier passes **1,219 full tests, zero skips**,
including 26 new fixture checks; Ruff and mypy (118 source files) pass. Full run
706.05 seconds, with two existing Typer/Click deprecation warnings. Approval review
is available again. Tests use a fresh workspace fixture directory because the
default Windows temporary directory is inaccessible.

The verifier revalidates original case/schema hashes, semantic flags, recomputed
usage/costs, memory margins, all four preservation flags and approved read-only
accounting across the separate controller and selector runs. Runtime and canonical
measurement sources must match; four named diagnostic orchestration files may
differ. The real three-case controller evidence validates, missing selectors fail
closed, and app/task acceptance always remains false. All 340 protected files
match. Next execute the approved pair using its fixed new counter, then validate
the combined evidence. Paper evaluation and private PC/Telegram acceptance remain.

# Previous selector preparation — 2026-10-15

**1,193 full tests pass, zero skips**, nine new; mypy 117, Ruff. All 340 protected
files match, including the successful Cerebras run and all prior counters/receipts/
allocations/configuration/recovery. Actual pending execution blocks before Settings,
funding or service access. No selector grant, approved receipt, call or activation.

[Two-call selector scope](hf-cerebras-selectors.md) is prepared for the unchanged
selector-1 and selector-10 cases on the selected Cerebras route. It binds the
completed controller receipt, allocation, three-arm ledger and successful result
through closed read-only SQLite readers, including all exhausted old grants.
A separate fixed counter requires explicit new funding; pending execution rejects
before Settings, network or initialization. Both generation APIs enforce the exact
provider experiment receipt. No source policy, prompt, label, schema or limit changes.

All 26 approved attempts remain used; no new call, receipt or funded selector ledger.
The successful controller run remains historical and unchanged. Two selectors still
form a diagnostic; validate both evidence sets before any full-five schema summary.
Task/development/holdout and private owner acceptance remain required; global app off.

# Previous successful Cerebras controller checks — 2026-10-15

User-selected `openai/gpt-oss-120b:cerebras` passed the unchanged scope, relevance
and rewrite fixtures. The reallocated three-slot counter settled exactly one
attempt per case. All expected/schema/usage checks and four preservation flags
pass; no raw generation or reasoning retained. Old Groq remainder cannot reserve
again, and all its original bytes remain intact. **26 actual attempts used, zero
active slots remaining; original approved ceiling retained.**

Source checkpoint **ee6dd58**, 1,184 tests/zero skips, mypy 116 and Ruff.
Admission RAM 1,907.91 MiB; minimum live 1,545.66 MiB. Added known usage estimate
$0.00046240; cumulative $0.00137020 plus 11 unknown-cost failures, not an invoice.
[Audited result](hf-cerebras-remaining.md). Receipts/confirmation/allocation under
`hf-cerebras-execution-20261015-01`; result under `hf-cerebras-live-20261015-01`.
No paper data, Telegram traffic, runtime flag change or app startup.

The three-case diagnostic cannot meet full five-case qualification. Next prepare
the original two Cerebras selector cases and obtain additional-call approval,
then retained development/holdout and private PC/owner acceptance. Goal ACTIVE;
model/app acceptance still pending. No Fireworks inference or approval request.

# Previous Cerebras source preparation — 2026-10-15

Preparation passes **1,184 full tests, zero skips**, 17 new, mypy 116 and Ruff.
All 329 protected files match and actual-private-value staged scans pass. The
initial full-run failure was the prior expected rejection of Cerebras; its test
now rejects unreviewed 20B while explicitly covering selected 120B and safe labels.
No assertion removed or threshold changed. Allocation and funding remain absent
until the verified source checkpoint and user-instruction record are saved.

[Cerebras diagnostic source](hf-cerebras-remaining.md) now freezes the original first
three cases, uses a separate three-arm counter and blocks reservations from the
fixed stopped Groq ledger once the allocation record exists. No old row, marker,
receipt or frozen profile is rewritten. Authorization records the provider
instruction plus remaining approved budget. Full five-case qualification remains
false for this three-case diagnostic, including when all three cases pass.

The exact selected model and safe provider label are registered; global model
defaults and HF/agent/Telegram flags remain unchanged. Its diagnostic measurement
copy adds only the catalog-bound Cerebras rates. Offline proposal and actual
pending execution rejection pass without credentials, funding or service access.

Latest user instruction: use `openai/gpt-oss-120b:cerebras`. Its public HF catalog
entry advertises it live/structured. No Cerebras inference yet. Preserve the
existing ceiling of 26 actual attempts: 23 used, three unspent. Prepare a separate
three-call diagnostic and explicit remaining-budget allocation from that steering;
block the old Groq remainder from duplicate spending. No budget increase, model
qualification or application activation is inferred from the model selection.

The now superseded Fireworks candidate passed **1,167 tests, zero skips**, 21 new
tests, mypy 115 and Ruff. Its frozen artifacts and pending proposal remain preserved;
no Fireworks call, funded ledger or approval request. Reuse its tested guard and
budget machinery for the selected Cerebras route while retaining old model/input
contracts, deadlines, quotas and memory gates. A partial three-case diagnostic
cannot satisfy the existing full five-case qualification or app acceptance.

# Historical Fireworks candidate preparation — 2026-10-15

The Groq failure remains preserved and unqualified: 23 actual attempts used,
three unspent under its stop rule. A separate
[five-case Fireworks scope](hf-fireworks-schema-candidate.md) is prepared for the
already registered alternative through the same HF token/router. Exact payloads
change only the model/provider string; original prompts, labels, schemas, limits,
memory and acceptance gates remain unchanged. No automatic provider fallback.

Its new fixed receipt/counter binds all three exhausted grants and the stopped
Groq receipt/counter/result. Both generation methods also bind their approval to
the exact provider experiment. Old funding cannot authorize the candidate. The
pending proposal cannot execute, read Settings, create a ledger or access services.
No Fireworks inference or candidate approval/funding yet; global runtime stays off.

Goal remains active. Next explicit new candidate-call approval and audited schema
qualification, then the retained development/holdout and private owner acceptance.

# Previous Groq check stopped at provider failure — 2026-10-15

User explicitly approved five synthetic HF/Groq calls. Scope passed; relevance
returned HTTP 400 / `json_validate_failed` / `invalid_request_error`. The frozen
stop rule held: **2 new calls used, 3 unspent; 23 cumulative attempts used out of
26 approved**. Remaining calls cannot fund retries, changed prompts/providers or
continuation past the failed check. Preserve the fixed new ledger/registration,
receipt/confirmation and both result files under `hf-schema-live-20261015-01`.

Admission at 1,302.12 MiB and minimum live RAM 1,253.19 MiB passed. This is a provider
validation failure, not a memory stop. Source/frozen input/corpus/model checks all
passed; generation data was discarded. Known cumulative usage estimate $0.00090780
plus 11 unknown-cost failures, not an invoice. Model and app remain unqualified.
No runtime flags changed, app/preview/bot started or Telegram requests sent.

[Exact scope and audit](hf-schema-execution.md) and a
[public synthetic reproduction](research/hf-groq-synthetic-reproduction-20261015/README.md)
are saved. The passing control and failing relevance body differ only in embedded
question wording; a root cause is not established. Public catalog metadata advertises
the existing Fireworks candidate as live/structured. Next prepare a distinct guarded
candidate scope before requesting its explicit approval. Existing qualification,
development/holdout and owner acceptance remain required; goal ACTIVE.

# Previous five-case HF check preparation — 2026-10-15

All **21 approved attempts are used; zero remain**. The next guarded runner checks
the five unchanged qualification-v2 synthetic cases with their exact prompts,
schemas and outgoing payloads. [Reviewable scope](hf-schema-execution.md) requests
up to five additional calls; there is no approval or funded new ledger yet.

Its fixed counter binds the original 13, prompt 6 and clarity 2 allowances plus
the successful clarity result. Both generation methods reserve before outbound
work, reject changed payloads and enforce five named arms without repeats. Failed
or uncertain attempts count; the first failed check stops the run. Missing
registered evidence requires recovery. Old frozen files and receipts stay intact.

Actual offline plan/proposal paths made no inference or credential reads. Execution
with the pending proposal was rejected before Settings, funding or service access.
Successful execution would establish schema compatibility only; it sends no paper
data and does not activate HF, agent, API preview or Telegram. The active app goal
still requires reviewed development, locked holdout and private owner acceptance.

**1,146 tests pass, zero skips**, 38 new and 80 focused; mypy 114, Ruff. All 316
protected private/frozen/receipt/counter/snapshot/recovery files match. All 15
retained container IDs/images/states and the full live corpus/model snapshot match:
58 papers and 2,775 chunks. No extra containers, new paid calls, Telegram traffic,
funded ledger or runtime activation. Preparation evidence is under
`tests/test_output/hf-schema-qualification-prep-20261015-01/`.

# Previous PC preview checkpoint; clarity pair passed — 2026-10-15

User explicitly approved two new public synthetic HF/Groq calls. The first run
stopped below1024MiB before provider/corpus/inference requests; user could not free
RAM. It recovered naturally; the same receipt/counter resumed in a fresh output.
Both clearer-question polarity cases passed with expected/schema checks,complete
usage and unchanged source/corpus/models/frozen labels. Only bounded counts/flags
were retained. [Audited scope/result](hf-clarity-execution.md).

**All21 approved attempts used,zero remaining:** original13+prompt6+clarity2.
No paper transfer,retry,prompt replacement or model/app qualification. Root cause
of prior400s remains unresolved. App/HF/agent/Telegram remain off; owner is verified.
Receipt under `tests/test_output/hf-clarity-execution-20261015-01/`; successful run
`tests/test_output/hf-clarity-live-20261015-02/`. Preserve first stopped run and all
three fixed counters/registrations. Known added usage estimate$0.00018495; cumulative
$0.00083205 plus10prior unknown-cost failures,not an invoice.

[PC API preview](pc-api-preview.md) is prepared forloopback8002,one worker and
separate persistent quotas. Reuses authenticated paper browse/detail/search while
blocking all generation routes. Owns read-only PostgreSQL connections and skips
production migrations; validated settings/loopback endpoints and cleanup preserve
original8000/runtime/data. Default check creates no server/network/state. Preview
and bot were not started. Qualified generation rollout remains pending.

**1,108 tests pass,zero skips**,18new preview tests,mypy111,Ruff. Goal active,
app acceptance incomplete. Next concrete guarded five-case exact-schema qualification
and explicit additional-call approval,then reviewed development/locked holdout and
qualified local/private owner acceptance. Existing roadmap remains required.

# Previous guarded two-call HF study preparation — 2026-10-15

User requested an active goal to finish the private PC HF/LangGraph/Telegram app.
Owner pairing is already complete. [New two-call study](hf-clarity-execution.md)
references unchanged clearer-question fixtures under a separate execution contract,
with fixed payloads/schema/limits/model, content-free diagnostics and a new
approval-bound counter referencing both completed old ledgers. Its manifest is
`aef8ff44f41dc662dcbe032755d0af014c4c590f98f9b54be79514d206190672`.

Offline/default/proposal paths make no inference or credential reads. Actual
pending-receipt execution was rejected before settings/network/funding. Original
13/13 and6/6 remain exhausted; no new receipt/grant/call. Proposed scope is **two
additional public synthetic HF/Groq attempts**,one positive/one negative. Failed or
uncertain arms cannot repeat. It sends no paper data and never qualifies/activates
the app. Existing qualification/development/holdout gates remain mandatory.

**1,090 tests pass,zero skips**,43new,56focused,mypy109,Ruff. A Windows recovery
failure exposed unclosed SQLite read handles; `contextlib.closing` fixes only
cleanup, independently saved as770943a. All303 audited private/config/pairing/
evaluation/ledger/receipt/snapshot/recovery files match; secret scans pass. No
dependency/model/data/runtime changes. Goal remains active and app acceptance
incomplete. Next explicit exact additional-call approval; independently prepare
isolated API8002 preserving8000,then conditional qualification and live acceptance.

# Previous private Telegram token and owner verified — 2026-10-15

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
recovery files matched the pre-setup snapshot; source scan found no private secrets.
The user then sent the code and asked whether silence was expected. The second
verification matched a fresh private proof and saved the owner ID. All other
private `.env` bytes and34 other protected files match; the challenge is consumed.
**Owner pairing is complete**, and the numeric ID/token remain private. Eight
read-only Telegram requests total (two preparation, two three-call verifications);
zero Telegram messages and zero HF calls. Evidence includes
`tests/test_output/telegram-owner-prep-20261015-01/owner-verification.json`.

Original13/13 +extension6/6 HF calls remain exhausted, zero remaining. No new
budget, model qualification, runtime activation, push or deployment. Original
running API/rollback remain untouched. Telegram/HF/agent are disabled. Next prepare
the concrete separately bounded HF study/runner and candidate API8002 before live
qualification and owner acceptance. User need not repeat BotFather or pairing.
Existing roadmap retained. Pairing source checkpoint290fef7 is fully verified.

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
