# Paper Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build everything the multi-paper benchmark and model bake-off need, offline and tested, so that each owner-approved stage is one command.

**Architecture:** A frozen `ModelProfile` makes `StudyModel` model-agnostic while keeping today's request byte-identical. Offline builders freeze the paper and question manifests. A runner drives the real `StudyService` per model into its own store, under call, price and memory ceilings. A scorer turns runs into metrics and a decision, and a RAGAS judge (imported lazily, run from `.venv-eval`) adds calibrated faithfulness scores.

**Tech Stack:** Python 3.12, Pydantic v2, httpx, pytest + anyio, Ruff, mypy; RAGAS 0.4.3 in a separate venv; HF router (OpenAI-compatible).

**Spec:** [docs/specs/paper-benchmark.md](../docs/specs/paper-benchmark.md)

## Global Constraints

- No model inference in Tasks 1–8. Public arXiv metadata and PDF downloads are allowed (Tasks 3–4); every model call happens only in the owner stages at the end, each with the owner's approval at the time.
- No Telegram messages; never touch `data/study/sessions.sqlite3`. Benchmark state lives under ignored `data/eval/paper-benchmark/`.
- With the default profile, production requests are byte-identical to today's (BM-2), and the full existing suite passes unchanged.
- Ceilings: price $40 total across all stages; calls per stage as in the spec §4 table (qualification amended below); free memory ≥ 1,024 MiB before any stage.
- Holdout runs once, after development is closed; nothing changes after holdout starts.
- Every published file carries paper IDs, questions, short reference quotes and aggregates — never full paper text.
- Write files with LF (`newline="\n"`). Heredocs and Edit collapse `\u`/`\n` escapes: build such strings with `chr()` in Python scripts.
- Gates per task: Ruff, mypy, and the task's tests; full suite at Tasks 2, 6 and 8.

## Rulings made while planning (spec amendments, applied in Task 5)

- **AI scope.** The intake accepts only papers carrying an `AI_CATEGORY_ALLOWLIST` category (`src/policies/ai_scope.py`). Every benchmark paper must be cross-listed in one, for example ML applied to biology. Otherwise, physics, biology and economics papers would fail with `outside_ai_scope` and measure nothing. The cost if wrong: the fields are "ML applied to X", not pure X. That matches the product's scope.
- **Qualification ceiling** is 4 calls per non-baseline model (12), not 2. One first lesson uses 2 calls; if the provider rejects a request option (HTTP 400/422), there is one retry with `request_options = {}`. The cost if wrong: 6 extra calls, about $0.10.
- **License exception.** If 2510.26807 is not CC-licensed, it stays in development with `"publish": false`. Its questions then live in ignored `data/eval/paper-benchmark/private-questions.json`, and only aggregates mention it.
- **Judge location.** The judge lives in `src/commands/judge_study.py`, not `evaluation/…`, with `ragas` imported only inside `build_metrics`. Its pure functions are then tested in the main suite, and the bot still never imports RAGAS.
- **Lesson capture.** `StudyService` gets an optional `observer`. Production passes none, so job results and the local API stay unchanged.

## Review Focus

1. A thinking model spends `max_tokens` on reasoning and returns `finish_reason="length"`. Expected: a format failure with diagnostic `incomplete_output`, counted and not retried (Task 2).
2. A provider rejects `reasoning_effort` with HTTP 400. Expected: qualification retries once with `{}` and freezes whichever passed (Task 6).
3. The runner dies mid-job, leaving an attempt reserved. Expected: on resume the job is marked unknown and not repeated, and its calls still count against the ceilings (Task 6).
4. A question text parses as an arXiv ID, a URL or a slash command, so the service treats it as a new paper. Expected: the validator rejects it (Task 4).
5. A call fails with no `usage`. Expected: the spend ledger charges that call's maximum possible cost, never zero (Task 6).

---

### Task 1: Model profiles

