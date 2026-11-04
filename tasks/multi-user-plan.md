# Multi-user Beta Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open the Telegram tutor to an invite-only beta: per-student state, daily paper and question limits, a reserved global dollar ceiling, a 3-slot fair model pool, owner-only `/deep`, 30-day retention, all behind `STUDY_MULTI_USER` (default off).

**Architecture:** A new `AccessGate` (SQLite tables beside the study store) admits each request; a `ServiceRegistry` holds one `StudyService` per student over the existing owner-keyed `StudyStore`; a shared `ModelPool` hands out call slots in arrival order and one HTTP client. The bot routes by sender chat and passes `user_id` to the study API. Lesson, evidence and claim-check code is unchanged.

**Tech Stack:** Python 3.12, FastAPI, httpx, SQLite (WAL), pydantic-settings, `zoneinfo` + `tzdata` (in `uv.lock`), pytest (asyncio auto mode).

**Spec:** `docs/specs/multi-user.md`

## Global Constraints

- Default `STUDY_MULTI_USER=false` must reproduce today's owner-only behaviour; every existing test passes unchanged except where a task names the change.
- Settings and defaults (spec §8): `STUDY_DAILY_PAPERS=3`, `STUDY_DAILY_QUESTIONS=30`, `STUDY_DAILY_USD_CEILING=2.00`, `STUDY_PARALLEL_JOBS=3` (1–4), `STUDY_MESSAGES_PER_MINUTE=6`, `STUDY_RETENTION_DAYS=30`; out-of-range values refuse startup.
- A day is the calendar day in `Africa/Cairo`.
- Only delivered (`ready`) answers count against a student; the owner is exempt from counts but not from the dollar ceiling.
- Dollar cost per call is `call_cost_usd(DEFAULT_PROFILE, usage, estimate=WORST_INPUT_TOKENS)` with `WORST_INPUT_TOKENS = 20000`; a call with no usage costs its worst case.
- Message copy is exactly spec §5 (Egyptian Arabic), kept in one module.
- Invite codes: 10 characters from `ABCDEFGHJKMNPQRSTUVWXYZ23456789`, valid 7 days, stored only as SHA-256; input is trimmed and upper-cased before checking.
- Logs never contain message text, paper text, invite codes or usernames; a user appears as `StudyStore.fingerprint()`.
- No model calls and no real Telegram calls in tests. Test command for the whole suite: `.venv-win/Scripts/python.exe -m pytest tests/unit tests/api -q -p no:cacheprovider --basetemp tests/test_output/mu` (Linux CI: `uv run --frozen pytest ... --basetemp tests/test_output/ci`).
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A second message while the student's job runs: the service answers `BUSY`; the reservation taken for it must be released, and no quota changes. (Task 6)
2. A job admitted at 23:59 Cairo and delivered after midnight counts on its admission day, and the next day starts full. (Task 3)
3. Invite codes typed with spaces or lower case still work; a code used by one person cannot be used by a second. (Task 2)
4. A Telegram 403 for one student never blocks deliveries to the others in the same poll. (Task 7)
5. The owner's existing history (stored under `str(owner_id)`) is still there after enabling multi-user. (Task 6)

---

### Task 1: Settings and message copy

**Files:**
- Create: `src/services/study/access_text.py`
- Create: `src/services/study/access_settings.py`
- Test: `tests/unit/test_access_settings.py`

**Interfaces:**
- Produces: `class AccessSettings(DefaultSettings)` with `env_prefix="STUDY_"` and fields `multi_user: bool = False`, `daily_papers: int = 3 (1–50)`, `daily_questions: int = 30 (1–500)`, `daily_usd_ceiling: float = 2.00 (0.10–100)`, `parallel_jobs: int = 3 (1–4)`, `messages_per_minute: int = 6 (1–60)`, `retention_days: int = 30 (1–365)`.
- Produces in `access_text.py`: constants `NOT_MEMBER, BAD_CODE, WELCOME, USAGE, PAPERS_USED, QUESTIONS_USED, CEILING, TOO_FAST, QUEUED, DEEP_OWNER_ONLY, GROUP_CHAT, REVOKED, PRIVACY` (spec §5 text; `USAGE`, `PAPERS_USED`, `QUESTIONS_USED`, `QUEUED` are `str.format` templates with `{p}`, `{P}`, `{q}`, `{Q}`, `{n}`), and `STUDENT_HELP_LINES` listing `/usage`, `/privacy`, `/forget`; `OWNER_HELP_LINES` listing `/invite`, `/members`, `/revoke`, `/usage`.

