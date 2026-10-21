# paper-evidence: claims that can be inspected

Status: extension spec, 21 October 2026. Inherits [shared rules](researcher-app.md).
Depends on paper-content; provides selected evidence/facts to tutor, visuals
and research. It does not import or trust their generated output as a source.

## Objective and baseline

Make each paper-specific explanation traceable to the right version and preserve
the meaning of a result. Existing snippets use stable block/snippet IDs and
server-copied quotations; selection is bounded and partly lexical. An observed
wrong best-result claim passed review. Exact copied numbers alone are insufficient.

## Provider contracts

`EvidenceRef`: paper/version, source hash/revision, block/snippet or region ID,
page, canonical range and origin. IDs are unique within this complete source
identity; `p4b0` alone is not a global ID. Resolve quotes server-side.

`EvidenceBundle`: query/action, selected refs, bounded full relevant context,
coverage/omissions, retrieval revision and optional unresolved evidence needs.
Record selection separately from extraction coverage. Missing selection does not
mean the PDF itself was only partially extracted.

`EvidenceFact`: reviewed statement, refs, origin and verification status; align
with the [visual fact contract](learning-visuals.md). `NumericClaim` refers to
verified cells plus metric/unit/dataset/split/setting. A comparison also binds
the compared method/cell set and direction of the metric. The application can
check values/arithmetic; semantic entailment still needs qualified review.

## Retrieval and claim validation

Build a small bilingual question→relevant-region development set before choosing
embeddings/reranking. Compare current selection, deterministic query aliases and
a separately budgeted rewrite/reranker on the same cases. Preserve small-device
operation; a new vector service is not a requirement for the first release.

Check source identity, existing IDs, quote ranges, compatible units/splits and
all compared values before rendering. Claims like "best" require the relevant
comparison set, not one matching number. Reject unsupported causal/training
edges and token/paragraph substitutions. General background and teaching examples
must be labeled and must not hide paper-specific claims.

## Implementation and checks

Existing: `evidence.py`, `service.py` selection and `tutor.py` validation/review.
Proposed: `claims.py`, retrieval fixture under `evaluation/paper_learning/` and
focused claim tests. Keep strict models/finite errors and small typed functions;
move responsibilities incrementally instead of growing the main service.

```powershell
.venv-win/Scripts/python.exe -m pytest tests/unit/test_study_tutor.py tests/unit/test_study_feedback.py tests/unit/test_study_service.py -q -o cache_dir=tests/test_output/study-pytest --basetemp tests/test_output/evidence-contract
```

Use real manifests/quote copying with stubbed model transport. Add tests for
equal/reversed metrics, incompatible splits, missing competing rows, wrong
source hashes and adversarial instructions. Lint/type commands are inherited.

## Acceptance

PE-1: Wrong/cross-paper refs, altered quotes and unsupported numeric comparisons
cannot become accepted paper claims. Original quotations remain inspectable.

PE-2: Fixed RAG negatives reject document-encoder updates, paragraph/token
confusion and the unsupported best-result statement; positive fixtures retain
the qualified meaning rather than rejecting all useful answers.

PE-3: Bilingual retrieval reports supporting-region recall and failure categories
on development plus fresh holdout. Release thresholds come from the shared
rubric; citation existence is not reported as entailment accuracy.

Open choice: retrieval method after measured comparison; no new model/database
is preselected. Missing structured tables remain an explicit content dependency.
