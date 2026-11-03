# Claim Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the whole-lesson grounding review with per-claim checks whose "supported" verdicts carry proof spans the application verifies.

**Architecture:** The writer emits paper sections as one-quote claims (`ClaimDraft`). Deterministic per-claim checks and screens withhold individual claims; one model call (`check_claims`) returns per-claim verdicts with spans, verified in code. `accept_draft` joins surviving claims back into today's `Lesson` shape, so storage, `/notes`, the reading map and rendering keep working.

**Tech Stack:** Python 3.12, Pydantic v2 strict models, pytest + anyio, existing `StudyModel` transport (HF router, strict `json_schema`), Deep Agents 0.7.28 in `.venv-study-research`.

**Spec:** [docs/specs/claim-check.md](../docs/specs/claim-check.md)

## Global Constraints

- Unconfirmed claims are withheld: never shown, never stored, never in `/notes`; only counts and section headings in one closing note.
- First lessons and follow-ups use exactly two model calls (write + check); `/quiz` with no paper claims makes no check call; `/deep` uses two research calls + one check.
- Paper section: `text == ""`, `evidence_ids == []`, `1 ≤ len(claims) ≤ 5`; claim text ≤400 characters, exactly one `evidence_id`. Other kinds: `claims == []`, non-empty `text`, `evidence_ids` ≤3.
- A kept claim needs: verdict `supported`, 1–3 spans of ≤200 characters each, every span an exact substring of the claim's own quote after whitespace collapsing, ≥3 words across spans, every `_numbers` value of the claim inside the spans.
- Withheld reasons (finite labels): `unsupported_quote`, `unsupported_number`, `degenerate_text`, `unrequested_comparison`, `unsupported`, `unverified_support`, `missing_verdict`.
- Lesson fails with `lesson_validation_failed` only when it had paper claims and none survive; an unparsable check response fails with `review_validation_failed`.
- `PROMPT_REVISION = "egyptian-grounded-tutor-context-review-v7"`. Check calls keep `purpose="grounding_review"` (attempt accounting unchanged) and the 16,000-character cited-block context budget.
- No model calls in any test. Every pytest run uses `-o cache_dir=tests/test_output/study-pytest --basetemp tests/test_output/<fresh-name>`.
- Write source files with LF endings (`newline="\n"`); escapes such as `‏` stay escapes in source.

## Review Focus

- Hyphen and quote variants: the model copies `RAG‑Token` (U+2011) or curly quotes while the quote has ASCII; a correct claim should still be kept (normalize U+2010–U+2015, U+2212 to `-` and curly quotes to straight on both sides before the substring test). Pinned in Task 4.
- Arabic-Indic digits in a claim (`٦٨٫٠`) against ASCII `68.0` in the span should count as present (reuse `_numbers`). Pinned in Task 4.
- Quotes containing newlines or double spaces versus single-spaced spans should match. Pinned in Task 4.
- Lessons stored before v7 (including `WITHHELD` uncertainty sections) must still render and appear in `/notes` unchanged. Pinned in Task 2.
- Many claims citing one block must send that block once in the check payload, inside the 16,000-character budget. Pinned in Task 4.

---

### Task 1: Claim draft contract

**Files:**
- Modify: `src/services/study/tutor.py` (`DraftSection`, `LessonDraft`, `lesson_schema`, `validate_lesson`, `SYSTEM`, `PROMPT_REVISION`)
- Create: `tests/unit/test_study_claims.py`

**Interfaces:**
- Produces:
  - `class DraftClaim(StrictModel)`: `text: str (1..400)`, `evidence_id: str (0..40)`.
  - `DraftSection` gains `claims: list[DraftClaim] (max 5)`; `text` allows `""`.
  - `@dataclass class Claim`: `text: str`, `support: Support | None`, `withheld: str | None = None`.
  - `@dataclass class ClaimSection`: `heading: str`, `kind: str`, `text: str`, `evidence: list[Support]`, `claims: list[Claim]`.
  - `@dataclass class ClaimDraft`: `title: str`, `sections: list[ClaimSection]`.
  - `validate_draft(raw: dict, blocks: list[EvidenceBlock]) -> ClaimDraft`: shape errors raise `TutorError("lesson_validation_failed", diagnostic="shape")`; non-paper unknown IDs raise `diagnostic="unsupported_quote"` (as today); per-claim unknown ID → `withheld="unsupported_quote"`; per-claim numbers not in its own quote → `withheld="unsupported_number"`.
  - `accept_draft(draft: ClaimDraft) -> tuple[Lesson, dict[str, int]]`: joins kept claims (single space) into section `text`, unique supports in order as `evidence`; drops sections with no kept claims; returns `{heading: withheld_count}`. Raises `lesson_validation_failed` with the first withheld reason as diagnostic when the draft had paper claims and none survive, and `arabic_output_required` per today's rule.
  - `validate_lesson(raw, blocks) -> Lesson` stays as `accept_draft(validate_draft(raw, blocks))[0]` for the worker and existing callers.
  - `lesson_schema(blocks, *, followup=False) -> dict` sets the snippet-ID enum on both `evidence_ids.items` and `claims.items.evidence_id` (enum plus `""` for the latter, so a claim with no valid ID is representable and withheld).