- [ ] **Step 1: Write the failing tests**

```python
def test_defaults_match_the_spec(monkeypatch):
    s = AccessSettings(_env_file=None)
    assert (s.multi_user, s.daily_papers, s.daily_questions, s.daily_usd_ceiling, s.parallel_jobs,
            s.messages_per_minute, s.retention_days) == (False, 3, 30, 2.00, 3, 6, 30)

@pytest.mark.parametrize("name,value", [("PARALLEL_JOBS", "5"), ("PARALLEL_JOBS", "0"), ("DAILY_USD_CEILING", "0"),
                                        ("RETENTION_DAYS", "0"), ("DAILY_PAPERS", "-1")])
def test_out_of_range_settings_refuse(monkeypatch, name, value):
    monkeypatch.setenv("STUDY_" + name, value)
    with pytest.raises(ValidationError):
        AccessSettings(_env_file=None)

def test_message_templates_format():
    assert access_text.USAGE.format(p=2, P=3, q=24, Q=30).startswith("النهارده: فاضلك 2 من 3 ورقة")
    assert "إنت رقم 2" in access_text.QUEUED.format(n=2)
```

- [ ] **Step 2: Run — expect ImportError**

Run: `.venv-win/Scripts/python.exe -m pytest tests/unit/test_access_settings.py -q -p no:cacheprovider --basetemp tests/test_output/mu1`

- [ ] **Step 3: Implement both modules** (copy verbatim from spec §5, including `/privacy`).

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit** `feat: add multi-user settings and message copy`

---

### Task 2: AccessGate membership and invites

**Files:**
- Create: `src/services/study/access.py`
- Test: `tests/unit/test_access_gate.py`

**Interfaces:**
- Consumes: `AccessSettings`, `access_text` (Task 1).
- Produces: `class AccessGate(path: Path, settings: AccessSettings, owner_id: int, *, now: Callable[[], float] = time.time)`. On init it creates tables `members(user INTEGER PRIMARY KEY, role TEXT, joined REAL, last_active REAL, revoked INTEGER, inactive INTEGER)`, `invites(hash TEXT PRIMARY KEY, created REAL, expires REAL, used_by INTEGER)`, `notes(user INTEGER, day TEXT, kind TEXT, PRIMARY KEY(user, day, kind))` in the same SQLite file, with `PRAGMA journal_mode=WAL`, and inserts the owner as role `owner`.
- Methods: `create_invites(count: int) -> list[str]` (1–10); `redeem(user: int, code: str) -> bool`; `role(user: int) -> Literal["owner", "student"] | None` (None for non-members and revoked); `revoke(user: int) -> bool`; `touch(user: int) -> None` (sets `last_active`, clears `inactive`); `mark_inactive(user: int) -> None`; `is_inactive(user: int) -> bool`; `note_once(user: int, kind: str) -> bool` (True the first time per Cairo day); `members() -> list[dict]`; `cairo_day(ts: float | None = None) -> str` (`YYYY-MM-DD`).

- [ ] **Step 1: Write the failing tests** (clock injected; `CAIRO = ZoneInfo("Africa/Cairo")`)

```python
def test_owner_is_always_a_member(gate): assert gate.role(OWNER) == "owner"
def test_invite_codes_are_single_use_and_normalised(gate):
    [code] = gate.create_invites(1)
    assert len(code) == 10 and set(code) <= set("ABCDEFGHJKMNPQRSTUVWXYZ23456789")
    assert gate.redeem(111, "  " + code.lower() + " ") and gate.role(111) == "student"
    assert not gate.redeem(222, code) and gate.role(222) is None
def test_codes_expire_after_seven_days(gate, clock):
    [code] = gate.create_invites(1); clock.advance(7 * 86400 + 1)
    assert not gate.redeem(111, code)
def test_codes_are_stored_only_as_hashes(gate, db_path):
    [code] = gate.create_invites(1)
    assert code.encode() not in db_path.read_bytes()
def test_revoke_blocks_and_a_new_code_readmits(gate):
    [a, b] = gate.create_invites(2); gate.redeem(111, a)
    assert gate.revoke(111) and gate.role(111) is None and gate.redeem(111, b) and gate.role(111) == "student"
def test_owner_cannot_be_revoked(gate): assert not gate.revoke(OWNER) and gate.role(OWNER) == "owner"
def test_notes_are_sent_once_per_cairo_day(gate, clock):
    assert gate.note_once(999, "not_member") and not gate.note_once(999, "not_member")
    clock.set_cairo("2026-11-05 00:00:01"); assert gate.note_once(999, "not_member")
def test_invite_count_is_bounded(gate):
    with pytest.raises(ValueError): gate.create_invites(11)
```

