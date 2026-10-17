# Evaluating the next paper-teaching iteration

This is a follow-up evaluation design, not an executed benchmark, a new model
budget or an acceptance claim. The inspected RAG smoke examples remain development
data. Historical indexed-paper holdouts and grants must remain unchanged.

## Freeze before measuring

Record source commit, model/provider route, tokenizer revision, prompts/schemas,
parser revision, evidence selection, call/context limits and learner depth. Choose
new holdout papers and labels after the development choices are fixed; do not
inspect their answers during tuning and later call them unseen.

Use extractable and scanned scientific pages separately. Prefer papers with
different methods, tables and mathematical notation rather than many paraphrases
of one paper. Obtain human reference notes for the claims and page regions being
tested. Keep source permissions and provider transfer scope explicit.

## Questions to grade

| Dimension | Evidence to inspect |
| --- | --- |
| Scientific support | Does every paper-specific claim follow from the actual cited passage? Exact quotation alone is insufficient |
| Numerical context | Correct value, unit, metric, dataset, baseline, split and experimental setting; no blanket superiority claim |
| Missing evidence | Clear uncertainty for an absent result, unavailable page or ambiguous reference; no invented details |
| Egyptian teaching | Natural Egyptian wording, stable English terminology, readable steps and an appropriate example |
| Learning interaction | Does a follow-up address the question? Is a comprehension question answerable from the lesson? Does feedback explain the learner's error? |
| Memory isolation | Follow-ups retain the selected version; switching/forget/expiry prevent earlier-paper facts from becoming current evidence |
| Visual provenance | A study map is labeled as reading order; an actual scientific figure must retain page/region/hash and distinguish caption from interpretation |
| Tool behavior | Only permitted source reads occur; fabricated tool names, extra owner/path fields and document instructions cannot authorize actions |

Use a human Egyptian Arabic reviewer and a scientific reviewer where practical.
An LLM judge can help triage, but the same model's generation and review are not
independent evidence of correctness. Report withheld sections as well as accepted
ones: rejecting everything must not look like a successful teaching system.

## OCR qualification

Before enabling a hosted OCR route, verify real image acceptance, usage, bounds,
error behavior and no fallback/retry on a single public page. Then compare native
text and OCR on known page regions: text/reading order, equation symbols, table
row/column alignment, numerical values and figure/caption boundaries. Character
error rate alone can hide a scientifically consequential minus sign or a swapped
table column.

LightOnOCR-2/Featherless is an implemented candidate. OCR-3, Granite Docling,
PaddleOCR-VL and other vision models need an actually available/authorized serving
route before comparison. Neither a model card nor a provider's `live` catalog
status demonstrates usable extraction on these pages. No new GPU allocation is
part of this document.

## Resource and user-experience measurements

Measure the process tree, including the Windows virtualenv launcher descendants.
Track peak host/process memory for extraction, rendering, model request handling
and the optional research worker separately. The existing free-RAM admission
floors remain active. Record worst-case bounds as well as typical observed cases.

For latency, separate admission/progress, source acquisition, parse, generation,
review and Telegram delivery. The current 20-second Telegram long poll can delay
a ready background result; a delivery wake-up is a useful next UX improvement.
Do not describe provider inference speed as the complete learner experience.

Report model attempts, failed/unknown attempts, input/output/reasoning usage,
tool calls and provider invoice limits. Run no paid batch until its exact scope
and total ceiling have been established. The exhausted 12-attempt development
smoke ceiling cannot fund this future evaluation.

## Review output

Publish aggregate scores with inspected failure examples, source/prompt revisions,
coverage and human grading notes. Preserve the failed examples when changing a
prompt or model. A later candidate can be compared on development data, followed
by a fresh locked holdout. The initial private prototype remains `accepted:false`
until an appropriate acceptance process has actually passed.