**Files:**
- Create: `src/services/study/models.py`
- Modify: `src/services/study/tutor.py` (`MODEL`, `StudyModel.__init__`, `StudyModel.complete`)
- Test: `tests/unit/test_study_models.py`

**Interfaces:**
- Produces:
  - `ModelProfile` (frozen dataclass): `name: str, route: str, input_estimate: Literal["gpt_oss_tokenizer", "utf8_bytes_div_3"], request_options: dict[str, object], price_in_usd_per_m: float, price_out_usd_per_m: float, priced_on: str`.
  - `DEFAULT_PROFILE = ModelProfile("baseline", "openai/gpt-oss-120b:cerebras", "gpt_oss_tokenizer", {"reasoning_effort": "low"}, 0.35, 0.75, "2026-11-03")`.
  - `estimate_input(profile, serialized: str) -> int`.
  - `call_cost_usd(profile, usage: dict | None, *, estimate: int, max_tokens: int = 3000) -> float`: with `usage`, it uses the real tokens; without it, `estimate` in and `max_tokens` out.
  - `load_profiles(path: Path) -> dict[str, ModelProfile]`.
  - `StudyModel(..., counter=None, profile=DEFAULT_PROFILE)`.
  - `tutor.MODEL == DEFAULT_PROFILE.route`.

- [ ] **Step 1: Write the failing tests**

```python
def test_default_profile_request_is_byte_identical(tmp_path):
    # Capture the request a fixed lesson call sends (MockTransport, 503 response) and compare it
    # with the frozen string produced by today's code, saved in the test as EXPECTED_BODY
    # (generate it once from HEAD before changing tutor.py).
    assert sent_body == EXPECTED_BODY

def test_payload_key_order_keeps_options_before_stream(tmp_path):
    profile = replace(DEFAULT_PROFILE, request_options={})
    assert list(sent(profile)) == ["model", "messages", "temperature", "max_tokens", "stream", "response_format"]

def test_byte_estimate_refuses_what_the_tokenizer_refuses():
    for text in (ARABIC_25K_CHARS, ENGLISH_90K_CHARS):
        assert estimate_input(BYTES, text) >= count_input_tokens(text)

def test_profile_route_is_recorded_on_attempts(tmp_path):
    # Non-default profile; MockTransport 503; store.attempts(job)[0]["model"] == "Qwen/Qwen3.8-27B:deepinfra"

def test_cost_without_usage_charges_the_maximum():
    assert call_cost_usd(P, None, estimate=10_000) == 10_000 * P.price_in_usd_per_m / 1e6 + 3000 * P.price_out_usd_per_m / 1e6
```

- [ ] **Step 2: Run them, expect FAIL** — `pytest tests/unit/test_study_models.py -v` → ImportError on `src.services.study.models`.
- [ ] **Step 3: Implement.**
  - The payload is `{"model", "messages", "temperature", "max_tokens", **request_options, "stream": False}`, then `response_format`/`tools` as today.
  - `counter=None` selects by `input_estimate`; an explicit `counter` still wins, so existing tests keep working.
  - `reserve_attempt` and `emit_event` use `profile.route`.
  - `utf8_bytes_div_3` is `ceil(len(serialized.encode()) / 3)`.
- [ ] **Step 4: Run** `pytest tests/unit/test_study_models.py tests/unit/test_study_tutor.py -q`. Expect: PASS.
- [ ] **Step 5: Commit** `feat: make the study model a frozen profile`.

### Task 2: Failure diagnostics and lesson observer

**Files:**
- Modify: `src/services/study/tutor.py` (the `except Exception` in `complete`), `src/services/study/failures.py`, `src/services/study/service.py` (`__init__`, `_teach`)
- Test: `tests/unit/test_study_tutor.py`, `tests/unit/test_study_service.py`