- [ ] **Step 2: Run — expect ImportError**
- [ ] **Step 3: Implement** with `secrets.choice` for codes and `hashlib.sha256(code.encode()).hexdigest()`; every method is one `BEGIN IMMEDIATE` transaction (`sqlite3.connect(path, timeout=5)`).
- [ ] **Step 4: Run — expect PASS**
- [ ] **Step 5: Commit** `feat: add the access gate's membership and invites`

---

### Task 3: AccessGate limits, ledger and rate window

**Files:**
- Modify: `src/services/study/access.py`
- Test: `tests/unit/test_access_limits.py`

**Interfaces:**
- Consumes: Task 2's `AccessGate`; `call_cost_usd`, `DEFAULT_PROFILE` from `src/services/study/models.py`.
- Produces tables `usage_day(user INTEGER, day TEXT, papers INTEGER, questions INTEGER, usd REAL, PRIMARY KEY(user, day))` and `reservations(job TEXT PRIMARY KEY, user INTEGER, day TEXT, kind TEXT, reserved REAL)`, and an in-memory rate window per user.
- Methods:
  - `allow_message(user: int) -> bool` — False once more than `messages_per_minute` messages arrive within 60 s.
  - `admit(user: int, kind: Literal["paper", "question", "other"], job: str, max_calls: int) -> str | None` — returns None and records a reservation of `max_calls × worst_call_usd()`, or returns the refusal text (`PAPERS_USED`/`QUESTIONS_USED` formatted, or `CEILING`). Students are checked against counts for `paper`/`question`; `other` needs no count. Everyone is checked against `spent + reserved + this ≤ daily_usd_ceiling` for the reservation's Cairo day.
  - `charge(job: str, usd: float) -> None` — adds real cost to the job's user/day `usd` and lowers the reservation by the same amount (not below 0).
  - `settle(job: str, *, delivered_kind: Literal["paper", "question"] | None) -> None` — counts a delivered paper/question on the reservation's day (students only) and deletes the reservation.
  - `release(job: str) -> None` — deletes a reservation without charging (refused or `BUSY` submits).
  - `usage(user: int) -> dict` (`papers_left`, `questions_left`) and `owner_usage() -> dict` (`spent`, `reserved`, `ceiling`, `top`: up to five `{user, usd, papers, questions}`).
  - `worst_call_usd() -> float` — `call_cost_usd(DEFAULT_PROFILE, None, estimate=20000)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_only_delivered_answers_count(gate, student):
    assert gate.admit(student, "paper", "j1", 2) is None
    gate.settle("j1", delivered_kind=None)
    assert gate.usage(student)["papers_left"] == 3
def test_papers_run_out(gate, student):
    for i in range(3):
        assert gate.admit(student, "paper", f"j{i}", 2) is None; gate.settle(f"j{i}", delivered_kind="paper")
    assert gate.admit(student, "paper", "j9", 2) == access_text.PAPERS_USED.format(P=3)
def test_owner_is_exempt_from_counts_not_the_ceiling(gate, settings):
    ...  # owner admits >3 papers; with ceiling 0.10 the owner's second $0.06 reservation is refused with CEILING
def test_parallel_reservations_never_exceed_the_ceiling(gate_with_ceiling_0_15, students):
    refusals = [gate.admit(s, "question", f"j{s}", 2) for s in students[:3]]
    assert refusals.count(None) == 2 and refusals[2] == access_text.CEILING
def test_charge_replaces_the_reservation(gate, student):
    gate.admit(student, "question", "j1", 2); gate.charge("j1", 0.01)
    u = gate.owner_usage(); assert u["spent"] == pytest.approx(0.01) and u["reserved"] == pytest.approx(2 * gate.worst_call_usd() - 0.01)
def test_a_job_admitted_before_midnight_counts_that_day(gate, student, clock):
    clock.set_cairo("2026-11-04 23:59:00"); gate.admit(student, "paper", "j1", 2)
    clock.set_cairo("2026-11-05 00:01:00"); gate.settle("j1", delivered_kind="paper")
    assert gate.usage(student)["papers_left"] == 3
def test_release_frees_a_reservation(gate, student):
    gate.admit(student, "question", "j1", 2); gate.release("j1"); assert gate.owner_usage()["reserved"] == 0
def test_rate_window(gate, student, clock):
    assert all(gate.allow_message(student) for _ in range(6)) and not gate.allow_message(student)
    clock.advance(61); assert gate.allow_message(student)
```

