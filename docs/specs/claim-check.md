# claim-check: per-claim grounding with verifiable proof

Status: design approved 3 November 2026; implemented offline the same day
([plan](../../tasks/claim-check-plan.md)); the live check is pending owner approval.
Two refinements made during implementation: a span may not exceed 200 characters
(an overlong one is unverified, not fatal), and the minimum is three words or the
whole quote when the quote itself is shorter.
Inherits [shared rules](researcher-app.md) and refines
[paper-tutor](paper-tutor.md) and [study-research](study-research.md).
Replaces the whole-lesson grounding review in `src/services/study/tutor.py`.

## Why

On 3 November 2026 the owner's live Telegram tests showed the whole-lesson
review failing in both directions:

- It kept two false superiority claims read from one Table 1 cell
  (`55.2%/66.1% (EM/Recall)` and `56.8/68.0 … متفوقًا على … DPR`; DPR's 57.9
  beats 56.8 on standard TQA). Both are now frozen in
  [science cases](../../evaluation/paper_learning/README.md).
- It rejected every section of four first lessons, and in an owner-approved
  A/B it rejected 1 of 4 verified-correct sections with either prompt revision.
- It kept a section containing a 1,460-character degenerate run.

A single verdict over a whole lesson is shallow, and one doubtful sentence
sinks a whole section. The goal: judge each claim against its own quote, keep
what passes, and accept a model's "supported" only with proof the application
can check without trusting the model.

## Decisions (owner)

- An unconfirmed claim is **withheld**: never shown with a page badge; only a
  count and its section heading appear in one closing note.
- A lesson keeps **two model calls**: write, then check. `/deep` stays at two
  research calls plus one check (three of its four).
- Approach A: the writer produces one-quote claims; the checker must copy
  supporting spans that the application verifies.

## 1. Writer output and deterministic checks

Draft schema (strict JSON mode needs one fixed shape, so every section has both
fields and the application enforces which is used):

```text
DraftClaim   { text: str (Arabic sentence, ≤400 chars), evidence_id: catalog snippet ID }
DraftSection { heading, kind, text, evidence_ids: [≤3], claims: [DraftClaim] }
  kind = paper            → text == "" and evidence_ids == [] and 1 ≤ len(claims) ≤ 5
  kind ≠ paper            → claims == [] and text non-empty (evidence_ids optional, as today)
```

Mixing the two forms is a `shape` failure of the lesson, as today.

Before any model check, each claim is withheld (the lesson continues) when:

| Check | Reason label |
| --- | --- |
| `evidence_id` not in the catalog | `unsupported_quote` |
| a number in the claim is absent from **its own** quote (same `_numbers` rules) | `unsupported_number` |
| degenerate repetition (existing screen) | `degenerate_text` |
| better/best/outperforms when the learner did not ask for a comparison (existing screen) | `unrequested_comparison` |

A section with no surviving claims is withheld whole. The lesson fails with
`lesson_validation_failed` only when no paper claim survives anywhere; that is
today's rule applied per claim. The existing Arabic-letter minimum still applies
to the accepted lesson.

The accepted `Lesson` keeps today's stored shape: surviving claim texts are
joined in order (separated by a space) into the section `text`, and their quotes
become its `evidence`. Claims exist only between writing and acceptance, so
stored lessons, `/notes`, the reading map and `render_lesson` need no migration.

## 2. The check call and proof verification

One call (`purpose="grounding_review"`, existing attempt accounting) receives:

- each surviving paper claim as `c0, c1, …` with its claim text, its own quote,
  and its full cited block for context (same 16,000-character context budget);
- each analogy as `a0, a1, …` with its text.

Strict output schema, one verdict per item:

```text
ClaimVerdict { id: enum(item IDs), supported: bool, support_spans: [1..3 str ≤200],
               issue: none | missing_support | contradiction | overgeneralized_comparison
                      | metric_setting_mismatch | unlabeled_background | analogy_mismatch }
ClaimCheck   { verdicts: [ClaimVerdict] }
```

Prompt rule: copy the exact words from **this claim's quote** that state it; if
it needs another passage, a different table column or outside knowledge, mark it
unsupported. The cited block is for reading captions and headers, not a source of
spans.

A paper claim is kept only when its verdict is `supported` **and**:

1. every span is an exact substring of the claim's quote after collapsing
   whitespace;
2. the spans together contain at least three words;
3. every number in the claim (per `_numbers`) appears inside the spans.