**Interfaces:**
- Produces:
  - `SAFE_DIAGNOSTICS` gains `incomplete_output, invalid_usage, invalid_choices, invalid_message, invalid_tools, invalid_output`.
  - `StudyService(..., observer: Callable[[str, Lesson, list[dict]], None] | None = None)`. The observer is called after `accept_draft` with `(job_id, lesson, evidence_catalog(selected))`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_truncated_output_keeps_its_diagnostic(tmp_path):
    # MockTransport returns a valid body with finish_reason "length"
    with pytest.raises(TutorError) as caught: ...
    assert str(caught.value) == "study_response_invalid_or_unavailable"
    assert caught.value.diagnostic == "incomplete_output"

async def test_observer_sees_the_accepted_lesson_and_the_writer_catalog(tmp_path):
    seen = []
    # existing honest Model stub; first lesson for the fixture paper
    assert seen[0][1].sections and seen[0][2][0]["id"].endswith("s0")
    assert "lesson" not in store.get_job(job_id)["result"]
```

- [ ] **Step 2: Run, expect FAIL**: the diagnostic is `ValueError`, and `observer` is an unexpected keyword.
- [ ] **Step 3: Implement.** Map a `ValueError` whose message is in the new set to that diagnostic, `JSONDecodeError` and `ValidationError` to their type names, and anything else to `None`.
- [ ] **Step 4: Run the full suite**, `pytest -q -p no:cacheprovider > <workspace>/t2.log`. Expect: everything passes (1,647 + new).
- [ ] **Step 5: Commit** `feat: keep transport diagnostics and expose accepted lessons to an observer`.

### Task 3: Paper manifest

**Files:**
- Create: `src/commands/build_benchmark.py`, `evaluation/paper_benchmark/candidates.v1.json`, `evaluation/paper_benchmark/papers.v1.json`
- Test: `tests/unit/test_paper_benchmark.py`

**Interfaces:**
- Produces:
  - `FIELDS = ("ml_nlp", "medicine", "physics", "biology", "economics", "systems")`.
  - `ALLOWED_LICENSES` = the arXiv URLs for CC BY 4.0, CC BY-SA 4.0 and CC0 1.0.
  - `parse_license(oai_xml: bytes) -> str | None`.
  - `admit(candidate: dict, content: PaperContent, license: str | None) -> dict` returns a manifest row or raises `ValueError(reason)`, with reason in `{"license", "pages", "no_text", "outside_ai_scope"}`.
  - `check_manifest(manifest: dict) -> None` raises on any rule.
  - CLI: `python -m src.commands.build_benchmark papers [--execute]`. It downloads through `ArxivIntake` + `PaperContentService(Path("data/eval/paper-benchmark/sources"))`, caches `content/<id>.json`, and writes `papers.v1.json`.
- Manifest row: `{"id": "2510.26807v1", "field", "split": "dev"|"holdout", "license", "publish": bool, "categories", "pages", "blocks", "sha256", "parser_revision", "features": ["table_result"|"equation_method"]}`.
- License source: OAI-PMH `https://oaipmh.arxiv.org/oai?verb=GetRecord&identifier=oai:arXiv.org:<id without version>&metadataPrefix=arXiv`, `<license>` element. Use the same 3-second spacing as the intake.

- [ ] **Step 1: Write the failing tests**

```python
def test_license_is_read_from_oai_record():  # fixture XML with <license>…by/4.0/</license>
def test_admit_rejects_unlicensed_long_textless_and_out_of_scope(): # each reason, one case
def test_manifest_has_five_per_field_and_a_2_3_split():
    check_manifest(load("evaluation/paper_benchmark/papers.v1.json"))
    # inside check_manifest: 30 rows, 5 per field, dev == 12 (2 per field), holdout == 18,
    # 2005.11401 absent, 2510.26807 in medicine/dev, each field has table_result and equation_method,
    # publish == (license in ALLOWED_LICENSES), every row has an allowlisted category
def test_cli_without_execute_makes_no_request(monkeypatch)
```