- [ ] **Step 2: Run — expect AttributeError / FAIL**
- [ ] **Step 3: Implement** (all reservation arithmetic inside one transaction per call).
- [ ] **Step 4: Run — expect PASS**
- [ ] **Step 5: Commit** `feat: add daily limits and the reserved dollar ceiling`

---

### Task 4: ModelPool and StudyModel sharing

**Files:**
- Create: `src/services/study/pool.py`
- Modify: `src/services/study/tutor.py` (`StudyModel.__init__`, `StudyModel.complete`)
- Test: `tests/unit/test_model_pool.py`, extend `tests/unit/test_study_tutor.py`

**Interfaces:**
- Produces: `class ModelPool(token: SecretStr, slots: int)` with `client: httpx.AsyncClient` (the headers, timeout and transport flags `StudyModel` uses today; `max_connections=slots`), `slot(job: str) -> AsyncContextManager[None]` (FIFO: waiters are granted in arrival order), `position(job: str) -> int | None` (1-based place among waiters, None if running or unknown), `aclose()`.
- `StudyModel(..., pool: ModelPool | None = None)`: when `pool` is given it uses `pool.client` (not owned) and wraps the HTTP exchange in `async with pool.slot(job_id)` inside its existing per-instance lock. Without a pool, behaviour and payload are byte-identical to today (`test_study_models.py` still passes).

- [ ] **Step 1: Write the failing tests**

```python
async def test_at_most_n_calls_run_at_once(): ...   # 5 tasks, slots=3: peak concurrency == 3
async def test_waiters_are_served_in_arrival_order(): ...  # order of entry == order of arrival
async def test_position_counts_waiters_ahead(): ...  # with 3 running and j4, j5 waiting: position("j5") == 2, position("j1") is None
async def test_a_model_with_a_pool_shares_its_client(tmp_path):
    pool = ModelPool(SecretStr("x" * 40), 3)
    a, b = (StudyModel(SecretStr("x" * 40), store_for(tmp_path, n), pool=pool) for n in ("1", "2"))
    assert a.client is b.client is pool.client
```

- [ ] **Step 2: Run — expect ImportError**
- [ ] **Step 3: Implement** `slot` with a `collections.deque` of waiter futures and a running counter (not `asyncio.Semaphore`, which does not expose positions).
- [ ] **Step 4: Run — expect PASS**; also `tests/unit/test_study_tutor.py tests/unit/test_study_models.py`.
- [ ] **Step 5: Commit** `feat: share model calls through a fair 3-slot pool`

---

### Task 5: Store support across students

**Files:**
- Modify: `src/services/study/store.py`
- Test: extend `tests/unit/test_study_store.py`

**Interfaces:**
- Produces module functions in `store.py`: `recover_all_interrupted(path: Path) -> int` (the `recover_interrupted` statements for every owner; returns jobs changed); `pending_deliveries_all(path: Path, limit: int = 5) -> list[dict]` (each job dict plus `"owner"`, oldest first). Activity for retention lives in `AccessGate.members.last_active`, not here.
- `StudyStore.__init__` sets `PRAGMA journal_mode=WAL` once.

- [ ] **Step 1: Write the failing tests**

```python
def test_recovery_covers_every_owner(tmp_path): ...       # running jobs for owners "1" and "2" both become interrupted
def test_pending_deliveries_span_owners_oldest_first(tmp_path): ...  # rows carry owner; at most 5
def test_store_uses_wal(tmp_path):
    StudyStore(tmp_path / "s.sqlite3", "1")
    assert sqlite3.connect(tmp_path / "s.sqlite3").execute("PRAGMA journal_mode").fetchone()[0] == "wal"
```

