# Week 7 agent evaluation preparation

Prepared 2026-10-13, Africa/Cairo. **No model collection has run.**

- [Protocol](PROTOCOL.md): fixed measurements, acceptance gates and later trial plan.
- [Source review](SOURCE_REVIEW.md): paper/section review, negative scope and limitations.
- [Development](development.json): eight cases using three new source papers.
- [Holdout](holdout.json): 24 evaluation-only cases using six different source papers.
- [Manifest](manifest.json): current v2 fingerprints and all 60 prior evaluation hashes.
- [Erratum](ERRATA.md): pre-run semantic novelty correction; exact first freeze retained in `frozen-v1/`.

Current manifest SHA-256:
`58b099eead49d8fd22d96be7a7ceba3142de9524ce6f80846e2e8ddee884b0db`.
Record this hash with any future collection. Do not tune using holdout outputs or
overwrite frozen labels after collection. This is a source-reviewed convenience
sample authored by Codex, not an independent or author-blind annotation study.

Offline source validation passed: 32 cases, 24 support-locator checks, five bounded
negative reviews, disjoint splits/prior support papers and 64 frozen/prior files.
The live source snapshot was read through existing paper-list and index text APIs;
58 papers, 2,775 current chunks, 1,221 v1 chunks and v2 alias are preserved. No
generation, ingestion, model/container/selector change or activation occurred.

```powershell
.venv-win/Scripts/python.exe -m src.commands.validate_agent_evaluation --snapshot tests/test_output/week7-source-review-20261013-01
.venv-win/Scripts/python.exe -m pytest tests/unit/test_agent_evaluation.py -q
```

Verification: **570 passed, zero skips**, including disposable PostgreSQL tests;
mypy for 77 source files, changed-file Ruff and diff checks passed. A novelty-guard
mutation was detected and the exact source bytes restored. Two existing dependency
deprecations remain. Source snapshots and test evidence stay locally ignored.

The [isolated collector](../../docs/week7-collector.md) is now implemented and
tested: 589 total tests pass, with 19 focused collector checks. The 192-job offline
holdout plan is ready. The guarded development pilot recorded **not started** at
1,638 MiB free RAM, below the unchanged 3,072 MiB admission requirement. Zero
inference, no temporary live app and no quality outputs. Frozen labels are intact.

Next: retry the isolated development pilot when actual headroom satisfies the
protocol, then review its outputs and collect
the 192-attempt holdout matrix and perform response-bound semantic review. Live
acceptance and resource/server sizing remain pending; missing backup hardware does
not block source work.

The [response-bound review/scoring tool](../../docs/week7-scoring.md) is now ready.
Full suite: 607 passed; mypy checks 80 source files. After the documented clean
WSL read-cache reclaim, retry 02 still recorded no start at 1,354.54 MiB host RAM.
Zero inference, no actual reviews/scores and no threshold changes. Frozen labels
and earlier evaluation fingerprints remain unchanged.