- [ ] **Step 2: Run, expect FAIL** (missing module and manifest).
- [ ] **Step 3: Implement the builder; then select papers.**
  - Search arXiv (API, cross-listed with an allowlisted category, 2025–2026, ≤40 pages) for about 8 candidates per field.
  - Record each in `candidates.v1.json` with field, the features you judged from the abstract and one skim of the PDF, and one line of reason.
  - Run `papers --execute`; it keeps the first 5 admitted per field and assigns `dev` to the first two in candidate order.
  - Recheck `features` against the cached text and edit the rows by hand where wrong.
- [ ] **Step 4: Run** `pytest tests/unit/test_paper_benchmark.py -v`. Expect: PASS. Also confirm `git check-ignore data/eval/paper-benchmark/content` succeeds.
- [ ] **Step 5: Commit** `feat: freeze a 30-paper benchmark manifest`.

### Task 4: Questions and references

**Files:**
- Create: `evaluation/paper_benchmark/questions.v1.json`
- Modify: `src/commands/build_benchmark.py` (`check_questions`, `spot_check_sheet`)
- Test: `tests/unit/test_paper_benchmark.py`

**Interfaces:**
- Consumes: `papers.v1.json` and cached `content/<id>.json` (Task 3).
- Produces:
  - `check_questions(questions: dict, papers: dict, contents: dict[str, PaperContent] | None) -> None`.
  - `spot_check_sheet(questions, papers, seed: int = 20261103) -> str`: Markdown with 20 questions, at least 3 per field.
  - CLI `python -m src.commands.build_benchmark questions` (validate only) and `… spot-check` (writes the ignored sheet).
- Shape: `{"version": "paper-benchmark-questions-v1", "papers": {"<id>": {"Q1": {"text", "facts": [{"fact", "block", "quote"}]}, "Q2": {…}, "Q3": {"text", "absent_terms": [..], "hits": 0}}}}`. 1–3 facts each; quote ≤ 300 chars.

- [ ] **Step 1: Write the failing tests**