- [ ] **Step 2–4: Run (FAIL) → implement → run (PASS)**, plus the whole of `tests/unit/test_study_store.py`.
- [ ] **Step 5: Commit** `feat: recover and deliver study jobs across students`

---

### Task 6: Service kind, registry and the multi-user API

**Files:**
- Modify: `src/services/study/service.py` (add `request_kind`; ready results carry `"kind"`)
- Create: `src/services/study/registry.py`
- Modify: `src/services/study/api.py`, `src/services/development_pc_api.py`
- Test: `tests/unit/test_study_registry.py`, extend `tests/unit/test_study_api.py`

**Interfaces:**
- Consumes: Tasks 1–5.
- `StudyService.request_kind(text: str) -> Literal["paper", "question", "other"]` — `paper` for an arXiv ID/URL, `/paper` with an ID, or `/choose N`; `question` when the text would be a follow-up on the active paper (the `_acknowledgement` rules); `other` for commands that never call the model and for title searches. Ready job results gain `"kind": "paper" | "question"` (from `state["followup"]`).
- `class ServiceRegistry(root: Path, pool: ModelPool, gate: AccessGate, intake, content, *, owner_id: int, research_python: Path | None, idle_seconds: float = 1800, now=time.monotonic)`: `service(user: int) -> StudyService` (lazy; owner gets `research_python`, students get None; each `StudyModel` gets `pool=pool` and an `audit` that calls `gate.charge(job, call_cost_usd(DEFAULT_PROFILE, usage, estimate=20000))`); `running() -> list[dict]` (`{"user", "id", "stage", "position"}`, where `stage` is `"queued"` while `pool.position(id)` is not None); `close_idle() -> None`; `sweep(retention_days: int) -> int` (forgets each non-owner member whose `last_active` is older than the cutoff); `aclose()`. When a job task finishes it calls `gate.settle(job, delivered_kind=result.get("kind") if status == "ready" else None)`; attempts still `unknown` at settle are charged `worst_call_usd()` each.
- API with `STUDY_MULTI_USER=true`:
  - `StudyMessage.user_id: int` (1 ≤ id < 2**52), required in multi-user mode, rejected (422) in single-user mode.
  - `POST /study/messages`: `gate.allow_message` → else `TOO_FAST`; `/start CODE`, `/invite [N]`, `/members`, `/revoke ID`, `/usage`, `/privacy`, `/help` handled before the service (owner commands only for `role == "owner"`; `/revoke ID` also runs `StudyStore(path, str(ID)).forget()`); non-members get `NOT_MEMBER` (or `REVOKED`) via `note_once`, else `{"reply": None}` (bot sends nothing); `/deep` from a student → `DEEP_OWNER_ONLY`; otherwise `kind = service.request_kind(text)`, `gate.admit(...)` then `service.submit(...)`; a submit returning no `job_id` (e.g. `BUSY`) calls `gate.release`. `gate.touch(user)` on every member message.
  - `POST /study/pending`: `{"jobs": [{"id", "status", "user"}], "running": registry.running()[:15]}`.
  - `POST /study/claim`: `DeliveryClaim` gains `user_id`; looks up the job in that user's store.
  - `POST /study/undeliverable` `{user_id}` → `gate.mark_inactive`.
  - No queued job is ever cancelled for the ceiling: an admitted job already holds its reservation, so spec §4's ceiling case only arises at admission.
- `create_development_app` builds the gate, pool and registry when `AccessSettings().multi_user`, runs `recover_all_interrupted`, then settles every reservation left open by a previous run (each attempt the job reserved charged `worst_call_usd()`, no quota), then `registry.sweep`, at startup, plus a 24 h sweep task; otherwise today's single-owner wiring, untouched.

- [ ] **Step 1: Write the failing tests** (registry with a mocked provider and `httpx.MockTransport`; API through `TestClient` with multi-user on)

```python
async def test_students_get_separate_papers_and_dialogue(registry): ...
async def test_a_busy_submit_releases_its_reservation(api, student): ...      # Review Focus 1
async def test_owner_history_survives_enabling_multi_user(tmp_path): ...      # Review Focus 5: data under str(OWNER) still active
async def test_delivered_lesson_counts_one_paper(api, student): ...
async def test_student_deep_is_refused_without_a_job(api, student): ...
async def test_non_member_gets_the_note_once(api): ...
async def test_owner_commands_need_the_owner_role(api, student): ...
async def test_unknown_attempts_are_charged_their_worst_case(registry): ...
async def test_sweep_forgets_inactive_students_never_the_owner(registry, clock): ...
def test_single_user_mode_rejects_user_id(api_single): ...
```

