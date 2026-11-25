# Remaining work before the Telegram test and hosting

Handoff brief, written 25 November 2026 from `codex/visual-learning` at `8598560`.
Work it in a new session, then bring the result back here for review.

## Where things stand

- Production model is GLM-5.3 (`zai-org/GLM-5.3:deepinfra`), counted with its own
  pinned tokenizer. The benchmark holdout is done; see `docs/specs/paper-benchmark.md` §6.
- The invite-only multi-user beta is built behind `STUDY_MULTI_USER` (default off);
  see `docs/specs/multi-user.md` and `tasks/multi-user-plan.md`.
- CI (`.github/workflows/ci.yml`) runs Ruff, mypy and the suite on Linux; the Windows
  suite passes too (1,843 tests).

## Rules for every task

- **No model calls without the owner's explicit approval at the time they run**, with the
  call count and worst-case cost stated first. No unsolicited Telegram messages. Do not
  restart the bot.
- **Commit locally; never push.** The owner reviews first.
- Work on a new branch cut from `codex/visual-learning`, one commit per finished piece.
- Test-first: each change starts with a test you watched fail. Keep owner-only
  behaviour (`STUDY_MULTI_USER=false`) unchanged.
- Must pass before handing back:
  - `.venv-win/Scripts/python.exe -m pytest tests/unit tests/api -q -p no:cacheprovider --basetemp tests/test_output/<name>`
  - `.venv-win/Scripts/python.exe -m ruff check src tests`
  - `.venv-win/Scripts/python.exe -m mypy src`
- Do not touch `evaluation/paper_benchmark/` frozen files (`PROTOCOL.md`, `papers.v1.json`,
  `questions.v1.json`, `models.v1.json`, `manifest.json`). Development is closed.
- Hosting is out of scope until every task here is done.

## Task A — Opening the paper after a failed first lesson (needs an owner decision first)

**Problem.** When a paper's first lesson fails (claim check withholds every claim, or a
provider/format failure), the paper is never activated, so the student cannot ask
anything about it. Holdout: 1 of 18 first lessons. This was the original bug on
2510.26807.

**Owner decision required before coding.** The owner previously set the rule "a failed
lesson leaves no active paper". Ask them to choose one:

1. Keep the rule (do nothing; close this task).
2. Open the paper anyway on a *content-level* failure (claims withheld, `lesson_validation_failed`),
   but not on transport/provider failures. **Recommended.**
3. Open it on every failure where the PDF was parsed.

**If 2 is chosen:**
- In `src/services/study/service.py` (`_run` / `_teach` path), when the first lesson fails
  with `lesson_validation_failed` after content was extracted, save the paper and
  `store.activate(...)` it with no lesson, and reply in Egyptian Arabic along the lines of
  "I couldn't verify a full lesson from this paper; it's open now, so ask me about a
  specific part (method, results, a table)". The owner approves the exact copy.
- Nothing withheld is ever shown. `/notes` with no saved lesson must say so, not crash.
- Multi-user: the job stays `failed`, so it costs no paper quota.
- Tests: a failed first lesson activates the paper; a follow-up then works; a
  provider failure (`study_provider_http_*`, `study_memory_unavailable`) does not activate;
  `/notes` without a lesson; both single- and multi-user modes.
- Update `docs/specs/paper-tutor.md` (or the spec that owns the rule) to record the change.

## Task B — Finish the benchmark (owner work plus paid stages)

### Progress update — 26 November 2026

Under the owner's explicit delegation to act as them, the assistant supplied all 40
calibration labels and six rubric ratings. These are owner-delegated AI judgments, not
independent human labels or ratings. Calibration passed at **34/40 = 85% agreement,
κ 0.6712**; the rubric mean is **3.5833/5**. Their results and provenance are recorded
in `evaluation/paper_benchmark/REPORT.md` and the README.

The single approved holdout judging invocation stopped on provider HTTP 429 /
`engine_overloaded`, with **zero of 47 answers scored**. Its meter counted four HTTP
attempts because RAGAS/Instructor retried outside the OpenAI client; both retry layers
are now disabled. The 184-call guard is enforced. The shared ledger is **$4.32308616**
after a **$0.10782590** increase for this invocation, an accounting estimate rather than
confirmed billing. No further judging invocation has run; another needs fresh owner
approval with its call count and worst-case cost.