```python
def test_every_quote_is_in_its_block_after_whitespace_normalization(): # temp content fixture
def test_q3_absent_terms_have_zero_hits(): # one term present → ValueError("q3_terms_present")
def test_question_text_cannot_open_a_new_paper():
    for text in ("2005.11401 ده بيقول إيه", "https://arxiv.org/abs/1", "/paper x"):
        with pytest.raises(ValueError, match="question_opens_paper"): check_questions(with_q1(text), ...)
def test_committed_questions_cover_every_published_paper():
    # structure always; quotes and Q3 hits only when content/ is present (skip otherwise, like the science fixtures)
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Author the 90 questions.**
  - Read each paper's cached blocks and write the questions in Egyptian Arabic. Q1 names its metric and setting.
  - Write the facts in English, each with a quote copied from the named block.
  - Rule for question text: `normalize_input` must not return kind `"id"`, and the text must not start with `/` or `http`.
  - Put non-published papers' questions in the ignored private file.
- [ ] **Step 4: Run** `pytest tests/unit/test_paper_benchmark.py -v` and `python -m src.commands.build_benchmark questions`. Expect: PASS and `questions ok: 90`.
- [ ] **Step 5: Commit** `feat: add benchmark questions with code-verified references`.

### Task 5: Protocol, model profiles file and freeze

**Files:**
- Create: `evaluation/paper_benchmark/PROTOCOL.md`, `evaluation/paper_benchmark/models.v1.json`
- Modify: `src/commands/build_benchmark.py` (`freeze`, `verify_frozen`), `docs/specs/paper-benchmark.md` (amendments above)
- Test: `tests/unit/test_paper_benchmark.py`

**Interfaces:**
- Produces:
  - `models.v1.json`: four profiles and a judge, in `load_profiles` format.
    - `qwen-27b`, `qwen-397b` and `control` start with `request_options = {"reasoning_effort": "low"}`.
    - The judge is `deepseek-ai/DeepSeek-V4-Pro:deepinfra`, at 1.30 / 2.60.
  - `freeze(root: Path) -> dict` writes `manifest.json` with SHA256 of `PROTOCOL.md`, `papers.v1.json`, `questions.v1.json` and `models.v1.json`.
  - `verify_frozen(root) -> str` returns the manifest hash or raises `ValueError("manifest_changed")`.
- PROTOCOL.md is spec §§4–6 restated as fixed measurement rules: stage table, metric definitions (below, verbatim), decision rule, and authorship statement.
- Metric definitions (shared with Task 7):
  - **delivered** = ready L/Q1/Q2 ÷ (3 × papers), with blocked counted as not delivered.
  - **format compliance** = 1 − format-failed calls ÷ calls made. A format failure is `study_response_invalid_or_unavailable`, `review_validation_failed`, or diagnostic `shape`.
  - **Q3 decline** = Q3 failed with `lesson_validation_failed` ÷ Q3 jobs that are neither blocked nor provider- or format-failed.
  - **latency** = job seconds of non-blocked jobs, as the median and the nearest-rank p95.
  - **unfaithful** = 1 − mean RAGAS faithfulness over judged answers.

- [ ] **Step 1: Failing tests**: `test_freeze_detects_any_changed_file` (temp root) and `test_models_file_loads_and_matches_spec_routes`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement**; amend the spec (Decisions, §1 scope rule, §4 qualification row 4/model (12), §7 judge path, license exception).
- [ ] **Step 4: Run the tests.** Expect: PASS. Do **not** run `freeze` yet; that happens in owner stage S1.
- [ ] **Step 5: Commit** `docs: add the benchmark protocol, model profiles and freeze check`.

### Task 6: Runner

**Files:**
- Create: `src/commands/evaluate_study.py`
- Test: `tests/unit/test_evaluate_study.py`

**Interfaces:**
- Consumes: `ModelProfile`, `load_profiles`, `call_cost_usd`, `estimate_input` (Task 1); `StudyService(observer=…)` (Task 2); `verify_frozen` (Task 5).
- Produces:
  - `plan_jobs(papers: dict, questions: dict, split: str) -> list[BenchJob]`, where `BenchJob(paper: str, kind: Literal["L","Q1","Q2","Q3"], text: str)`. Order: per paper L, Q1, Q2, Q3. L's text is the versioned ID.
  - `SpendLedger(path: Path, ceiling_usd: float = 40.0)` with `.spent() -> float`, `.charge(usd: float) -> None`, `.allows(next_max_usd: float) -> bool`.
  - `async run_stage(stage, profile, jobs, *, root: Path, service_factory, ledger: SpendLedger, call_ceiling: int, memory=host_memory_mib, clock=time.monotonic) -> list[dict]` appends rows to `root/<stage>-<profile.name>/jobs.jsonl` and returns them.
  - `async qualify(profile, job, **same) -> dict` returns `{"model", "passed": bool, "request_options"}` and writes it to `root/qualification.json`.
  - CLI: `python -m src.commands.evaluate_study --stage {qualify,dev,holdout} --model NAME [--execute] [--close-dev]`.
- Row: `{"paper", "job", "status": "ready"|"failed"|"blocked"|"unknown"|"stopped", "failure_code", "diagnostic", "stage", "review", "seconds", "calls": [{"purpose", "state", "usage", "cost_usd"}], "lesson", "contexts": [quote, …], "question"}`.
- Stage ceilings, per model: qualify 4; dev 96; holdout 144.

Refusals, each a test:
- no `--execute` → prints the plan (jobs, call ceiling, worst-case cost) and opens no client;
- manifest changed;
- memory < 1,024 MiB;
- holdout without `dev-closed.json`;
- a non-baseline model without `passed` in `qualification.json`;
- the ledger cannot afford the next call's worst case, computed as 20,000 input tokens plus 3,000 output tokens at the profile's prices. The run then stops and remaining rows are `stopped`;
- source SHA differs from the manifest → that paper's rows are `failed` with `failure_code = "source_changed"`.

- [ ] **Step 1: Write the failing tests**, with a stub intake/content (fixture PDF via `study_helpers.pdf_fixture`) and a stub model.

```python
async def test_failed_first_lesson_blocks_its_followups(tmp_path): # rows: L failed, Q1–Q3 blocked
async def test_resume_skips_finished_and_marks_interrupted_unknown(tmp_path):
    # first run killed after L reserved an attempt (store left "running"); second run: L "unknown", not resubmitted, calls counted