Up to three spans are allowed because a table claim needs the caption and the
row, which are far apart in the same quote.

Otherwise the claim is withheld with a reason: `unsupported` (verdict false, with
its issue label), `unverified_support` (verdict true but proof fails), or
`missing_verdict` (no, duplicate or unknown ID). Analogies are kept on
`supported=true` and withheld on false, with no span check. If the response does
not parse against the schema, nothing can be confirmed and the job fails with
`review_validation_failed`, as today.

What this guarantees: every kept claim points at words the student can see under
it, and its numbers are located in those words. What it does not guarantee:
that the checker judged the meaning correctly. The superiority screen therefore
stays in front, and table semantics remain the job of verified cells (C2/E3).

## 3. Student view, paths and compatibility

Telegram shows surviving claims as one paragraph per section with
`↩︎ المصدر: ص …` for their pages. Withheld material appears once at the end,
with counts and headings only:

```text
⚠️ شلت 3 جمل ماقدرتش أتأكد منها من نص الورقة (في «الطريقة»، «النتيجة»). اسألني عنها بسؤال أضيق.
```

Withheld claim text never appears in the reply, `/notes` or the job result.
`/notes` lists only the quotes of surviving claims. Existing RTL handling
(`rtl_line`) is unchanged.

| Path | Calls | Change |
| --- | --- | --- |
| First lesson, follow-up | write 1 + check 1 | claim format, per-claim checks, claim check |
| `/quiz` (question only) | write 1 | none: no paper claims, no check call |
| `/deep` | research 2 + check 1 | worker's final schema uses claims; worker validates shape (`validation` stage); parent screens and checks (`result_validation`, `review` stages) |

`PROMPT_REVISION` becomes v7. `GroundingReview`/`review_lesson` and
`REVIEW_PROMPT` are replaced by `ClaimCheck`/`check_claims` and `CLAIM_PROMPT`;
the v4–v6 review prompts remain in git history. The job's review report records
label counts only: `claims`, `kept`, and withheld counts per reason (plus the
existing `screened` list), for the failure ledger (Q0).

## 4. Tests, limits and rollout

Offline, zero model calls, before any live run:

- Writer format: paper/claims and other/text rules; mixed form is `shape`.
- Per-claim deterministic checks withhold only the offending claim; the lesson
  fails only when no paper claim remains.
- Proof verification with scripted checkers: honest spans kept; span not in the
  quote, under three words, or a claim number outside the spans is
  `unverified_support`; duplicate/unknown/missing verdicts are `missing_verdict`;
  an unparsable response is `review_validation_failed`.
- Science fixtures converted to claims: all four verified-correct sections
  survive an honest checker; each of the twelve critical cases records and is
  stopped at its expected layer (deterministic, screen, or check call with its
  exact quote).
- Rendering: claims joined in order, one closing note, withheld text absent from
  the reply, `/notes` and stored result.
- `/deep`: the real SDK loop with a stubbed provider returns a claim-format
  answer; existing failure-injection tests still pass.
- Full unit/API suite, research-environment suite, Ruff and mypy.

Live check only with explicit owner approval: about six calls (first lesson,
the TQA-Wiki question, `/deep`). It measures writer format compliance, withheld
claims per lesson, and whether the two observed false claims are stopped. If the
writer often breaks the format, tighten the prompt; do not add calls.

Known limits: spans prove location, not understanding; superiority claims the
learner asked for rely on the check call; equation signs stay uncovered until a
reviewed equation fact exists.

Rollout as two commits within the five-file guideline:

1. Claim format and per-claim deterministic checks: `tutor.py`, `service.py`,
   science fixture JSON/README, `test_study_science_fixtures.py`,
   `test_study_feedback.py`. The existing review keeps running on the joined
   sections until commit 2.
2. Claim check call, rendering note and `/deep`: `tutor.py`, `service.py`,
   `src/commands/study_research.py`, `research/tests/test_deep.py`,
   `test_study_feedback.py`.

## Acceptance

CC-1: Every kept paper claim has verified spans inside its own quote containing
all of its numbers; no withheld claim text reaches the learner or storage.

CC-2: With an honest scripted checker, the four verified-correct fixture sections
survive; with a dishonest one, unsupported or misplaced proof is withheld.

CC-3: First lessons and follow-ups use two calls and `/deep` three; existing
attempt accounting, stages and failure categories still hold.