- [ ] **Step 2: Run — expect FAIL**
- [ ] **Step 3: Implement** in the order service → registry → API → app wiring.
- [ ] **Step 4: Run — expect PASS**, plus `tests/unit/test_study_service.py tests/unit/test_study_api.py tests/unit/test_development_bot.py`.
- [ ] **Step 5: Commit** `feat: route study requests per student behind the access gate`

---

### Task 7: Bot routing per chat

**Files:**
- Modify: `src/services/telegram_policy.py` (add `sender_text`), `src/services/telegram_bot.py`
- Test: extend `tests/unit/test_study_telegram.py`, `tests/unit/test_telegram_policy.py`

**Interfaces:**
- Consumes: Task 6's API.
- `@dataclass(frozen=True) class Sender: chat_id: int; user_id: int | None; text: str | None` and `sender_text(update) -> Sender | None` — for a private chat, the same checks as `owner_text` minus the owner comparison (`chat.id == from.id`, not a bot, not forwarded or via-bot, text present), giving `user_id` and `text`; for a group, supergroup or channel message, `Sender(chat_id, None, None)`, which the bot answers with `GROUP_CHAT` once per chat per bot run; anything else, None.
- `PrivateTelegramBot(..., multi_user: bool = False)`: with `multi_user`, `handle` posts `{"intent", "text", "user_id"}` and replies to that chat (a `{"reply": None}` result sends nothing); `_study_text(text, chat_id, keyboard)` and `_study_photo(encoded, chat_id)` take a chat; `self.progress` becomes `dict[str, dict]` keyed by job id, each with `chat_id`; a `"queued"` stage edits to `QUEUED.format(n=position)`; deliveries use each job's `user`; a Telegram 403 on any send to a chat posts `/study/undeliverable` and moves on to the next job; sends are at least 40 ms apart, and edits to one chat at least 1 s apart. Without `multi_user`, every existing test passes unchanged.

- [ ] **Step 1: Write the failing tests**

```python
async def test_reply_goes_to_the_senders_chat(bot_multi): ...
async def test_group_chat_gets_one_refusal(bot_multi): ...
async def test_queued_stage_shows_the_place_in_line(bot_multi): ...
async def test_a_403_for_one_student_does_not_block_another(bot_multi): ...   # Review Focus 4
async def test_owner_only_bot_is_unchanged(bot_single): ...                    # existing behaviour, multi_user=False
```

- [ ] **Step 2–4: Run (FAIL) → implement → run (PASS)**, plus `tests/unit/test_telegram_bot.py tests/unit/test_telegram_policy.py tests/unit/test_telegram_command.py`.
- [ ] **Step 5: Commit** `feat: route Telegram replies, progress and deliveries per student`

---

### Task 8: End-to-end check, docs and the full suite

**Files:**
- Create: `tests/api/test_multi_user_flow.py`
- Modify: `.env.example` (the seven `STUDY_*` settings with defaults and one-line comments), `README.md` (a short "Invite-only beta" section: enabling, `/invite`, limits, privacy), `docs/specs/multi-user.md` (status line → implemented)
- Test: the whole suite

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the failing end-to-end test** — two students redeem invites, request different papers at once through the API with a mocked provider and one pool slot; both receive their own lesson; the second shows `position == 1` while the first runs; a third, uninvited user gets `NOT_MEMBER` once; owner `/usage` reports `spent > 0` and `≤ ceiling`.
- [ ] **Step 2: Run — expect FAIL until wiring gaps are closed; fix only wiring**
- [ ] **Step 3: Update `.env.example`, README and the spec status**
- [ ] **Step 4: Run the full suite, Ruff and mypy** — expect all green on Windows; then the Linux CI job in WSL (`uv sync --frozen`, ruff, mypy, pytest as in `.github/workflows/ci.yml`).
- [ ] **Step 5: Commit** `test: cover the multi-user beta end to end and document it`

## After the plan

The owner's live Telegram test (spec §8 rollout steps 1–3) needs the bot restarted with `STUDY_MULTI_USER=true`; that and any model calls happen only with the owner's go-ahead.