async def test_call_without_usage_is_charged_its_maximum(tmp_path)
async def test_price_ceiling_stops_before_the_call_that_could_exceed_it(tmp_path)
async def test_qualification_retries_once_without_options_after_http_400(tmp_path)
async def test_followups_carry_contexts_and_lesson_from_the_observer(tmp_path)
def test_cli_without_execute_opens_no_client(monkeypatch, capsys)
# plus one test per refusal listed above
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - The store is `StudyStore(root/<stage>-<model>/state.sqlite3, "paper-benchmark")`, with `set_total_ceiling(call_ceiling)` and `recover_interrupted()` at start.
  - Job intents are `bench:<stage>:<paper>:<kind>`, so `create_job` deduplicates.
  - The audit callback charges the ledger from `usage`. After each job, attempts the audit did not see are charged their maximum.
- [ ] **Step 4: Run** `pytest tests/unit/test_evaluate_study.py -v`, then the full suite. Expect: PASS.
- [ ] **Step 5: Commit** `feat: run benchmark stages under call, price and memory ceilings`.

### Task 7: Scorer, decision and exports

**Files:**
- Create: `src/commands/score_study.py`
- Test: `tests/unit/test_score_study.py`

**Interfaces:**
- Consumes: Task 6 rows; Task 5 metric definitions.
- Produces:
  - `nearest_rank(values: list[float], q: float) -> float`.
  - `model_metrics(rows: list[dict]) -> dict`, with keys `delivered, format_compliance, claims, kept, withheld (dict), q3_decline, q3_answered (list of paper ids), latency_median, latency_p95, cost_usd, cost_per_delivered, failures (code → count)`.
  - `decide(metrics: dict[str, dict], *, baseline: str = "baseline", judged: dict | None, owner_unfaithful: dict | None) -> dict` returns `{"choice", "eligible": [...], "reasons": {model: [str]}}`, per spec §6:
    - gates: compliance ≥ 0.95, p95 ≤ 90, unfaithful ≤ baseline + 0.02;
    - rank by delivered, factual, rubric, cost;
    - replace only with delivered +0.10 or factual +0.10.
  - `ragas_rows(rows, questions, model) -> list[dict]`, holdout ready L/Q1/Q2: `{"model", "paper", "job", "question", "answer"` (joined `paper`-kind section texts) `, "contexts", "reference"` (joined facts, or `None` for L) `}`.
  - `rubric_sheet(rows_by_model, papers, seed=20261103) -> tuple[str, dict]`: 6 holdout papers (one per field) × 4 models, shuffled, with codes and a private key.
  - CLI: `python -m src.commands.score_study --stage holdout [--export-ragas] [--rubric-sheet] [--rubric-scores CSV] [--judged JSONL]` writes `metrics.json` under the stage root.

- [ ] **Step 1: Failing tests**:
  - hand-computed metrics on a 2-paper stub run (one blocked, one Q3 decline, one format failure);
  - `nearest_rank([1..20], .95) == 19`;
  - decision cases: baseline kept when no challenger clears +0.10; challenger chosen; ineligible on p95; judge missing → owner_unfaithful used; both missing → the gate is reported as `"not_measured"` and blocks a switch;
  - the RAGAS export excludes withheld text and non-paper sections;
  - the rubric sheet hides model names, and its key maps every code.