- [ ] **Step 1: Write failing tests in `tests/unit/test_study_claims.py`**
  - `test_paper_sections_must_use_claims_and_others_must_use_text`: a paper section with non-empty `text`, a paper section with zero claims, and a background section with claims each raise `TutorError` with `diagnostic == "shape"`.
  - `test_unknown_claim_quote_is_withheld_not_fatal`: two claims, one with `evidence_id="p9b9s0"`; `validate_draft` marks it `withheld == "unsupported_quote"`, the other `None`; `accept_draft` returns one section whose text equals the kept claim and `{"heading": 1}`.
  - `test_numbers_are_checked_against_each_claims_own_quote`: claim A cites a quote containing `66.1` and states `68.0`; claim B cites the quote with `68.0`; A is `unsupported_number`, B kept.
  - `test_lesson_fails_only_when_no_paper_claim_survives`: every claim withheld → `TutorError` with `diagnostic == "unsupported_quote"`.
  - `test_schema_offers_catalog_ids_to_claims`: `lesson_schema(blocks)["$defs"]["DraftClaim"]["properties"]["evidence_id"]["enum"]` equals catalog IDs plus `""`.

- [ ] **Step 2: Run them to see them fail**

Run: `.venv-win/Scripts/python.exe -m pytest tests/unit/test_study_claims.py -q -o cache_dir=tests/test_output/study-pytest --basetemp tests/test_output/claims-t1-red`
Expected: FAIL (ImportError on `validate_draft`).

- [ ] **Step 3: Implement the models and functions above in `tutor.py`; update `SYSTEM`**

Replace the "Every such section MUST have 1-3 evidence_ids" paragraph with: paper sections leave `text` empty and give 1–5 claims, each one Egyptian Arabic sentence with exactly one snippet ID from the catalog; other kinds use `text`. Bump `PROMPT_REVISION` to v7.

- [ ] **Step 4: Run new and existing tutor tests**

Run: `.venv-win/Scripts/python.exe -m pytest tests/unit/test_study_claims.py tests/unit/test_study_tutor.py -q -o cache_dir=tests/test_output/study-pytest --basetemp tests/test_output/claims-t1-green`
Expected: PASS. Update existing `test_study_tutor.py` drafts that build paper sections with `text`/`evidence_ids` to the claim form; do not weaken their assertions.

- [ ] **Step 5: Commit** — `feat: write paper sections as one-quote claims with per-claim checks`

### Task 2: Per-claim screens, wiring and the closing note

**Files:**
- Modify: `src/services/study/tutor.py` (`screen_sections` → `screen_claims`, `render_lesson`), `src/services/study/service.py` (`_teach`), `tests/unit/test_study_feedback.py`

**Interfaces:**
- Consumes: Task 1 `ClaimDraft`, `validate_draft`, `accept_draft`.
- Produces:
  - `screen_claims(draft: ClaimDraft, *, question: str = "") -> ClaimDraft`: per claim `degenerate_text` / `unrequested_comparison` (same regexes and `COMPARISON_REQUEST` rule as today); a non-paper section with degenerate text loses its `text` and is dropped by `accept_draft`.
  - `draft_report(draft: ClaimDraft) -> dict`: `{"claims": int, "kept": int, "withheld": {reason: count}}`.
  - `render_lesson(..., withheld: dict[str, int] | None = None)`: closing note `⚠️ شلت N جمل ماقدرتش أتأكد منها من نص الورقة (في «h1»، «h2»). اسألني عنها بسؤال أضيق.` (use `جملة واحدة` when N == 1); legacy `WITHHELD` sections still collapse into the existing note.
- `_teach` order: `validate_draft` → `screen_claims` → `accept_draft` → existing `review_lesson` on the accepted lesson (replaced in Task 5). Job `review` report = `draft_report(...)` merged with the review's counts.

- [ ] **Step 1: Write failing tests in `tests/unit/test_study_feedback.py`**
  - Rewrite `test_degenerate_and_unrequested_superiority_sections_are_withheld_not_shown` to the claim form: one section with three claims (clean, degenerate, "متفوق"); the job is `ready`, its text contains the clean claim only, `review["withheld"] == {"degenerate_text": 1, "unrequested_comparison": 1}`, and the note reads `شلت 2 جمل` with the heading.
  - `test_withheld_claim_text_never_reaches_reply_notes_or_storage`: the withheld claim string is absent from `job["result"]["text"]`, from `StudyService.notes(...)`, and from the stored lesson JSON.
  - `test_lessons_stored_before_v7_still_render`: a `Lesson` with a legacy `WITHHELD` uncertainty section renders the existing `⚠️ شلت 1 جزء` note and `/notes` lists its quotes.

