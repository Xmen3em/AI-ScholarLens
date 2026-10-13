# Week 7 response-bound scoring and second pilot admission

2026-10-13, Africa/Cairo. Frozen v2 protocol/labels and all earlier evaluations
remain unchanged. Live agent inference has still not started.

## Offline review/scoring

`src.commands.score_agent` adds `template` and `score` operations. It reads collector
records and metadata, rechecks the pinned freeze and source snapshot, and audits
each successful response against the original request and preserved citations.
Templates leave reviewer, relevance, covered facts and rationale unset. They do
not infer relevance from quotations, marker validity or agent outcome labels.

Completed reviews bind to the complete response hash and each marker/quotation
hash, original question and required facts. Unknown/duplicate fact IDs, mismatched
fact assignments, irrelevant quotations credited with facts, missing rationale,
stale responses and unreviewed quotations fail closed. A source-valid substantive
negative answer still fails negative acceptance. Failed requests do not earn
abstention credit; errors and positive abstentions receive zero fact coverage.

The report separates case-averaged fact coverage, relevance denominators, correct
negative abstentions, false abstentions, failures, calls/embeddings and p50/p95
latency including failed attempts. It reports literal/paraphrase/numeric/two-paper
coverage strata and paired cell differences. A partial/subset holdout, missing
preservation checks, resource/integrity/work breach, hybrid fallback, incorrect
scope rejection, unsupported answer or regression cannot be accepted. Development
pilot scoring never becomes holdout acceptance. Observed sample acceptance is not
population quality, sustained-load sizing or deployment approval.

Commands for a later run containing actual responses:

```powershell
.venv-win/Scripts/python.exe -m src.commands.score_agent template --run tests/test_output/ACTUAL-RUN --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/ACTUAL-RUN/review-template.json
# Complete source-based judgments in a separate review file, then:
.venv-win/Scripts/python.exe -m src.commands.score_agent score --run tests/test_output/ACTUAL-RUN --snapshot tests/test_output/week7-source-review-20261013-01 --reviews tests/test_output/ACTUAL-RUN/reviews.json --output tests/test_output/ACTUAL-RUN/summary.json
```

Outputs must be new ignored files. A no-start run is rejected by the scorer;
no empty semantic report or fabricated judgments were written for the live pilot.

## Actual resource attempt

The user requested proceeding to the next pilot. Read-only model metadata showed
the original two installed model digests and no loaded model. Host free memory
was initially about 1,908 MiB, below the unchanged 3,072 MiB threshold.

The handoff's previously used Docker/WSL clean read-page-cache reclaim procedure
was inspected and applied once: `sync; echo 1 > /proc/sys/vm/drop_caches` inside
Docker Desktop's WSL distribution. This operation drops clean cached pages;
it does not configure future cache growth or delete files. See
[Docker's WSL guidance](https://www.docker.com/blog/docker-desktop-wsl--2-best-practices/)
and [Linux kernel documentation](https://docs.kernel.org/admin-guide/sysctl/vm.html#drop-caches).
No persistent memory settings, services, user applications or models changed.

WSL cached memory fell from 2,589,540 KiB to 773,596 KiB and guest free memory
rose from 2,586,844 KiB to 4,522,056 KiB. This did not produce enough Windows
host headroom. Guest free memory was not substituted for the frozen host-RAM
criterion. After offline work and a fresh corpus/model check, pilot retry 02
measured **1,354.54 MiB** available on the host, requiring **3,072 MiB**.

Result: **not_started / insufficient_memory**, zero inference requests, no live
evaluation server, no response records and no quality judgment. Evidence remains
in `tests/test_output/week7-development-pilot-20261013-02/metadata.json`.
The source/corpus/index/model identities matched and the frozen threshold was
preserved. All original container IDs/images/states were checked unchanged;
before/after Ollama metadata showed no model loaded. Recovery bundle untouched.

## Verification and continuation

**607 tests passed, zero skips**, including disposable PostgreSQL tests. Mypy
checks **80 source files**; changed-file Ruff/diff pass. **18 scoring tests** cover
unset templates, stale/mismatched reviews, corrupted records/sources, correct
failure denominators, incomplete matrices, full synthetic observed-gate acceptance,
coverage regression and substantive negative rejection. A stale-response guard
mutation was detected and exact source restored. Synthetic tests are not live
quality results. Two existing dependency deprecations remain.

The active API, key, quotas, selectors, corpus/indexes, models, runtime/rollback
containers and prior evaluation data remain intact. Source changes are uncommitted,
agent defaults remain disabled; no deployment/push/merge occurred. Next run the
guarded development pilot only when measured host headroom satisfies the protocol,
then source-review its responses using the new tool before the full holdout.
The research interface and server preparation remain later roadmap work; missing
backup hardware still does not block source implementation.
