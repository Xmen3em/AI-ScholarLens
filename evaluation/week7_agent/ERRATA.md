# Pre-run novelty correction

2026-10-13, Africa/Cairo. No model collection or semantic output scoring has run.

The first holdout's Cairo weather forecast request was too close in meaning to an
earlier saved out-of-domain forecast request. Exact normalized-query validation
passed, illustrating why the protocol also requires manual semantic novelty review.
Freeze v2 replaces this single case with an origami-instruction task. Counts,
expected out-of-scope/unsupported labels, source-paper split and scoring gates stay
the same. Development questions and all 60 prior evaluation files are unchanged.

`frozen-v1/` retains the exact original four documents/data files and manifest.
Original manifest SHA-256:
`793d66c6e5305844becbdb16d24589ae09e453c9aba82fdc8458ece4b19b955b`.
The current v2 manifest links to that hash. Source-review/protocol v2 notes record
the correction; no result was used to choose it. Collect future runs only against
the current v2 freeze and record its manifest hash in run metadata.