- [ ] **Step 2: Run, expect FAIL.** **Step 3: Implement.** **Step 4: Run, PASS.**
- [ ] **Step 5: Commit** `feat: score benchmark runs and apply the decision rule`.

### Task 8: RAGAS judge and calibration

**Files:**
- Create: `src/commands/judge_study.py`, `requirements-eval.txt`
- Test: `tests/unit/test_judge_study.py`

**Interfaces:**
- Consumes: `ragas_rows` output (Task 7); judge profile from `models.v1.json`.
- Produces:
  - `score_rows(rows, metrics: dict[str, Callable[[dict], Awaitable[float]]]) -> list[dict]`: each row gains `faithfulness`, plus `factual_correctness` and `context_recall` when it has a reference.
  - `agreement(owner: list[bool], judge: list[bool]) -> dict` returns `{"agreement", "kappa"}`.
  - `calibrated(result) -> bool` (agreement ≥ 0.85 and κ ≥ 0.6).
  - `CallCounter(ceiling)` is an httpx request hook that raises when the ceiling is passed.
  - `build_metrics(profile, token, counter) -> dict` has the only `import ragas`. It builds Faithfulness, FactualCorrectness(mode="recall") and LLMContextRecall, using the HF router through an OpenAI-compatible client.
  - CLI: `python -m src.commands.judge_study {calibrate,judge} [--execute]`, run from `.venv-eval`.
- `calibration.v1.json` (Task 8 creates the 16 science-case rows; the owner adds 24 in S4): `[{"claim_ar", "quote_en", "owner_faithful": bool|null}]`.

- [ ] **Step 1: Failing tests**:
  - stubbed metrics on two canned rows write the expected keys;
  - L rows get only faithfulness;
  - the kappa hand example (owner `[T,T,F,F]` vs judge `[T,F,F,F]` → agreement 0.75, κ 0.5);
  - `CallCounter(2)` raises on the third request;
  - importing the module does not import `ragas` (`"ragas" not in sys.modules`).
- [ ] **Step 2: Run, expect FAIL.** **Step 3: Implement**.
  - Create `.venv-eval` with `py -3.12 -m venv .venv-eval`, then `.venv-eval/Scripts/pip install ragas==0.4.3 openai httpx`.
  - Pin the resolved versions from `pip freeze` into `requirements-eval.txt`.
  - Confirm that `build_metrics` constructs its objects against the installed 0.4.3 API with a dummy key and **no request**.
  - Make sure `.venv-eval` is gitignored.
- [ ] **Step 4: Run** the task's tests, the full suite, Ruff and mypy. Expect: all green.
- [ ] **Step 5: Commit** `feat: add a calibrated RAGAS judge in its own environment`.

---

## Owner stages (after Tasks 1–8; each one needs the owner's explicit approval at the time)

| Stage | Owner does | Command | Ceiling |
| --- | --- | --- | --- |
| S1 freeze | reviews the 20-question spot-check sheet | `build_benchmark freeze` | none |
| S2 qualify | approves | `evaluate_study --stage qualify --model {qwen-27b,qwen-397b,control} --execute` | 12 calls |
| S3 development | approves | `--stage dev --model <each> --execute`; fix only model-agnostic defects; at most one rerun; then `--close-dev` | 384 calls |
| S4 calibration | labels 24 dev claims plus the 16 science cases | `judge_study calibrate --execute` | ≤80 calls |
| S5 holdout | approves | `--stage holdout --model <each> --execute` | 576 calls |
| S6 judging | approves | `score_study --export-ragas`, then `judge_study judge --execute` | 864 calls |
| S7 rubric and report | rates 24 blind lessons | `score_study --rubric-scores … --judged …` → write `REPORT.md` and the README results section | none |

The $40 ledger spans S2–S6. Switching the production model afterwards is a separate change for the owner to approve.