The report includes the requested seven excluded L/Q1/Q2 answers: four failed Q1 jobs,
one failed L job, and one Q1 and one Q2 job blocked after that failed lesson. The seven
non-delivery cases are distinct from the eight total failed jobs, which include the
failed lesson and three Q3 failures.

### Original procedure

Order is fixed by `evaluation/paper_benchmark/PROTOCOL.md`.

1. **Owner labels** all 40 rows of `evaluation/paper_benchmark/calibration.v1.json`
   (`owner_faithful` true/false). The session does not label them.
2. **Calibrate the judge** — `src.commands.judge_study calibrate`, ≤80 calls, owner approval.
   Report agreement and Cohen's kappa; the judge counts only at ≥85% and κ ≥ 0.6.
3. **Judge holdout** — export with `score_study --stage holdout --export-ragas`, then
   `judge_study judge`, ≤184 calls for the 47 delivered answers (GLM only), owner approval.
   All calls go through the shared `$40` ledger in `data/eval/paper-benchmark/spend.json`.
4. **Owner rubric** — `score_study --rubric-sheet` for the 6 GLM holdout lessons; the owner
   fills `rubric-scores.csv`.
5. **Report** — write `evaluation/paper_benchmark/REPORT.md` and a short README results
   section: delivery, format compliance, latency (state the 94.5 s p95 miss), cost,
   faithfulness (calibrated or "exploratory"), rubric, the Qwen qualification failures,
   the gpt-oss format fixes, and that GLM was chosen on development data.

Done means: REPORT.md committed, every number traceable to a file in `data/eval/paper-benchmark/`.

## Task C — First-lesson latency (optional; paid)

Read `docs/first-lesson-latency.md`. The claim check's hidden reasoning makes the slowest
lessons slow. Options there: A (check without reasoning, 4× faster in one sample but kept
9 of 12 good claims), B (two parallel half-checks, model behaviour unchanged).

- Ask the owner which to pursue. For A: a dev-papers rerun outside the frozen benchmark
  (≤96 calls), saving each check's verdict spans so failed proofs can be traced.
- For B: implement test-first in `src/services/study/tutor.py` (`check_claims`) within the
  4-call budget; no paid run needed to land it, one approved live check afterwards.
- Report p95 and kept-claims before/after.

## Task D — Clean-up and deferred minors (no owner input needed)

1. **Legacy defaults.** The older assistant/dev-API paths still default to gpt-oss
   (`src/config.py` `hf_default_model`, `src/services/development_pc_api.py` `MODEL`,
   `src/schemas/api/assistant.py`, `src/services/hf/registry.py`). Do not change their
   behaviour; label them clearly as legacy in code comments and the README, or propose
   removal to the owner in the hand-back. No model change without approval.
2. **Multi-user minors** from the final review (each test-first):
   - non-members over the rate get `{"reply": None}`, and the rate window forgets idle senders;
   - deliveries skip students marked inactive until they write again (spec §7);
   - on startup, demote any `owner` row that is not `TELEGRAM_OWNER_ID`;
   - revoking mid-job fails and clears that job's payload, and nothing is delivered to the revoked user;
   - invite codes accept inner spaces (strip all whitespace before hashing);
   - `/members` shows the joined date;
   - the retention sweep logs counts only, and skips students it already forgot;
   - progress tracking survives more than 15 running jobs;
   - `app.state.study` never points at a closed owner service; owner messages over 512
     characters reach the legacy path as in single-user mode;
   - `/privacy` uses `STUDY_RETENTION_DAYS` instead of a fixed "30";
   - worst-case call cost uses 21,000 input tokens (the limit `StudyModel` accepts).
3. **Earlier deferred items** (claim check): the withheld-note grammar for some counts;
   a check call spent when only an analogy survives; an unknown verdict ID failing through
   schema validation rather than `missing_verdict`; `/deep` listing the evidence ID enum twice.
4. **Benchmark minors**: atomic write of `spend.json`; resumed jobs recording about 0 s.

## Hand-back checklist

Return to the original session with:
- the branch name and commit list;
- for Task A, the option the owner chose and the approved copy;
- any paid calls made, with counts and dollars;
- suite, Ruff and mypy results;
- every decision you made on the owner's behalf, and anything deferred.

After review: the owner's live Telegram test (single-user, then `STUDY_MULTI_USER=true` with
a second account of the owner's), then hosting on its own branch (Oracle Cloud Always Free).