- [ ] **Step 2: Run to see them fail** (same command pattern, basetemp `claims-t2-red`).

- [ ] **Step 3: Implement `screen_claims`, `draft_report`, the `withheld` render parameter and the `_teach` wiring**

Remove `screen_sections`; keep `DEGENERATE`, `SUPERIORITY`, `COMPARISON_REQUEST` unchanged.

- [ ] **Step 4: Run feedback, service, telegram and claims tests** (basetemp `claims-t2-green`). Expected: PASS.

- [ ] **Step 5: Commit** — `feat: screen claims individually and summarize withheld claims once`

### Task 3: Science fixtures in claim form

**Files:**
- Modify: `evaluation/paper_learning/science-cases.v1.json`, `evaluation/paper_learning/README.md`, `tests/unit/test_study_science_fixtures.py`

**Interfaces:**
- Consumes: Task 1 `validate_draft`/`accept_draft`, Task 2 `screen_claims`.
- Produces: each case's `section` in claim form (paper: `text ""`, `claims: [{text, evidence_id}]`); `expected.deterministic` becomes `kept` or `withheld:<reason>`; `expected.screen` unchanged; `paper-claim-without-evidence` uses `evidence_id: ""` and expects `withheld:unsupported_quote`.

- [ ] **Step 1: Update tests first**
  - `test_offline_validation_matches_the_frozen_outcome`: for `kept`, `accept_draft(validate_draft(...))` keeps the claim text; for `withheld:<r>`, the single claim carries `withheld == r` and `accept_draft` raises with `diagnostic == r`.
  - `test_first_lesson_screen_matches_the_frozen_outcome`: uses `screen_claims` and asserts the claim's `withheld` equals `expected.screen`.
  - Keep identity, locator, rejected-claim coverage, critical-class and holdout tests unchanged.
