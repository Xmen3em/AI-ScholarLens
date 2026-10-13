# First live HF/Groq qualification result

The user explicitly approved the one-case public-paper BM25/JSON pilot with
`openai/gpt-oss-120b:groq` through `https://router.huggingface.co/v1/`, capped at
13 outbound attempts. Earlier attempts made no HF calls because host RAM failed
admission. Retry04 on 2026-10-13 passed admission with1525.93MiB recorded before
qualification, above the unchanged1024MiB requirement. No additional cache
reclaim, app closing, container stop or resource-policy change occurred.

## Observed result

The public router catalog advertised Groq live with structured output and tools.
Two paid **synthetic** calls returned completed responses with known usage:

| Qualification | Structured schema | Expected decision | Client duration | Input/output tokens | Minimum host free RAM |
|---|---|---|---|---|---|
| Scope | Passed | Passed | 836.29 ms | 130 / 31 | 1513.46 MiB |
| Relevance | Passed | Failed | 625.14 ms | 166 / 50 | 1512.21 MiB |

The original 30-ID selector diagnostic rejected locally with zero outbound work.
The relevance call returned schema-valid JSON, but its parsed object differed
from the frozen expected `{"relevant_markers":["[1.1]"]}`. The qualifier raised
`ValueError` at that expected-answer comparison and stopped. This was not a
provider HTTP error, native schema violation, timeout, unknown-usage event or
memory failure. The returned decision text was deliberately not retained; its
exact differing value cannot be reconstructed from the metadata. Empty, differently
formatted or duplicate marker lists in the new tests are **synthetic examples**,
not claims about the observed response.

No retry/failover/downgrade occurred. Rewrite and selector qualification calls
did not run, the temporary application never started, and both planned paper
jobs remained uncollected. **No frozen paper question or corpus passage was sent
for inference**; only the two synthetic prompts were sent. No controller text,
reasoning or provider response body was printed or persisted.

Total reported usage:296 input/81 output tokens, including28 reported reasoning
tokens within output usage. The dated frozen0.15/0.75USD-per-million rates yield
**$0.00010515 known-usage estimated cost**, with zero unknown-usage attempts.
This is not an invoice or a credit-balance check. The calls establish successful
authenticated HF/Groq connectivity and limited schema behavior, not complete
qualification, application latency, task quality, tool capability or deployment
readiness. The two timings are synthetic-call observations, not answer benchmarks.

## Gates and regression verification

The offline hosted scorer rejects development/holdout acceptance: qualification
failed, the matrix is incomplete and collection did not reach the required
`collected` completion status. Its `hosted_preservation_incomplete` gate also
requires that status; it does **not** indicate changed protected data here.
All four saved preservation booleans are true. The empty review template contains
no invented semantic judgments or responses.

Three new isolated regression cases prove that schema-valid wrong decisions
stop qualification after two synthetic calls. Removing the expected-decision
comparison makes all three fail; exact source bytes were restored. **741 tests
passed, zero skips**, including disposable PostgreSQL; changed-test Ruff and diff
checks pass. No application source changed, so the prior mypy88-file check remains
applicable. All162 pre-existing protected fingerprints match, both frozen
protocols verify and the local validator rechecks64 frozen/prior evaluation files.
All15 original container IDs/images/states match,5 running, after disposable
test resources are removed. Corpus/model fingerprints match in pre/post collection
and the frozen recovery manifest matches its pinned digest.

Evidence, retained locally in ignored output directories:

- `tests/test_output/hf-development-pilot-20261013-04/`:metadata,qualification,
  empty records,completion and final audit.
- `tests/test_output/hf-pilot04-review-template-20261013-01.json` and
  `hf-pilot04-score-20261013-01.json`:empty reviews and rejected acceptance.
- `tests/test_output/hf-protocol-20261013-01/expected-decision-mutation.json`,
  `containers-pilot04-before/after.json`.
- `tests/test_output/hf-semantic-qualification-focused-20261013-01/` and
  `hf-qualification-full-20261013-01/`.

Defaults remain disabled; original Week6 API/key, selector guards/prompts, corpus,
indexes/models, old evaluations, runtime/rollback and recovery bundle remain
intact. No deployment,push,merge,data/model replacement or selector tuning.

## Next qualification revision

Preserve this rejected v1 trial and its frozen protocol. Audit the synthetic
fixture before treating this as a model-selection result. Its prose says
`Return relevant_markers containing only [1.1]`; the production controller sends
markers as quoted strings inside a JSON data object with `CONTROLLER_SYSTEM`.
An ambiguity in the synthetic request is a hypothesis, not a proven cause.

Prepare a separately versioned qualification fixture using the production
controller system/instruction/data shape and an explicit JSON marker example.
For example, ask which passages neural retrieval selects and supply marker
`"[1.1]"` with evidence that neural retrieval selects indexed passages. Keep the
same canonical schema and expected marker string. Freeze exact prompt/system/
schema/expected bytes in its own manifest before another paid trial; preserve
all original controller/selector prompts and guards. Add bounded mismatch
diagnostics such as expected-match and supplied-marker-membership booleans,
without recording raw decisions or reasoning.

The approved pilot has used2 of its13 outbound attempts. Any subsequent trial
within that authorization must enforce the **remaining11-attempt ceiling**
across new qualification and case work; a fresh directory must not silently
reset that allowance. No further call is made in this checkpoint. Do not collect
paper cases while qualification is rejected or choose a provider on holdout.
Complete reviewed development and a locked same-pair holdout remain pending;
then follow the research-interface/server roadmap. Missing backup hardware does
not block implementation.
