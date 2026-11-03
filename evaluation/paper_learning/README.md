# Paper-learning science regression cases

`science-cases.v1.json` freezes known scientific mistakes as single lesson
sections, so the existing validator and review routing are tested against
them without a model call. It is development regression data for one paper,
arXiv [2005.11401v4](https://arxiv.org/abs/2005.11401v4). It is not an
independent scientific evaluation and not the release holdout.

## Source of truth

All facts come from the reviewed
[RAG visual fixture](../visual_learning/rag-method.v1.json) (same PDF SHA256 and
parser revision); this file adds no new truth set. Locators are rebuilt from
that fixture, except one short verified excerpt of the table itself:

- `reviewed_excerpts`: the fixture's short exact quotes for one block, joined.
- `native_extract_excerpt`: the exact Table 1 caption and rows (421 characters)
  from the native extraction of the same PDF/parser revision, checked on
  3 November 2026. It contains the reviewed TQA-Wiki EM values (Token 66.1,
  Sequence 68.0). When the ignored PDF is present, a test re-extracts it and
  confirms the excerpt is an exact substring; CI uses the stored excerpt.

## Cases and what currently stops them

Four supported sections must pass. Twelve critical errors cover four of the
spec's five critical classes and every reviewed rejected claim. Two offline
layers run before the model review: validation (numbers, citations) and, since
3 November 2026, screening (degenerate text, and superiority claims the learner
did not ask for):

| Class | Critical cases | Stopped offline? |
| --- | --- | --- |
| Training updates | document encoder updated; paper claim with no evidence | Only the missing-evidence case |
| Token/paragraph mechanism | token-as-paragraph analogy; new retrieval per token | No — review only |
| Best result | Token "best" on TQA-Wiki; invented score; invented score after an Arabic prefix; **observed** TQA pair as one result "outperforming DPR" | Invented numbers (validation); unrequested "best"/"outperforms" (screen) |
| Units/splits | wrong TriviaQA split; F1 instead of EM; score read as a percent gain; **observed** split pair read as EM/Recall | Only claims that also say "better/outperforms" (screen) |

In a first lesson, validation stops **3 of 12** and screening **4 more**. If the
learner asks who is better, the screen steps aside, so 3 of 12 are stopped
offline and the rest rely on the review. The remaining 5 (wrong split, F1 vs EM,
percent gain, document encoder, per-token retrieval/analogy) have correct
numbers and citations; the tests prove they reach the review with full cited
context and are withheld when flagged. They do **not** prove the model flags
them, and two observed claims show it sometimes doesn't.

Equation signs stay open: the reviewed fixture has no source-checked equation
fact, so no case was invented for it.

## Observed in a live lesson (3 November 2026)

The owner's first RAG lesson said `RAG-Token وصل 55.2%/66.1% (EM/Recall)
متفوقًا على النماذج السابقة`. Both numbers are EM, on the standard TQA and
TQA-Wiki test sets, and 55.2 is below DPR's 57.9, so the superiority claim is
false. It passed the live grounding review and reached the owner. Case
`observed-tqa-cell-read-as-em-recall` keeps it. Prompt revision v5 now asks the
lesson and the review to name the split and metric of every number and to read
an `a/b` cell as two columns; that is a mitigation, not a proven fix.

A second live first lesson the same day said `RAG‑Sequence … 56.8/68.0 EM على
TQA (العمود اليمين)، متفوقًا على … DPR`: the pair is two test sets, and DPR's
57.9 beats 56.8 on standard TQA. The live review kept all six sections. Case
`observed-tqa-pair-as-one-result` keeps it; the superiority screen now
withholds it.

## Review A/B, owner-approved 2 calls (3 November 2026)

After every live first lesson came back with all sections rejected, the review
alone ran once with the v4 prompt and once with v5 (v5 adds only the two
table-split lines). Input: one lesson made of the four supported sections above,
over the same locators. Separate diagnostic store, ceiling 2, no Telegram.

| Prompt | Kept | Rejected | Issue |
| --- | --- | --- | --- |
| v4 | 3 of 4 | 1 | `missing_support` |
| v5 | 3 of 4 | 1 | `missing_support` |

So the v5 lines did not cause the live rejections. The reviewer did wrongly
reject one verified-correct section with either prompt. That's one run, not a
rate. Which section isn't known: the report then stored counts only. It now also
stores `rejected_sections` (indices). The live failures point at the lesson
text or its evidence; a full lesson run would need its own approval.

## Defect found while freezing these cases

The unsupported-number check skipped digits glued to Arabic letters. `و70.2`
or `بـ70.2` extracted only `2`, and `بـ71` extracted nothing, so an invented
score could pass. The same bug falsely rejected a correct `لـ68.0`. Since
3 November 2026 only ASCII identifiers (`F1`, `p6b0`) hide a digit. Case
`invented-score-after-arabic-prefix` fails on the earlier code.

## Holdout

The 12-paper/48-question holdout is **not reserved** here. It needs its own
source review, and its papers must not overlap this development paper; the test
enforces that once a holdout is recorded.

```powershell
.venv-win/Scripts/python.exe -m pytest tests/unit/test_study_science_fixtures.py -q -o cache_dir=tests/test_output/study-pytest --basetemp tests/test_output/science-fixtures-fresh
```