- [ ] **Step 2: Run to see them fail** (basetemp `claims-t3-red`).
- [ ] **Step 3: Convert the 16 cases in the JSON; update the README counts table wording to "claims"** (numbers stay 3 validation + 4 screen of 12).
- [ ] **Step 4: Run the science fixture tests** (basetemp `claims-t3-green`). Expected: PASS, including the local-PDF substring test when the PDF exists.
- [ ] **Step 5: Commit** — `test: freeze science cases as one-quote claims` (end of the spec's first commit milestone).

### Task 4: The check call and proof verification

**Files:**
- Modify: `src/services/study/tutor.py`, `src/services/study/failures.py` (add the seven withheld reasons to `SAFE_DIAGNOSTICS`)
- Modify: `tests/unit/test_study_claims.py`

**Interfaces:**
- Consumes: Task 1 `ClaimDraft`, `Claim`.
- Produces:
  - `class ClaimVerdict(StrictModel)`: `id: str`, `supported: bool`, `support_spans: list[str] (0..3, each ≤200)`, `issue: Literal["none","missing_support","contradiction","overgeneralized_comparison","metric_setting_mismatch","unlabeled_background","analogy_mismatch"]`.
  - `class ClaimCheck(StrictModel)`: `verdicts: list[ClaimVerdict] (max 40)`.
  - `CLAIM_PROMPT: str` — spec section 2 rule text.
  - `verify_support(claim_text: str, quote: str, spans: list[str]) -> bool`: normalize whitespace, hyphen variants (U+2010–U+2015, U+2212 → `-`) and curly quotes on both sides; all spans substrings; ≥3 words total; `_numbers(claim_text) <= _numbers(" ".join(spans))`.
  - `async def check_claims(model, job_id: str, draft: ClaimDraft, *, blocks: list[EvidenceBlock], report: dict | None = None) -> ClaimDraft`: items `c<i>` for kept paper claims and `a<i>` for analogies; schema enum on `id`; one `model.complete(job_id, "grounding_review", ..., schema=...)`; unparsable → `TutorError("review_validation_failed")`; applies `unsupported` / `unverified_support` / `missing_verdict`; an analogy with `supported=false` is dropped (counted under its issue). Returns without a call when there are no items.

- [ ] **Step 1: Write failing tests**
  - `test_honest_spans_keep_the_claim` and `test_span_outside_quote_is_unverified`, `test_fewer_than_three_words_is_unverified`, `test_number_outside_spans_is_unverified`.
  - `test_duplicate_unknown_or_missing_verdicts_withhold_only_those_claims`.
  - `test_unparsable_response_fails_the_review` (`diagnostic` absent, code `review_validation_failed`).
  - `test_no_items_means_no_call` (a stub that fails if called).
  - Review Focus: `test_hyphen_and_quote_variants_still_verify` (claim/span with U+2011 vs quote ASCII), `test_arabic_indic_digits_count_as_present` (`٦٨٫٠` vs `68.0`), `test_whitespace_differences_still_verify` (quote with `\n` and double spaces), `test_repeated_block_is_sent_once` (15 claims on one block → one entry in `source_context`).
- [ ] **Step 2: Run to see them fail** (basetemp `claims-t4-red`).
- [ ] **Step 3: Implement the models, `CLAIM_PROMPT`, `verify_support` and `check_claims`.**
- [ ] **Step 4: Run claims tests** (basetemp `claims-t4-green`). Expected: PASS.
- [ ] **Step 5: Commit** — `feat: check claims with proof spans the app verifies`

### Task 5: Replace the whole-lesson review

**Files:**
- Modify: `src/services/study/service.py` (`_teach`), `src/services/study/tutor.py` (delete `GroundingReview`, `REVIEW_PROMPT`, `review_lesson`), `tests/unit/test_study_feedback.py`, `tests/unit/test_study_tutor.py`, `tests/unit/test_study_science_fixtures.py`

**Interfaces:**
- Consumes: Task 4 `check_claims`; Task 2 `draft_report`.
- `_teach` order: `validate_draft` → `screen_claims` → (stage `review`) `check_claims` → `accept_draft` → render with `withheld`. `/deep` stage tagging (`result_validation`, `review`) unchanged.

- [ ] **Step 1: Update tests that used `review_lesson`** to scripted `check_claims` stubs returning verdicts; keep each test's intent (`/deep` review stage + report, review sees full cited context, rejected analogy withheld). The science routing test asserts every `review: reject` case reaches `check_claims` with its exact quote and is withheld when the scripted verdict is false, and that all four supported cases survive an honest scripted checker (CC-2).
- [ ] **Step 2: Run to see them fail** (basetemp `claims-t5-red`).
- [ ] **Step 3: Wire `check_claims` in `_teach`; delete the old review code.**
- [ ] **Step 4: Run all study tests** (`tests/unit/test_study_*.py`, basetemp `claims-t5-green`). Expected: PASS; a first lesson in the service tests records exactly two attempts (CC-3).
- [ ] **Step 5: Commit** — `feat: replace the whole-lesson review with per-claim checks`

### Task 6: `/deep` in claim form

**Files:**
- Modify: `src/commands/study_research.py` (system text: `evidence_id` per claim), `research/tests/test_deep.py`

**Interfaces:**
- Consumes: Task 1 `lesson_schema(followup=True)` and `validate_lesson` (shape + surviving claims), unchanged signatures.

- [ ] **Step 1: Update `_answer()` and the success test in `research/tests/test_deep.py`** to return `{"title", "sections": [{"heading","kind":"paper","text":"","evidence_ids":[],"claims":[{"text": ..., "evidence_id":"p1b1s0"}]}]}`; `test_block_id_instead_of_snippet_id_fails_validation` now expects `{"error":"lesson_validation_failed","diagnostic":"unsupported_quote","stage":"validation"}` via the withheld-claim path.
- [ ] **Step 2: Run to see them fail**

Run: `.venv-study-research/Scripts/python.exe -m unittest discover -s research/tests -v`
Expected: FAIL on the updated cases.
- [ ] **Step 3: Update the worker's system text.**
- [ ] **Step 4: Rerun the research suite.** Expected: all tests OK; parent `/deep` test in `test_study_feedback.py` records three attempts (CC-3).
- [ ] **Step 5: Commit** — `feat: return /deep answers as one-quote claims`

### Task 7: Verification and records

**Files:**
- Modify: `docs/specs/claim-check.md` (status line), `tasks/todo.md` (F1/F2 notes), `evaluation/paper_learning/README.md` (layer table)

- [ ] **Step 1: Full checks**

Run: `.venv-win/Scripts/python.exe -m pytest tests/unit tests/api -q -o cache_dir=tests/test_output/claims-pytest --basetemp tests/test_output/claims-full` (background, about 15 minutes), then `.venv-win/Scripts/python.exe -m ruff check src tests research` and `.venv-win/Scripts/python.exe -m mypy src`.
Expected: all pass, 2 known Typer/Click deprecation warnings.
- [ ] **Step 2: Update the spec status to "implemented offline; live check pending", and the README/todo records with the actual counts.**
- [ ] **Step 3: Commit** — `docs: record the offline claim check implementation`
- [ ] **Step 4: Ask the owner before the ~6-call live check;** report format compliance, withheld claims per lesson and whether both observed false claims are stopped.
