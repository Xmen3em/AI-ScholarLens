# Week 6 local verification

## Whole-app implementation — task index

Active expansion of the same initiative, 21 October 2026. All implementation
items below are pending; research/specification is not a passing implementation.
See [whole-app contract](../docs/specs/researcher-app.md) and
[plan](plan.md#whole-app-implementation--21-october-2026).
The existing V1–V9 checklist below remains the canonical visual task list.

Task records define acceptance, dependencies, verification and likely files.
Paths explicitly described as new are proposed. Keep each slice at five files
or fewer; split a task if its implementation grows. S/M mean one small/focused
session, not a deadline. Do not check off live work from offline evidence.

For each pytest verification listed below, use the complete runner pattern,
substituting that task's test files and a fresh task-specific basetemp:

```powershell
New-Item -ItemType Directory -Force -Path tests/test_output | Out-Null
.venv-win/Scripts/python.exe -m pytest tests/unit/test_study_service.py -q -o cache_dir=tests/test_output/study-pytest --basetemp tests/test_output/task-check-fresh
.venv-win/Scripts/python.exe -m ruff check src tests research
.venv-win/Scripts/python.exe -m mypy src
```

Future test paths are run only after they are created. Each task runs applicable
focused tests plus lint/type checks; checkpoints add justified regression/runtime
checks. SDK verification uses the separate full command in task F2. Never run
live calls just because a task lists qualification as a prerequisite.

### F1 — Reviewed science and acceptance fixtures

- [ ] Freeze the documented mechanism/comparison failures and evaluation rubric.

**Accept:** Reviewed positive/negative claims, source identity and expected
outcomes are inspectable; reserve a distinct 12-paper/48-question holdout without
calling a model. V1 reuses the RAG facts instead of inventing another truth set.
**Verify:** New `test_study_science_fixtures.py`; inspect every source/label and
confirm no development/holdout overlap.
**Depends:** None. **Files:** new `evaluation/paper_learning/README.md`, fixture
JSON and `tests/unit/test_study_science_fixtures.py`. **Scope:** M, 3 files.

### F2 — Offline Deep failure diagnosis coverage

- [ ] Exercise each worker/transport/validation failure boundary with safe traces.

**Accept:** A failing SDK path retains a bounded stage/category and job identity;
unknown historic causes stay unknown. No provider output/secret leaks.
**Verify:** Existing `test_study_feedback.py`, plus
`.venv-study-research/Scripts/python.exe -m unittest discover -s research/tests -v`;
inject malformed JSON, IDs, timeout and context limits in the actual SDK loop.
**Depends:** None. **Files:** `research/tests/test_deep.py`, `failures.py`,
`src/commands/study_research.py`, `test_study_feedback.py`. **Scope:** M, 4 files.

### F3 — Shared phase-budget reservation

- [ ] Reserve answer/review capacity in the admitted-job budget contract.

**Accept:** Four-attempt total stays immutable; exploration cannot reserve the
last synthesis/review slots, and failed/unknown attempts remain spent.
**Verify:** Existing `test_study_store.py` plus new `test_study_budget.py`;
exercise concurrent reservation, exhaustion, crash and restart.
**Depends:** F1. **Files:** new `budget.py`, `store.py`, the two named tests.
**Scope:** M, 4 files.

### F4 — Apply reserved phases to the research workflow

- [ ] Integrate the finite research→synthesis→review schedule.

**Accept:** A research job returns a validated/reviewed artifact or finite useful
terminal state; no unchecked repair, hidden child budget or automatic retry.
**Verify:** Actual SDK/stub-transport loop plus `test_study_service.py`; inspect
attempt purposes/counts when research exhausts its allocation.
**Depends:** F2, F3. **Files:** `deep.py`, `src/commands/study_research.py`,
`service.py`, `research/tests/test_deep.py`, `test_study_service.py`.
**Scope:** M, 5 files.

### F5 — Scoped live Deep diagnosis/verification

- [ ] Execute only an explicitly authorized diagnostic scope and report the result.

**Accept:** Frozen source/intents/ceilings are honored; actual question reaches
answer/review/delivery before claiming repair. All failures stay recorded.
**Verify:** Follow `docs/deep-repair-execution-20261021.md`, which is currently
pending/unapproved. If F3/F4 changed source, preserve its required baseline or
prepare a revised scope first; do not spend the old pending request on new source.
**Depends:** F2 and applicable explicit approval; independent of V1–V4.
**Files:** execution/result documentation, ignored proof only. **Scope:** S.

### P1 — Measure local memory and latency

- [ ] Capture cold/warm startup, native extraction and render resource envelopes.

**Accept:** A reproducible report identifies import/worker peaks and hardware;
startup/live floors and original ledgers/configuration remain unchanged.
**Verify:** Offline import/parser/render probe, no inference or unsolicited
Telegram traffic; repeat only if new measurements justify a change.
**Depends:** None; render portion follows V3. **Files:** new bounded profiling
command, its unit test and resource report. **Scope:** M, 3 files.

### P2 — Implement a measured resource/error improvement

- [ ] Address the largest measured peak and preserve readable failure behavior.

**Accept:** Demonstrated lower peak or bounded worker lifetime, same gates,
no background browser/model load; source/text remain usable after failure.
**Verify:** Repeat P1's exact probe plus `test_development_imports.py` and the
focused parser/render failure tests; record before/after rather than a guess.
**Depends:** P1. **Files:** measured import/worker boundary, two focused tests
and resource report; select exact boundary from profiling. **Scope:** M, ≤4 files.

### Checkpoint C0 — Baseline and offline visual lane

- [ ] After each two/three tasks, focused checks pass and a bounded slice is committed.
- [ ] F1–F4/P1–P2 retain quotas, errors and resources; Deep live status is accurate.
- [ ] Existing V1–V4 produce reviewed RAG SVG/PNG/viewer with source inspection,
  all applicable RTL cases and zero navigation/model traffic.

### I1 — Canonical paper identity adapter

- [ ] Carry the exact selected identity through new artifact contracts.

**Accept:** Existing StudyPaper/URL/title selection remains compatible; new
PaperRef is server-owned, and expired/wrong-owner/version-mismatched selections
cannot fetch a source or attach an old artifact.
**Verify:** Existing `test_study_intake.py` and service selection/version tests
with stub metadata and zero inference.
**Depends:** None. **Files:** new identity adapter, intake/service integration
and two focused tests. **Scope:** M, ≤5 files.

### C1 — Native source manifest and region identity

- [ ] Add versioned source/region contracts around existing native extraction.

**Accept:** Page/hash/revision/coverage and unknown geometry are explicit; old
PaperContent/EvidenceBlock consumers still work. No ignored full PDF dependency.
**Verify:** New `test_source_manifest.py` and existing `test_study_content.py`;
wrong hashes, missing pages, reading order and parser timeout cases.
**Depends:** I1, F1. **Files:** new `source_manifest.py`, `content.py`, new manifest
test and tiny fixture. **Scope:** M, 4 files.

### E1 — Claim identity and numeric validation

- [ ] Validate claims against complete source/setting identities.

**Accept:** False best-result, incompatible metric/split and wrong-source claims
fail; supported statements retain inspectable original evidence.
**Verify:** New `test_study_claims.py` plus `test_study_feedback.py` and F1 negatives.
**Depends:** F1, C1. **Files:** new `claims.py`, `tutor.py`, new claim test and
`test_study_feedback.py`. **Scope:** M, 4 files.

### E2 — Bilingual evidence selection baseline

- [ ] Compare bounded selection strategies on the same Arabic/English questions.

**Accept:** Supporting-region recall, omissions and unavailable structure are
reported; no model rewrite, vector service or silent provider fallback is enabled.
**Verify:** New `test_study_retrieval.py` plus a reproducible local fixture scorer.
**Depends:** F1, C1. **Files:** new retrieval module, scorer, fixture and test.
**Scope:** M, 4 files.

### S1 — Persistent library and study position

- [ ] Save/open owner-scoped goals, bookmarks and accepted artifact positions.

**Accept:** A→B→A and restart restore the right version/step with no generation;
wrong owner and stale artifact IDs fail safely.
**Verify:** New `test_study_progress.py` and existing `test_study_store.py` with
real temporary SQLite, migration/rollback and interrupted writes.
**Depends:** C1. **Files:** new `session_state.py`, `store.py`, new progress test,
existing store test. **Scope:** M, 4 files.

### S2 — Bounded context and complete deletion

- [ ] Integrate saved progress with recent context, retention and forget.

**Accept:** Late jobs cannot overwrite switched papers; expired/context summaries
never become evidence. Forget removes new personal state without resetting calls.
**Verify:** `test_study_store.py`, `test_study_service.py`, new progress tests;
test expiry, restore, stale responses and two-owner deletion isolation.
**Depends:** S1. **Files:** session state, store, service and two focused tests.
**Scope:** M, 5 files.

### T1 — Guided learning action

- [ ] Deliver a short orientation and a focused goal/section step.

**Accept:** Explicit goal/depth, paper/background/example origins and finite next
actions remain compatible with current Lesson delivery; no full lesson on every action.
**Verify:** New `test_study_teaching.py` plus tutor/service tests with stub transport.
**Depends:** E1, E2, S1. **Files:** new `teaching.py`, tutor, service, new teaching
test and `test_study_tutor.py`. **Scope:** M, 5 files.

### T2 — Learner attempt and grounded feedback

- [ ] Add one task-bound comprehension attempt/feedback loop.

**Accept:** Correct paraphrases are accepted; a reviewed misconception receives
specific source-based correction, with skip/back and saved state.
**Verify:** New `test_study_comprehension.py` plus teaching tests and reviewed
correct/incorrect learner fixtures; budget exhaustion leaves a useful result.
**Depends:** T1, S2, F3. **Files:** new comprehension module, teaching integration,
two focused tests and fixture. **Scope:** M, 5 files.

### D1 — Authenticated deterministic study actions

- [ ] Add owner/version-bound actions and artifact/library read contracts.

**Accept:** Request quotas apply to navigation; generation admission remains
unchanged. Duplicate intent/hash, stale version and inaccessible artifacts behave
as specified, with zero model calls.
**Verify:** New `test_study_actions_api.py` and existing API quota tests.
**Depends:** S1, T1. **Files:** new actions API/models, thin route registration,
new action tests and existing quota test. **Scope:** M, 5 files.

### D2 — Telegram learning controls and terminal states

- [ ] Route lesson/library/progress text actions through the deterministic contract.

**Accept:** Existing private/update/forward/ack gates remain; help/status/actions
are local and worker/image failures leave source/text accessible. Existing
labeled general-concept and legacy paper modes keep their routing contracts.
**Verify:** Existing study Telegram/bot tests, including duplicate update,
UTF-16 boundaries and uncertain delivery. Visual delivery stays canonical V7.
**Depends:** D1, T2. **Files:** Telegram bot, study service, study Telegram test,
bot test and delivery state test. **Scope:** M, 5 files.

### N1 — Editable source-linked local notes

- [ ] Save/version user notes alongside accepted generated notes and quotations.

**Accept:** Origins remain distinct, stale edits conflict, `/notes` compatibility
and forget work; editing does not regenerate a lesson.
**Verify:** New `test_study_notes.py` plus store/service regression.
**Depends:** S2, T1. **Files:** new notes module/store extension, service adapter,
new note test and store test. **Scope:** M, 5 files.

### M1 — Provider capability adapter readiness

- [ ] Define isolated route capabilities and deterministic transport qualification.

**Accept:** Schema/images/tools/history/tokenizer/usage/error contracts differ
explicitly by route; current Cerebras wire settings remain frozen and compatible.
**Verify:** New provider adapter tests with captured synthetic response fixtures;
no live request or provider fallback is sent.
**Depends:** F3, V2. **Files:** capability model, isolated adapter, tests and
synthetic fixture. **Scope:** M, 4 files. Hosted comparison remains canonical V8.

### Q1 — Scientific and teaching evaluation harness

- [ ] Score the frozen capability-specific holdout and preserve failed outcomes.

**Accept:** Development/holdout identities, supported denominators, critical
errors and reviewer disagreement are recorded; no score is inferred from unit tests.
**Verify:** New scorer tests with a tiny synthetic scored run, plus rubric review;
actual model generation requires a separately approved scope.
**Depends:** F1, E1, T2. **Files:** evaluation scorer, schema, test and rubric.
**Scope:** M, 4 files.

### Release R1 — Private daily native-text study

- [ ] F/E/S/T/D/N baseline tasks and V5–V9 integration pass their applicable checks.
- [ ] User can bring a new supported paper, learn/attempt/inspect a method, save,
  switch/resume and forget; model-generated visuals are qualified beyond RAG.
- [ ] Scientific/Arabic/RTL/owner/restart/resource evidence is recorded; Deep is
  labeled experimental unless F5 actually qualifies it. No old grant is reused.

### C2 — Structured tables and verified cells

- [ ] Extract/curate table regions, headers, cells and experimental settings.

**Accept:** Table/row/column/dataset/split/unit/printed-value identities remain
attached to source regions; merged/ambiguous cells stay unverified.
**Verify:** New `test_study_tables.py`, real tiny multicolumn/table PDFs and
manual comparison to rendered pages.
**Depends:** C1, E1. **Files:** table models/extractor, table test, fixture and
source-manifest integration. **Scope:** M, 5 files.

### C3 — Equation and figure region inspection

- [ ] Expose original crops, captions and bounded symbolic interpretations.

**Accept:** Crop coordinates/hash/page are inspectable; extracted minus/sign/
superscript and caption associations are verified or explicitly unavailable.
**Verify:** New region tests plus actual crop/render inspection on reviewed fixtures.
**Depends:** C1. **Files:** region models, fixed region worker, region tests,
fixture and manifest adapter. **Scope:** M, 5 files.

### E3 — Compatible table comparisons

- [ ] Link numeric claims to verified cell sets and comparison semantics.

**Accept:** Wrong best result, reversed metric, unit and split mismatches fail;
verified values remain copied, not regenerated by a model.
**Verify:** New numeric-claim tests plus E1/F1 science regression.
**Depends:** C2, E1. **Files:** numeric claim module, claim integration,
numeric test and fixture. **Scope:** M, 4 files.

### O1 — Selective OCR qualification fixtures

- [ ] Prepare page-image scientific extraction cases and strict route responses.

**Accept:** Pages/regions sent, expected signs/columns and quality flags are
bounded; existing disabled OCR adapter remains disabled.
**Verify:** Existing OCR tests plus new scientific OCR fixture tests using stub HTTP.
**Depends:** C1, C2, C3. **Files:** OCR contract/adapter, two tests and fixture.
**Scope:** M, 5 files.

### O2 — Hosted OCR capability and scientific qualification

- [ ] Compare actual candidate routes under a separate explicit scoped ceiling.

**Accept:** Exact image/task/schema/terms and scientific outputs qualify against
O1; failed/unknown requests count. No route is enabled from catalog status alone.
**Verify:** Frozen execution plan, immutable attempts and source/region comparisons;
stop according to that scope. Public-page/image transmission is disclosed there.
**Depends:** O1 and applicable approval. **Files:** execution plan, result and
qualification metadata; ignored run proof. **Scope:** M, ≤4 files.

### O3 — Integrate qualified selective OCR

- [ ] Admit OCR only for the source pages/regions that require it.

**Accept:** Parent budget/resource/disk limits hold, native text stays usable,
and extraction model/revision/coverage are recorded without silent source replacement.
**Verify:** OCR/content/service tests for page selection, failure/unknown state,
partial fallback and measured worker peak.
**Depends:** O2, F3, P1. **Files:** OCR, content, service and two focused tests.
**Scope:** M, 5 files.

### T3 — Read a verified table with the learner

- [ ] Teach one result/setting using selected verified cells and a short question.

**Accept:** Explanation and feedback preserve metric/split/unit/comparison set;
unavailable structure is acknowledged rather than reconstructed.
**Verify:** New table-teaching tests with correct/misleading learner answers.
**Depends:** E3, T2. **Files:** table teaching module, tutor adapter, test and
fixture. **Scope:** M, 4 files.

### T4 — Explain an equation or original figure

- [ ] Walk through reviewed symbols/components with an explicitly educational example.

**Accept:** Original crop/source stays visible, symbol direction/meaning matches
the verified interpretation and unsupported parts remain marked.
**Verify:** New equation/figure teaching tests and manual scientific/RTL inspection.
**Depends:** C3, T2. **Files:** interpretation teaching module, tutor adapter,
two focused tests and fixture. **Scope:** M, 5 files.

### V10 — Verified numeric chart template

- [ ] Render a restricted interactive chart from verified table-cell IDs.

**Accept:** Values/units/splits copy exactly; no model expressions/URLs, invented
measurements or silent axis reversal. Source data and text remain inspectable.
**Verify:** New chart contract/renderer tests and actual browser/PNG output.
**Depends:** E3, V3, V4. **Files:** chart contract, fixed renderer/template,
tests and trusted viewer integration. **Scope:** M, ≤5 files.

### V11 — Equation and figure visual walkthrough

- [ ] Add source-linked symbolic/component highlighting to the trusted viewer.

**Accept:** Source figures are preserved, derived labels distinguished and LTR
equations readable; navigation stays deterministic and prior artifacts survive edits.
**Verify:** New visual-region tests plus actual export/browser/copy inspection.
**Depends:** C3, T4, V5. **Files:** walkthrough template, renderer adapter,
viewer action adapter, tests and fixture. **Scope:** M, 5 files.

### Release R2 — Structured/scanned scientific learning

- [ ] C2/C3/E3/T3/T4/V10/V11 pass structured science and actual output checks.
- [ ] O1–O3 pass before OCR-supported scanned pages are advertised; unsupported
  cases remain explicit. Record critical signs/cells/coverage and resources.
- [ ] Re-evaluate added capabilities on the frozen holdout; native R1 regression
  and readable failure alternatives remain intact.

### S3 — Explicit multi-paper study selection

- [ ] Create a separate comparison session with two chosen source identities.

**Accept:** Both sources/versions are shown and scoped independently; ordinary
one-paper context and notes are not overwritten by a comparison.
**Verify:** New comparison-session tests for switches, wrong versions and two owners.
**Depends:** S2, E1. **Files:** comparison session model/store, selection adapter,
tests and API model. **Scope:** M, 5 files.

### T5 — Evidence-based two-paper comparison

- [ ] Compare assumptions/methods/results with independent supporting evidence.

**Accept:** Different datasets/settings are shown as incomparable where required;
no unsupported global winner and no quote is attributed to the other paper.
**Verify:** New comparison tutor tests and fresh paired scientific review cases.
**Depends:** S3, E3, T2. **Files:** comparison tutor, strict output model,
tests and paired fixture. **Scope:** M, 4 files.

### R1 — External primary-source fetch policy

- [ ] Specify and enforce the bounded read-only external acquisition boundary.

**Accept:** Allowed origins/redirects/bytes/deadlines and source identity are
explicit; private addresses, credentialed URLs and executable instructions fail.
**Verify:** New external-fetch policy tests for SSRF, redirect/DNS policy and quotas.
**Depends:** F3, C1. **Files:** source policy, fixed fetch adapter, tests and
policy documentation. **Scope:** M, 4 files. No search subscription provisioned.

### R2 — Optional search/MCP research report

- [ ] Expose the approved primary-source tools to bounded research.

**Accept:** Outside-paper findings have their own provenance and label; parent
budgets, owner and explicit allowed tool set cannot be changed by model text.
**Verify:** Actual installed MCP/SDK with stub search/fetch; test wrong scope,
hostile tool content and disconnected provider states.
**Depends:** R1, F4. **Files:** external tools, MCP adapter, research report model
and two tests. **Scope:** M, 5 files. Live search/inference needs its own scope.

### N2 — Previewed local export

- [ ] Export exactly selected note/lesson/visual versions to a reviewable package.

**Accept:** Markdown/source links and optional accepted visuals preserve origin,
canonical copy and hashes; no credentials, new inference or arbitrary file paths.
**Verify:** New export tests, inspect actual package and Arabic/English copy output.
**Depends:** N1, V5. **Files:** export module, strict preview model, tests and
trusted notes UI adapter. **Scope:** M, 4 files.

### N3 — Optional deliberate Notion export

- [ ] Connect a narrow application adapter to an owner-chosen destination.

**Accept:** Preview/action/digest precede the write; revoked/disconnected access
doesn't block local study; duplicates/unknown outcomes use tracked reconciliation.
**Verify:** Stubbed create/read-back/revocation tests, then one explicitly
authorized export with the configured application connection/destination.
**Depends:** N2 and connection/destination choice. **Files:** Notion adapter,
export intent store, tests and integration guide. **Scope:** M, 4 files.

### D3 — Readable integrated desktop study workspace

- [ ] Compose source, lesson, visual and note views from accepted artifacts.

**Accept:** Loading/partial/empty/error states, RTL/text alternatives and source
inspection work without embedded secrets or generation on view open.
**Verify:** Actual browser DOM/console/network/keyboard/narrow/zoom checks and
new workspace-export tests; inspect the generated desktop artifact.
**Depends:** D1, V4, N1, C3. **Files:** workspace exporter, trusted HTML/JS/CSS
assets and tests. **Scope:** M, 5 files.

### D4 — Workspace study/edit actions

- [ ] Connect deliberate learning, saved-position and note actions to the API.

**Accept:** Model-free controls stay under request quota; generation is explicit,
version conflicts recover without losing accepted work and deletion is complete.
**Verify:** Workspace/API integration plus actual browser action/network tests.
**Depends:** D3, D2, N2, S2. **Files:** workspace action JS, API client,
action route adapter and two tests. **Scope:** M, 5 files.

### Release R3 — Expanded private research workspace

- [ ] Comparison, external research and exports each pass independent source/
  owner/budget/disconnected-state checks; enabled capabilities are clearly shown.
- [ ] Notion remains optional and is tested only after its explicit destination action.
- [ ] Complete desktop flow and new scientific holdout pass; no public/phone
  reachability or new research tools are implied by local viewer availability.

### H1 — Private hosting profile

- [ ] Define measured capacity, cost envelope, credentials and traffic move plan.

**Accept:** Host/storage/worker/polling ownership, HTTPS/auth and rollback are
reviewable before any spend/deployment; no local RAM floor is bypassed by assumption.
**Verify:** Capacity/secret-boundary/rollback review against P1 and real workload.
**Depends:** R1 release evidence, owner host/budget choice. **Files:** host profile,
deployment config draft and operations guide. **Scope:** M, 3 files.

### H2 — Backup and restore verification

- [ ] Create a bounded private-state/artifact backup with safe restore semantics.

**Accept:** Restored study positions/notes/hashes work, spent intents remain
spent, and old polling/provider/delivery uncertainty cannot replay automatically.
**Verify:** Real temporary SQLite/files restore drill plus new restoration tests.
**Depends:** S2, V5, N1. **Files:** backup adapter, restore adapter, tests and
restore runbook. **Scope:** M, 4 files.

### H3 — Supervised hosted private runtime

- [ ] Deploy only the reviewed private configuration and move one poller safely.

**Accept:** Health/stage/error metrics are redacted; startup/restart/rollback and
network loss leave safe states. Local and hosted Telegram pollers never overlap.
**Verify:** Staging health/restore/rollback drill and authorized owner test;
deployment/cost authorization is required before the external move.
**Depends:** H1, H2, P2. **Files:** deployment config, supervisor/health adapter,
tests and runbook. **Scope:** M, ≤5 files.

### H4 — Phone-facing Mini App/session authentication

- [ ] Add validated Telegram initialization and owner-only web session access.

**Accept:** Server verifies signature/owner/freshness/replay; token never reaches
the frontend, untrusted initDataUnsafe is not authority, and sessions can expire.
**Verify:** New auth tests for forged/expired/replayed/wrong-owner data plus
actual HTTPS browser/client verification.
**Depends:** H3, D4. **Files:** Mini App auth, session adapter, web registration
and two tests. **Scope:** M, 5 files.

### H5 — Private mobile acceptance

- [ ] Verify complete study and mixed-text reading on the owner's actual clients.

**Accept:** Source/visual/quiz/notes/resume work; failure/text fallbacks remain
usable across phone/desktop, and hosted availability claims match observed operation.
**Verify:** Recorded client/version, screenshots, reconnect/restart test and
owner walkthrough; no unsolicited test messages.
**Depends:** H4, H2, V7. **Files:** acceptance checklist/result and ignored proof.
**Scope:** S, ≤2 tracked files.

### Q2 — Automated offline release checks

- [ ] Add a reproducible CI job for established offline contracts and SDK separation.

**Accept:** No paid network/live secrets, disabled tests or softened gates;
new runner setup reproduces focused/full checks and preserves fixture provenance.
**Verify:** Local CI-equivalent run, clean installation rehearsal and actual
CI run once the workflow is committed; keep source/date of evidence.
**Depends:** Q1, R1 release evidence. **Files:** new CI workflow, test command
wrapper if needed, reproducibility guide. **Scope:** M, ≤3 files.

### Release R4 — Continuously available private study

- [ ] Hosted runtime, backup/restore, safe polling move, auth and phone tests pass.
- [ ] Model/resource/quality evidence and operational rollback are current.
- [ ] Public users, billing or broader source access remain a separate reviewed
  initiative; no multi-user launch is implied by private hosted readiness.

---

## learning-visuals — next implementation

This extends the same paper-learning initiative and preserves all older tasks
below. Current work completed research/specification; feature tasks are pending.
[Plan](plan.md#next-source-grounded-visual-learning--21-october-2026) ·
[Contract](../docs/specs/learning-visuals.md).

- [x] Inspect current renderer, workflow, quotas and deployment boundaries.
- [x] Research Kimi K3/K2.x, live HF metadata, PaperVizAgent, interactive revision
  and declarative rendering from primary sources; record revisions/hashes.
- [x] Select a bounded source-linked method explainer as the first offline slice.
- [x] Research W3C/Unicode, SVG/Pillow and Telegram direction boundaries; record
  the owner's mixed Arabic/English [reading contract](../docs/specs/arabic-reading.md).

### V1 — Reviewed RAG source fixture (small; no dependency)

- [x] Record canonical version/hash, short source references and reviewed facts
  for inference and training. No dependency on the ignored full PDF in CI.
- [x] Include negative examples: document-encoder update, token/paragraph confusion
  and the unsupported best-result claim. Mark illustrative material explicitly.
- [x] Verify facts against the original source and retain the fixture rubric.

Likely files:`evaluation/visual_learning/rag-method.v1.json`, its readme and one
focused fixture test. Verify a curator can inspect each fact's source/page.
Acceptance: fixed training/inference facts and negative cases are inspectable;
source review is real and independent of the previously generated lesson.
Whole-app trace: F1/[paper-evidence](../docs/specs/paper-evidence.md).
Scope: M, 3 files; no new provider call.

### V2 — Visual contract and validation (medium; depends on V1)

- [x] Add typed evidence/spec models with finite template/interaction contracts.
- [x] Reject unknown references, cross-paper hashes, invalid graph endpoints and
  unsupported scientific update relations; keep example origins distinct.
- [x] Add meaningful positive/negative contract tests, including inert labels.
- [x] Define bounded semantic text runs and shared mixed-text fixtures from the
  reading contract; keep canonical source/IDs separate from decorated text.

Likely files:`src/services/study/visual_learning/models.py`, `validation.py`,
`tests/unit/test_visual_contract.py`. Verify focused pytest, Ruff and mypy.
Acceptance: invalid IDs/hash/edges/text controls fail, valid reviewed facts pass.
Whole-app trace: [visual spec](../docs/specs/learning-visuals.md) and
[reading contract](../docs/specs/arabic-reading.md). Scope: M, ≤4 files.

### V3 — SVG/PNG method renderer (medium; depends on V2)

- [ ] Draw approved scene primitives from one validated spec and source manifest.
- [ ] Produce readable RTL/mixed-term SVG and PNG without model code execution.
- [ ] Visually inspect real exports, clipping, arrow meanings and image bounds.
- [ ] Measure shaped text in pixels; preserve graphemes/diacritics, isolate
  mixed terms and citations, and inspect both SVG and PNG against the RTL cases.

Likely files:visual scene/renderer module, fixed Windows drawing support where
needed, `tests/unit/test_visual_renderer.py`. Keep current reading maps working.
Acceptance: actual shaped SVG/PNG have no clipped labels or misleading arrows;
missing-shaping/render failure keeps text available. Scope: M, ≤5 files.

### V4 — Desktop interactive viewer (medium; depends on V3)

- [ ] Provide training/inference switching, step navigation, component details
  and original evidence in a trusted local HTML/SVG shell.
- [ ] Navigation performs zero model/network requests and exposes no credentials.
- [ ] Verify keyboard, narrow/desktop layouts, Arabic, reduced motion and console
  errors using an actual browser; preserve a text alternative.
- [ ] Verify explicit RTL blocks/LTR runs, auto-direction input, logical focus
  order, 320px reflow/zoom/spacing and canonical copy; no arrow/axis mirroring.
- [ ] Keep text, source and navigation usable if the visual cannot be rendered.

Likely files:viewer exporter, trusted static assets and viewer tests. The output
opens on this PC; do not advertise a phone-accessible Mini App or public link.
Acceptance: training/inference, step/source controls and text alternatives work
in a real browser with no model/network calls. Scope: M, ≤5 files.

### Checkpoint — Offline teaching prototype

- [ ] V1–V4 accepted checks pass; inspect an actual training/inference artifact.
- [ ] Label the RAG fixture scope; no claim of arbitrary-paper model generation.
- [ ] Record changed files, resources and zero inference before integration.

### V5 — Versioned owner artifacts (medium; depends on V2)

Whole-app prerequisites: V2 and S1. Trace: learning-visuals/learning-session.

- [ ] Store owner/paper/hash/version, locked facts, parent revisions and asset
  hashes under a separate bounded artifact store without modifying old ledgers.
- [ ] Preserve accepted versions during focused edits; verify isolation/deletion.
- [ ] Test cache identity, stale source/version rejection and restart recovery.

Likely files:visual artifact store and its tests; no migration of source/eval data.
Acceptance: version/cache/owner/forget behavior passes real temporary storage
tests and preserves accepted prior exports. Scope: M, ≤4 files.

### V6 — Authenticated visual actions (medium; depends on V4,V5)

Whole-app prerequisites: V4, V5 and D1; share its auth/quota/action conventions.

- [ ] Add strict owner-bound artifact/action contracts with existing API auth.
- [ ] Keep deterministic navigation under request quotas, generation admission
  under generation quotas; do not loosen current endpoint classification.
- [ ] Verify missing/wrong owner access, unknown actions and zero navigation calls.

Likely files:dedicated visual API module, thin app registration and API tests.
Acceptance: authorized step/source actions succeed, stale/wrong-owner actions
fail, all with zero model calls and existing quotas intact. Scope: M, ≤5 files.

### V7 — Private Telegram delivery (medium; depends on V6)

Whole-app prerequisites: V6 and D2; this is the canonical visual delivery task.

- [ ] Add `/visual method` and validated text actions, PNG/source display and a
  clear unsupported-paper response while only the fixture prototype is available.
- [ ] Preserve owner/forward/update/acknowledgement/replay gates and error behavior.
- [ ] Qualify plain-text isolation/splitting and final UTF-16 budgets on Desktop
  and the owner's mobile client; use separate lines when needed, no HTML `bdi`.
- [ ] Test the local flow; obtain explicit authorization before any developer-
  initiated live model call or Telegram test message.

Likely files:thin Telegram dispatcher, visual service adapter and delivery tests.
Acceptance: private validated actions deliver image/source/readable fallback;
Desktop/mobile mixed-text evidence is recorded when authorized. Scope: M, ≤5 files.

### V8 — Model/provider qualification (medium; depends on offline checkpoint)

Whole-app prerequisites: offline V1–V4, M1, Q1 and a separate applicable ceiling.

- [ ] Freeze common scientific/Arabic/schema/vision cases and a separate budget.
- [ ] Verify the selected HF route's schema, images, tools/history, tokenizer,
  usage, limits and license terms; provider catalog status alone is insufficient.
- [ ] Compare current text planning against Kimi K3 and a Qwen alternative;
  record failures and choose from measured results, without automatic fallback.

No execution is authorized by this checklist. Existing pending Deep slots are
not a visualization grant. Isolate provider settings from frozen Cerebras paths.
Acceptance: measured route/scientific/Arabic comparison and failures are saved;
no candidate is activated from metadata alone. Likely files: frozen experiment,
qualification fixture/schema and result metadata. Scope: M, ≤4 tracked files.

### V9 — General-paper visual planning (medium; depends on V5,V8)

Whole-app prerequisites: V5, V8, E1 and T1.

- [ ] Add a bounded plan→validate→review→render path over the selected evidence.
- [ ] Reserve final review capacity; stop on rejection instead of publishing an
  unchecked repair. User-requested edits preserve locked facts and prior versions.
- [ ] Evaluate new papers and questions separately from the tuned RAG fixture.

Acceptance: new supported papers produce reviewed source-bound method artifacts
under admitted budgets; rejected edits preserve accepted versions. Verify the
planner/review loop with stub transport then the separately authorized holdout.
Likely files: planner, workflow adapter, contract/review test and fixture.
Scope: M, ≤5 files. Numeric/equation/figure templates are separate V10/V11 tasks.

### Later slices (not part of first prototype)

- [ ] Verified table-cell chart contract and declarative chart templates.
- [ ] Source equation/figure regions and qualified visual interpretation.
- [ ] Phone-facing Mini App with appropriate HTTPS hosting and validated initData.
- [ ] Researcher learning evaluation and independent scientific holdout.

---

> Current direction — 16 October 2026: private manual Telegram testing is working.
> These older task lists are retained as history and may contain stale unchecked
> items. The proposed next work is the [paper-learning capability map](../CAPABILITY_MAP.md).
> Review its boundaries before creating module specifications and new tasks;
> do not restart old experiments or treat unused historical grants as available.

## Active HF/LangGraph/private PC goal — 2026-10-15

- [x] Create the user-requested app-completion goal; retain owner pairing and old state.
- [x] Freeze separate two-call execution referencing unchanged clearer fixtures.
- [x] Add exact-approval two-arm counter binding both exhausted parent allowances.
- [x] Reuse guarded collector and exact-payload reproduction; retain original old runner.
- [x] Reproduce/fix Windows read-only SQLite handle leak without counter changes.
- [x] Verify1090full/zero skips,56focused,mypy109,Ruff and303 protected hashes.
- [x] Prepare pending proposal and verify it cannot execute/fund/read credentials.
- [x] Obtain explicit approval of at most two new public synthetic HF/Groq attempts.
- [x] Execute/audit the bounded study; both cases pass,model/app stay unqualified.
- [x] Prepare read-only API preview8002 without migrations;preserve original8000/data.
- [x] Prepare guarded five-case exact-schema qualification and pending bounded proposal.
- [x] Verify 1,146 full/zero skips,80focused,mypy114,Ruff and316 protected files.
- [x] Obtain explicit approval of up to five new synthetic HF/Groq attempts.
- [x] Execute/audit until the first failure: scope passes, relevance HTTP400;2used/3unspent.
- [x] Save public synthetic reproduction without secrets, generated text or submission.
- [x] Prepare guarded Fireworks candidate with unchanged payloads except provider.
- [x] Preserve unapproved Fireworks candidate when user selected Cerebras instead.
- [x] Prepare Cerebras first-three-case diagnostic within existing three-slot remainder.
- [x] Execute/audit user-selected Cerebras:3cases pass,all26used,zero active slots.
- [x] Prepare guarded two-selector scope bound to successful Cerebras controllers.
- [x] Verify1,193full/zero skips,mypy117,Ruff and340protected files.
- [ ] Obtain explicit approval of two additional synthetic HF/Cerebras calls.
- [ ] Execute/audit selectors; validate all five cases before schema summary.
- [ ] Add qualified generation rollout after actual model/task acceptance.
- [ ] Complete exact qualification,reviewed development/locked holdout and owner acceptance.

[Audited scope](../docs/hf-clarity-execution.md). Goal active; original13+prompt6+
clarity2 =21approved attempts used,zero remain. Both clarity cases pass; no paper
data or model/app qualification.1108full/zero skips,mypy111,Ruff. Preview/bot not
started. Telegram/HF/agent remain off; existing roadmap below retained.

## Private Telegram owner pairing — 2026-10-15

- [x] User created `@AIScholarLensbot` and saved its token privately.
- [x] Verify expected bot/no webhook with read-only Telegram requests.
- [x] Implement one-time private-code owner pairing without adopting first sender.
- [x] Preserve pending updates, original configuration and disabled runtime flags.
- [x] Complete1047full/zero skips,36new/91focused,mypy106,Ruff and secret/state audit.
- [x] User sends the private start code; verify and save only their owner ID.
- [ ] Prepare/approve new bounded HF study; qualify model and paper tasks.
- [ ] Prepare candidate API8002 and finish live private Telegram acceptance.

[Setup](../docs/telegram-langgraph.md). Eight read-only Telegram calls,zero messages,
zero HF calls. Exact owner-only private configuration change;challenge consumed.
Original13/13 +extension6/6 exhausted; no new budget or activation.

## LangGraph/private Telegram completion scope — 2026-10-14

- [x] Record user selection: LangGraph, private owner-only bot, current PC.
- [x] Run actual conditional LangGraph nodes with original guards/prompts/limits.
- [x] Preserve status backpressure, joined cancellation and caller tracing context.
- [x] Add private polling/commands, authenticated API forwarding and validated replies.
- [x] Add durable offset/registration, single-instance lock and no uncertain API replay.
- [x] Shield private credentials/logs/history and cover both settings templates/readers.
- [x] Complete1,011full/zero skips,128focused,mypy105,lint,owner/replay mutation checks.
- [x] Fix optional-codec local audit regression; verify full retained state and closed ledgers.
- [x] Create Telegram bot through BotFather; configure private token and verified owner ID (2026-10-15).
- [ ] Obtain new separately scoped HF budget; complete live qualification and task acceptance.
- [ ] Prepare reviewed isolated candidate API8002; activate/test private owner's bot locally.

[Setup and source evidence](../docs/telegram-langgraph.md). No live Telegram/HF calls;
13/13 +6/6 allowances exhausted,zero remaining. Running original API/rollback unchanged.
Old tasks/records remain; older optional-Telegram/no-LangGraph choices are superseded.

## Offline fixture clarity and successful-response diagnostics — 2026-10-14

- [x] Review positive-label ambiguity without rewriting past labels/results.
- [x] Freeze separate clearer-question positive/negative controls with original contracts.
- [x] Add bounded flags/counts after canonical validation without generated-text retention.
- [x] Prepare offline-only planner with no execute option or live fixture registration.
- [x] Verify malformed/over-cap/duplicate/unknown marker handling and measurement binding.
- [x] Complete949-test/zero-skip,mypy102,114focused,lint and privacy/equality mutation checks.
- [x] Preserve both exhausted ledgers,old evidence/private settings,15containers,corpus/models/recovery.

See [review and evidence](../docs/hf-fixture-review.md). No new paid calls or budget;
original13/13 +extension6/6 exhausted,zero remain,19authorized attempts used.
HF/agent remain disabled and HF unqualified. Further live study needs a separate
explicit budget and guarded runner;prospective fixtures alone cannot execute it.
Earlier records and all unfinished acceptance/interface/server tasks remain.

## Semantic prompt comparison continuation — 2026-10-14

Current original allowance:13/13 used,zero remain. See
[comparison specification](../docs/hf-prompt-comparison.md); prior balances below
are historical. This extends the same HF work and retains every earlier task.

- [x] Freeze six synthetic semantic arms with original schema/system/limits.
- [x] Verify answering/unrelated labels and absence of target objects in messages.
- [x] Prepare offline plan and pending six-attempt approval proposal.
- [x] Add separately bound extension ledger and guarded diagnostic execution.
- [x] Verify unique arms,unknown completion,privacy and unchanged exhausted ledger.
- [x] Finish regression/type/lint/mutation/preservation checks and concrete review.
- [x] Obtain explicit additional six-attempt approval before any new paid call.
- [x] Execute/audit all6 approved calls;no pair passed,qualification/application off.

Live outcome:[audited results](../docs/hf-prompt-results.md). Original13/13 and
extension6/6 exhausted;zero remain,19totalauthorized used. No candidate promotion.
Source unchanged;next offline fixture clarity/mismatch diagnostic review. Separate
provider/transport study and new budget needed before any further paid work.

Preparation checkpoint:915 full tests,zero skips;mypy100;80 combined focused
checks. No new inference/funded extension;original13/13 stays byte-unchanged.

## Hosted generation continuation — adapter source complete, acceptance pending

Current2026-10-14: [structural diagnostic](../docs/hf-structure-diagnostic.md)
complete; one syntheticHTTP400 reports empty failed_generation. No rejected
JSON to inspect,root cause unresolved. **835 passing tests,zero skips**,48 new
tests,mypy96 and preservation checks pass. **8/13 used,5 remain**. Next local
minimal reproduction and separately frozen compatibility/limit experiment.
Existing source/guards/defaults/runtime/data/models/prior trials retained.
Remaining5 cannot fund complete qualification plus the paired paper pilot.

Current: [two-route comparison](../docs/hf-route-comparison.md) complete; both
scheduled HF/Groq arms returnHTTP400/json_validate_failed with identical request
content hashes. No paper cases,usage unknown. **787 passing tests,zero skips**,
17 new tests,mypy94 and preservation checks pass. **7/13 calls used,6 remain**.
Next bounded structural diagnostics before another frozen paid experiment.
Earlier checkpoints below retain their historical attempt balances/test counts.

Latest:[qualification revision/diagnosis](../docs/hf-qualification-v2.md).
770 tests pass,zero skips,mypy92. Trial05+one diagnostic:3 new synthetic calls;
relevanceHTTP400 reportsjson_validate_failed. No paper cases. Total5/13 used,
8 remain in fixed SQLite allowance. Preserve all failed trials/guards/freezes.

Latest [retry04](../docs/hf-pilot04.md): RAM passed,two real synthetic HF/Groq
calls. Scope passed;relevance schema passed but expected decision failed. Stop
before paper cases;no retry/failover.741 tests pass,zero skips;3 new semantic
regressions/mutation and preservation checks. Only11 approved calls remain.
Next additive frozen qualification revision with production-format JSON markers
and bounded mismatch diagnostics; no selector tuning or v1 overwrite.

Latest HF-5: [hosted evaluation checkpoint](../docs/hf-evaluation.md),40 new
isolated tests; full suite738 passed,zero skips,mypy88 files. Additive protocol,
collector/scorer/development lock complete. User explicitly approved the exact
one-case13-attempt HF/Groq transfer/pilot. Approved admission02/03 were
not_started at932.93/738.29MiB free versus unchanged1024MiB; one clean WSL cache
reclaim did not meet host admission. Zero hosted requests. Existing runtime/
frozen local v2 retained. Retry same approved pilot after additional RAM is free.

Read the [HF research/architecture plan](../docs/hf-inference-research-plan.md).
This extends the current Week 7 work; it does not replace pending local acceptance
or recovery tasks. Read the [adapter checkpoint](../docs/hf-inference-adapter.md).
HF-1 through HF-4: 91 new focused tests; 698 full-suite passes, zero skips. No real
HF inference or runtime activation. Initial registry: Groq/Fireworks GPT-OSS;
Qwen/richer profiles await qualification. Conservative admission rejects the
original 30-ID schema before inference, without weakening its constraints.

- [x] Research current official HF billing, public provider/model capabilities,
  model cards and LangChain behavior; retain a dated public metadata snapshot.
- [x] HF-1: Specify a provider-neutral generation result, additive disabled HF
  settings and explicit model/provider registry. Acceptance: old local names and
  defaults unchanged; credential/endpoint/allowlist validation fails closed;
  missing usage/duration fields stay unknown. Verify offline contract/config
  tests. Depends on none. Likely files: new generation contracts, config, focused
  config/contract tests (small/medium slice).
- [x] HF-2: Implement standalone async HF chat adapter using existing httpx.
  Acceptance: fixed HTTPS router, pinned pair, original schemas/explicit token
  limits; every attempt counted with no hidden retries; sanitized 401/402/429/5xx,
  malformed/truncated/empty/oversize response handling. Verify synthetic HTTP
  transport tests with no token/network/inference. Depends on HF-1. Likely files:
  new HF client/factory and adapter tests (small/medium slice).
- [x] HF-3: Verify exact schemas and cancellation. Acceptance: retained controller
  bool/array/length and selector regex boundaries; all adversarial IDs/fields and
  reasoning-only outputs rejected; disconnect/deadline closes local work and
  never starts a fallback call. Verify focused boundary/mutation tests and compare
  unchanged canonical policy/prompt bytes. Depends on HF-2. Likely files: adapter
  tests, capability profile and acceptance notes (small/medium slice).
- [x] Checkpoint HF foundation: focused tests/type/lint pass, no network/model
  calls, canonical guard/prompt preservation verified. Rejected schema pairs stay
  unqualified; no JSON-mode downgrade to obtain green tests.
- [x] HF-4: Wire one opt-in isolated path through the existing API/workflow.
  Acceptance: default local API/model behavior unchanged; existing key/quotas and
  validated SSE retained; hosted trials uncached and readiness never performs
  paid generation. Verify offline ASGI/regression/lifespan tests. Depends on
  HF-3. Likely files: service dependency boundary/main, readiness, route/lifespan
  tests (split any slice exceeding five files).
- [x] HF-5: Freeze a separate hosted collection protocol and memory profile.
  Acceptance: unchanged local v2 files; holdout cases referenced by digest with
  no model selection on holdout; same pinned hosted model for baseline/agent,
  explicit attempt/token/deadline/concurrency/headroom and quality/latency gates.
  Verify offline protocol/collector/score validation. Depends on HF-4. Likely
  files: new hosted evaluation profile/protocol and runner tests (medium slice).
- [x] Checkpoint hosted path: full isolated regression/type/lint pass; resource
  profile and quality/latency targets fixed before live collection; original
  runtime, local models, corpus/indexes and all old evaluations remain intact.
- [ ] HF-6: After requested execution and locally configured HF credentials,
  qualify schemas with synthetic smoke calls, compare Groq gpt-oss and DeepInfra
  Qwen on development cases, then lock the chosen pair. Acceptance: exact-schema
  admission plus real task quality/latency/usage/memory evidence; budgeted read-only
  tool smoke with no new production tools; record failures and billed estimates.
  Verify complete collection records and development review. Depends on HF-5.
  Likely files: test-owned run evidence and development report (small slice).
- [x] Execute the explicitly approved initial Groq pilot once RAM admits it;
  retain failed qualification and known usage/cost. Scope passes, relevance
  expected decision fails after2 synthetic calls; no case/context transfer.
- [x] Freeze exact production-format synthetic qualification fixtures in a new
  additive revision with bounded private mismatch diagnostics. Keep original
  schemas/prompts/guards and v1 failure; enforce remaining11 approved calls before
  any new paid trial. No retry in place or automatic provider failover.
- [x] Add bounded allowlisted error-code/type diagnostics and a separately frozen
  one-attempt reproduction; discard messages/failed generations and retain
  unknown usage. Provider-reported JSON validation failure confirmed; total5 calls.
- [x] Specify/pin/test and execute the explicit provider-specific HF relay
  comparison against the unified route. Same frozen synthetic schema/controls;
  two scheduled one-attempt arms both fail400/json_validate_failed. No paper
  cases or qualification. Cumulative allowance7/13 used,6 remain; evidence kept.
- [x] Add isolated bounded structural failed-generation diagnostics with
  synthetic privacy/error-boundary tests. Persist only fixed booleans/counts;
  retain no error/generated text and do not tune schemas/prompts/guards. Freeze
  the one-call experiment and reserve its ceiling before paid work. Observed
  complete error envelope with empty failed_generation; total8/13 used,5 remain.
- [ ] Prepare a local minimal reproduction and separately freeze a compatibility/
  generation-limit experiment with fixed privacy-safe failure categories.
  Preserve original schemas/prompts/limits/defaults; any diagnostic control
  variant must be explicit. No unchanged paid repetition or support publication.
  Use cumulative remaining5 only within approved scope; complete qualification
  before paper collection and account for additional complete-pilot budget.
- [ ] HF-7: Collect/review same-model hosted baseline and agent against the
  referenced frozen holdout without tuning. Acceptance: existing semantic and
  preservation gates pass; no accepted grounding/schema/work-bound violation;
  report measured latency distribution and limits. Verify offline scorer and
  before/after preservation audit. Depends on HF-6. Likely files: test-owned
  evidence/reviews and hosted acceptance report (small slice).
- [ ] HF-8: Resume the research interface after hosted acceptance; separately
  specify a richer read-only tool workflow if development evidence requires it.
  Acceptance: source inspection/browse/search precede history; ownership precedes
  persistence; LangGraph/wrappers preserve bounded execution and reasoning history
  if introduced. Verify future UI/tool contract tests. Depends on HF-7. Detailed
  interface/server tasks remain in the existing roadmap below.

## Week 7 bounded agent source work

- [x] Audit pinned course Week 7 graph/nodes/routes and current official LangGraph docs; write [acceptance spec](../docs/week7-agent-spec.md) before code.
- [x] Add strict scope/grading/rewrite contracts and a disabled-by-default finite workflow; retain original-question identity and all evidence guards.
- [x] Bound retrievals/rewrite/generation/stages, input/output sizes and deadlines; test cancellation and abandoned-search occupancy.
- [x] Add authenticated JSON/SSE agent routes to the same global generation budget before work; verify cache bypass and validated-output ordering.
- [x] Extend allowlisted monitoring/tracing metadata; verify content privacy and scope-routing mutation detection.
- [x] Run full isolated regression suite, type/lint/Compose/diff checks and verify retained runtime identities.
- [x] Freeze eight new development and 24 holdout cases with source-reviewed facts, negative scope and disjoint source papers; preserve first-freeze novelty correction and all old evaluations.
- [x] Fix comparison/scoring/resource gates before collection; verify offline provenance, frozen hashes and novelty guard tests.
- [x] Prepare/test an isolated uncached comparison runner, fixed 192-job holdout plan, source/model/memory admission, measured budgets and response integrity checks.
- [x] Attempt guarded development-pilot admission; retain no-start evidence at 1,638 MiB free versus required 3,072 MiB, with zero inference and unchanged runtime.
- [ ] Run the development pilot once headroom meets the unchanged protocol, then compare/review the frozen holdout with baseline before enabling.
- [x] Add offline response/quotation-bound semantic review templates and fixed coverage/relevance/abstention/failure/latency scoring; reject partial or regressing holdout acceptance.
- [x] Retry resource admission after the previously documented clean WSL read-cache reclaim; retain retry02 no-start evidence at 1,354.54 MiB host RAM, zero inference.
- [ ] Measure live cold/sustained memory, latency and concurrency before activation; preserve Week 6 runtime and rollback until separately authorized.
- [ ] Build research browsing/detail/search and citation/source inspection, then define ownership before history/feedback.
- [ ] Prepare reproducible server config, HTTPS/secret injection, user/replica quotas, release/rollback and measured resource sizing.

Week 7 source checks: 552 passed, zero skips, including disposable PostgreSQL;
mypy (76 files), changed-file Ruff and Compose/diff checks passed. No live agent
evaluation or answer-quality improvement is claimed. Earlier Week 6 checks below
remain historical records.

- [x] Review and checkpoint Week 6 source, configuration, tests and local evidence; prepare [Week 7 continuation context](../docs/week7-continuation.md) for the next session.

- [x] Prepare the recommended encrypted USB transfer, pinned receiving verifier and separate-machine instructions; verify no-copy mode, internal-drive rejection, restrictive ACL and checksum boundaries on local fixtures.

Transfer preparation: [procedure](../docs/week6-off-machine-transfer.md).
User asked for a recommendation; encrypted NTFS USB with 20 GiB free and a
separate x86-64 Docker computer with 16 GiB RAM/50 GiB free are recommended.
Device/path and second-machine access are still absent; copy/rehearsal remain open.

- [x] Observe eight sequential normal Gradio requests, cold/miss/hit latency, quotas, real token usage and memory; retain evidence and verify preservation.
- [x] Reverify all 233 frozen recovery-bundle manifest files before off-machine transfer; bundle unchanged.

Observation: [report](../docs/week6-observation.md). Cache hits 263–579 ms,
misses 7.2–16.5 s, zero API failures; minimum free memory 539 MiB during cold
inference. This controlled sample does not establish sustained capacity or quality.
Off-machine destination and separate-machine access remain missing; no copy or
new recovery rehearsal has occurred.

Latest: [local activation](../docs/week6-local-activation.md) passed on 2026-10-13.
The healthy API runs one worker with caching and file monitoring; the normal
Gradio browser check passed. Original API/key and all protected data are retained.
Langfuse, Airflow and Dashboards remain stopped; no external deployment or tuning.
Earlier stopped-state statements below describe the prior staged acceptance.

Continuation on 2026-10-13: opt-in tracing, caching and offline monitoring are
implemented in source. The six original application containers were already
stopped and remain stopped; the activated image/key and frozen recovery bundle
are preserved. See [monitoring plan](../docs/week6-monitoring-plan.md) and the
new operations section. No deployment, API rebuild or selector tuning occurred.

- [x] Audit current Langfuse SDK/self-hosting, source parity, installed images and actual host/VM capacity.
- [x] Verify metadata-only isolated Langfuse OTLP export, bounded failure, correlation and SSE lifecycle before cache work.
- [x] Implement disabled-by-default signed Redis exact-match caching after authentication and quotas.
- [x] Verify policy/settings/revision invalidation, TTL, unavailable Redis, validated nonempty citations, endpoint parity and interrupted delivery.
- [x] Add bounded per-worker event files and offline percentile/failure/quota/token/cache monitoring views.
- [x] Run 494 passing tests, all-source mypy, changed-file Ruff, Compose/diff checks and preservation audit; remove owned scratch resources.
- [x] Validate a full local Langfuse backend/project/storage and stored-data UI in a separate bounded phase after RAG services are stopped.
- [x] Verify live corpus/index/model revision probes and enabled cache behavior on the separately prepared local runtime.
- [x] Activate one-worker API, Redis and file monitoring after simultaneous real-miss memory checks; verify Gradio, auth/quotas, fallback and preservation.
- [ ] Verify simultaneous loaded-model RAG/Langfuse operation and sustained-load sizing if separately requested; the memory-safe local mode keeps Langfuse stopped.

The approved staged continuation passed: [live acceptance](../docs/week6-live-acceptance.md).
Real quoted-answer cache hits took 360/265 ms, endpoint citations matched, and
real interruption/TTL/fallback/quota checks passed. Full Langfuse stored 34
metadata observations across 15 real request IDs; its isolated console rendered
them without uncaught errors. Exported events were explicitly historical replay.
Original services are restored stopped, temporary API/Redis are removed, and the
new private Langfuse lab is retained stopped. All data/model/key/bundle checks
passed. Evidence: `test_output/week6-live-20261013-01/`; no source/selector change,
deployment, commit or push. This is staged acceptance, not combined-stack sizing.

Earlier source-only evidence: `test_output/week6-monitoring-20261013-01/`. Redis acceptance used only
synthetic data and an existing installed image. Original source guard files,
model-volume fingerprints and 304 key/evaluation/bundle checksums match. No fresh
live API/readiness/corpus-count verification is claimed with the stack stopped.

Local activation approved on 2026-10-12: rebuild only the API, configure a key,
and verify access, limits, logs, readiness and the normal Gradio client. See
`test_output/week6-activation/` for acceptance/preservation evidence.

- [x] Activate the API with a saved local key and localhost binding.
- [x] Verify 401/429 behavior, healthy readiness under exhausted budgets and window reset.
- [x] Verify correlated request/retrieval/generation logs and active source parity.
- [x] Verify the normal Gradio UI renders a completed answer and paper links.
- [x] Confirm corpus/index/model/evaluation preservation and unchanged dependency containers.
- [x] Verify isolated recovery of OpenSearch, PDF/checkpoint, Ollama and Docling cache volumes using matching installed images.
- [x] Compare complete file fingerprints, search contents/vectors/mappings/aliases and model digests; remove only owned scratch resources.
- [x] Prepare a protected, checksummed recovery bundle including current source/configuration, a fresh database dump and six exact installed images.
- [x] Verify image archive integrity/load and a fresh isolated replacement API/Gradio stack from the bundle; verify the packaged rehearsal script.
- [x] Diagnose Airflow's existing webserver failure without changing live processes, DAG flags or data.
- [ ] Copy the complete bundle to protected off-machine storage and verify receiving checksums (destination not yet available).
- [ ] Rehearse on a separate replacement machine; verify full machine-loss recovery before any cutover.

Continuation evidence: `test_output/replacement-recovery-20261012-01/`. The local
bundle is about 8.35 GiB and includes private credentials under a restricted ACL.
Docker image load and isolated replacement/API/Gradio checks passed; scratch
resources were removed. All 8,828 previous artifacts and source/runtime/data/key
fingerprints remained intact. Existing Airflow failure is a stale monitor PID
collision plus missing `pkill`; diagnosis is verified, no live repair applied.
All attached drives are internal; off-machine copy remains pending a destination.

Volume recovery passed on 2026-10-12; evidence is in
`test_output/volume-recovery-20261012-01/`. API/Gradio health, all existing
artifacts/workspace files, the key, corpus and models were preserved. OpenSearch
and Ollama had brief local maintenance stops; Airflow retained its preexisting
unhealthy process state after a cache-archive pause. No deployment or tuning.

Activation checks: 476 tests passed including Docker integration tests, Ruff and
mypy passed, 72 source files match the active image, and the Gradio client is
available at `http://127.0.0.1:7861`. No external deployment or selector tuning.

- [x] Audit four areas and compare the course reference before implementation.
- [x] Request IDs, total latency and safe selector/stream JSON events; verify success, HTTP failure and SSE failure.
- [x] API key and shared budgets; verify rejection before work, window reset, concurrent workers and store failure.
- [x] OpenSearch readiness and local configuration; verify missing aliases/red/unreachable dependencies.
- [x] Backup/restore procedure; verify full-content restore into an isolated empty database.
- [x] Full checks, runtime evidence, preservation audit and final documentation.

Deployment remains outside scope. Answer-quality defects and fresh-data requirements
remain open in `plan.md` and the selector report; they are not Week 6 completion gates.

Verified: 443 passed, 32 existing integration skips; Ruff/mypy/Compose/diff checks
passed. Real database restore matched all 58 paper rows/fields and schema revision.
The temporary two-worker API passed authentication, readiness, SSE and shared
quota checks. Original runtime and corpus were left intact.

Before any separately approved deployment: rehearse machine-loss recovery,
provision off-machine backups, choose multi-replica limits if needed, and replace
development-only infrastructure configuration. Cold-volume recovery is now
verified locally; the remaining items are not verified deployment controls.
