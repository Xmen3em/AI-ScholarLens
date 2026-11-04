# multi-user: an invite-only beta with daily limits and a dollar ceiling

Status: design approved 4 November 2026; spec awaiting owner review.
Inherits [shared rules](researcher-app.md) and extends
[learning-delivery](learning-delivery.md) and [paper-tutor](paper-tutor.md).
Production model: GLM-5.3 ([paper-benchmark](paper-benchmark.md) §6).

## Why

The tutor answers one Telegram account. `TelegramSettings.owner_id` decides who
may write and where every reply, progress edit and study map goes; the study API
builds one `StudyStore(..., owner)`, one `StudyService` and one `StudyModel`,
whose single lock refuses a second concurrent call as `study_model_busy`. Limits
count calls, not money. To open the tutor to community members it needs
membership, per-student state, fair concurrency, and a hard cap on spend, before
it is hosted.

The store already keys every table by `owner`, and `/forget` exists, so
per-student data is mostly an addressing change.

## Decisions (owner, 4 November 2026)

- Audience: an **invite-only beta**, about 5–30 community members.
- Limits: **papers and questions per student per day**, plus a **global daily
  dollar ceiling** counted from real usage.
- Concurrency: **up to 3 jobs at once**, one per student, in a fair queue that
  shows the student's place.
- `/deep`: **owner only** at launch.
- Retention: content is deleted **after 30 days without use**, or at once with
  `/forget`; accounting is kept without content.
- Approach A: one `StudyService` per student, created on demand, sharing one
  model pool, behind a new access gate. Lesson, evidence and claim-check logic
  are unchanged.

## 1. Components

```
Telegram ──► bot (routes by chat; private chats only)
                │  member?  rate ok?
                ▼
         AccessGate ── invites · members · daily counts · $ ledger (SQLite)
                │  admitted
                ▼
   ServiceRegistry ── StudyService per student (lazy; idle ones closed)
                │            └─ StudyStore(sessions.sqlite3, owner=<telegram user id>)
                ▼
   ModelPool ── one HTTP client · 3-slot FIFO · memory gate · usage → $ ledger
```

- **Bot** (`src/services/telegram_bot.py`, `src/services/telegram_policy.py`):
  accepts private-chat updates from any user and replies to the sender's chat.
  Progress messages and study-map uploads are tracked per chat. Group and channel
  updates get one refusal and are otherwise ignored.
- **AccessGate** (new, `src/services/study/access.py`): members, invites, daily
  counts, the dollar ledger and the request-rate window. Its tables live in the
  same `data/study/sessions.sqlite3`. Every admission decision is one
  transaction.
- **ServiceRegistry** (new, in the study API): `StudyService` per student, built
  on first use from the shared intake, content service and model pool; closed
  after 30 minutes idle. The owner's service also has `research_python` (for
  `/deep`); students' services do not.
- **ModelPool** (new, `src/services/study/pool.py`): replaces the per-instance
  lock in `StudyModel` with a shared semaphore of `STUDY_PARALLEL_JOBS` slots
  granted in arrival order, at most one held per student. Each student's
  `StudyModel` keeps its own store (attempt accounting) and shares the pool's
  HTTP client. The live memory gate (600 MiB) still runs before every call.
- **API** (`src/services/study/api.py`): `StudyMessage` gains `user_id`
  (a positive integer, as Telegram gives it). Pending deliveries and delivery
  claims are listed across all students, each carrying its `user_id`.

With `STUDY_MULTI_USER=false` (the default) none of this is reachable: the owner
is the only accepted chat, the owner commands (`/invite`, `/members`, `/revoke`)
do not exist, and the behaviour is today's.

## 2. Membership and access

- The owner (`TELEGRAM_OWNER_ID`) is always a member with role `owner`.
- `/invite` or `/invite N` (owner, 1 ≤ N ≤ 10) returns N one-time codes: 10
  characters from an unambiguous alphabet (no 0/O/1/l), valid 7 days. Only a
  hash of each code is stored.
- `/start CODE` from a non-member consumes a valid code and makes the sender a
  `student`. A used, expired or unknown code is refused with the same message.
  From an existing member it shows the welcome again and consumes nothing.
- A non-member writing anything else gets the invite-only note at most once per
  Cairo day, and nothing else happens: no service, store or model is touched.
- `/revoke USER_ID` (owner) blocks the student at once and deletes their study
  content (`StudyStore.forget` for that owner). Accounting stays. A revoked user
  who writes gets the revoked note at most once per Cairo day; a new invite code
  can make them a member again.
- `/members` (owner): each member with role, joined date, last active, and
  today's papers, questions and dollars.
- `/deep` from a student is refused with its own message; it is never queued.

## 3. Daily limits and the dollar ledger

A day is the calendar day in `Africa/Cairo` (the `tzdata` package, already in
`uv.lock`, makes this work on Windows).

- **Counts.** A *paper* is a delivered first lesson; a *question* is a delivered
  follow-up. Only delivered (`ready`) answers count, so a failure on our side
  (provider, format, memory, claim check) never costs a student quota. Defaults:
  `STUDY_DAILY_PAPERS=3`, `STUDY_DAILY_QUESTIONS=30`. The owner is exempt from
  counts.
- **Admission.** A first lesson is admitted only if the student has a paper
  left; a follow-up only if a question is left. Because a student holds at most
  one job, in-flight work never exceeds what is left.
- **Dollars.** Each call costs `call_cost_usd(DEFAULT_PROFILE, usage)`: reported
  usage at the profile's prices, or the worst case (input estimate plus 3,000
  output tokens) when a response carries no usage. Every caller, the owner
  included, counts toward the ceiling.
- **Reservations.** At admission a job reserves `max_calls × worst call` (about
  $0.06 for a two-call lesson on GLM-5.3) against today's ceiling,
  `STUDY_DAILY_USD_CEILING` (default `2.00`). As each call settles its real cost
  replaces part of the reservation; when the job ends the remainder is released.
  Admission requires `spent + reserved + this reservation ≤ ceiling`, so parallel
  jobs cannot overshoot it.
- **Rate.** More than `STUDY_MESSAGES_PER_MINUTE` (default 6) messages from one
  user in 60 seconds are answered with the slow-down note and nothing else.
- `/usage`: a student sees their own remaining papers and questions; the owner
  sees today's spend, reservations and ceiling, and the top five students.

## 4. Queue and progress

- When all slots are busy, an admitted job waits in arrival order. Its progress
  message reads `في الطابور: إنت رقم N` and is edited as N changes, then moves on
  to the existing reading / writing / checking stages
  ([learning-delivery](learning-delivery.md)).
- If the ceiling is reached while a job waits, the job ends with the ceiling
  message, reserves nothing further and costs no quota.
- `/forget` while a job runs keeps today's refusal (`في طلب شغّال دلوقتي...`).

## 5. Messages (Egyptian Arabic; exact copy)

| Case | Text |
| --- | --- |
| Not a member | البوت ده في تجربة محدودة بالدعوة. لو معاك كود دعوة ابعت: /start الكود |
| Bad or used code | الكود ده مش صالح أو اتستخدم أو انتهى. اطلب كود جديد من صاحب البوت. |
| Welcome | أهلًا بيك في تجربة ScholarLens! ابعت رابط ورقة من arXiv أو اسمها بالإنجليزي وهشرحهالك. اكتب /privacy تعرف إحنا بنحفظ إيه، و/usage تعرف فاضلك قد إيه النهارده. |
| Usage (student) | النهارده: فاضلك {p} من {P} ورقة و{q} من {Q} سؤال. العداد بيتصفّر الساعة 12 بالليل بتوقيت القاهرة. |
| Papers used up | خلّصت ورق النهارده ({P} من {P}). تقدر تكمّل أسئلة على الورقة الحالية، أو ترجع بكرة. |
| Questions used up | خلّصت أسئلة النهارده ({Q} من {Q}). ارجع بكرة. |
| Ceiling reached | البوت وصل لحد الاستخدام اليومي. ارجع بكرة، ومعلش على كده. |
| Too fast | استنى دقيقة قبل الرسالة الجاية. |
| Queued | في الطابور: إنت رقم {n}. هبدأ أول ما ييجي دورك. |
| /deep (student) | أمر /deep متاح لصاحب البوت بس في التجربة دي. |
| Group chat | البوت بيشتغل في الشات الخاص بس. |
| Revoked | العضوية دي اتلغت. |

**/privacy:** بنحفظ الأوراق اللي فتحتها وأسئلتك وإجاباتها عشان نكمّل معاك. نص الورقة
وسؤالك بيتبعتوا لموديل الذكاء الاصطناعي (GLM-5.3) عن طريق Hugging Face عشان يتعمل
الشرح. لو ما استخدمتش البوت 30 يوم بنمسح كل ده تلقائيًا، و/forget بيمسحه فورًا. بنحتفظ
بس بعدد الرسائل وتكلفتها من غير أي محتوى.

`/help` lists `/usage`, `/privacy` and `/forget` for students, plus the owner
commands for the owner.

## 6. Retention and privacy

- A sweep runs at startup and then every 24 hours: every `student` whose last
  activity is older than `STUDY_RETENTION_DAYS` (default 30) has
  `StudyStore.forget` applied. The owner is never swept. The sweep logs counts
  only.
- Kept after a sweep, `/forget` or `/revoke`: member row, daily counts, call
  attempts and dollar ledger, all without content.
- Logs and audit events never contain message text, paper text, invite codes
  or Telegram usernames; a user appears as `StudyStore.fingerprint()`.

## 7. Failures

- **Crash mid-job:** startup recovers interrupted jobs for every owner, not one.
  They end `failed` (no quota), and their open reservations settle at the worst
  case of the calls actually reserved.
- **Memory gate, provider or format failure:** the existing failure message; no
  quota; only made calls are charged.
- **SQLite:** the database is switched to WAL once at startup; writes keep
  `BEGIN IMMEDIATE` and a 5 s busy timeout. A job's count and ledger updates
  share one transaction.
- **Blocked bot:** a Telegram 403 on send drops that delivery, marks the member
  inactive, and stops further sends to them until they write again.
- **Telegram limits:** sends stay at least 40 ms apart globally, and progress
  edits stay at least 1 s apart per chat.

## 8. Configuration and rollout

| Setting | Default |
| --- | --- |
| `STUDY_MULTI_USER` | `false` |
| `STUDY_DAILY_PAPERS` | `3` |
| `STUDY_DAILY_QUESTIONS` | `30` |
| `STUDY_DAILY_USD_CEILING` | `2.00` |
| `STUDY_PARALLEL_JOBS` | `3` (1–4) |
| `STUDY_MESSAGES_PER_MINUTE` | `6` |
| `STUDY_RETENTION_DAYS` | `30` |

Settings are validated at startup; an out-of-range value refuses to start. The
owner's existing data is already stored under `str(owner_id)`, so it carries
over. New tables are created idempotently and no existing table changes.

Rollout: (1) enable with the owner as the only member; (2) invite a second
account of the owner's; (3) the owner's live Telegram test before hosting;
(4) invite the beta.

## 9. Tests (offline; mocked provider and Telegram)

- **AccessGate:** codes single-use, hashed, expiring after 7 days; non-member
  note once per Cairo day; revoke blocks and forgets; counts per Cairo day
  (midnight rollover); only delivered answers count; reservations under three
  concurrent admissions never exceed the ceiling; rate window.
- **ModelPool:** at most N slots; arrival order; one slot per student; queue
  positions; cancellation when the ceiling is reached while waiting.
- **Bot:** replies go to the sender's chat; groups refused; owner-only commands
  and `/deep`; `/usage` and `/privacy` copy exactly as §5; 403 marks inactive;
  `STUDY_MULTI_USER=false` reproduces today's owner-only behaviour.
- **Retention:** the sweep forgets inactive students, keeps accounting, and never
  touches the owner.
- **End to end:** two simulated students at once through the API, each seeing
  only their own paper and dialogue.
- The full suite and CI pass on Windows and Linux.

## Out of scope

Hosting (deferred until every feature is done), payments, a web interface,
public sign-up, per-student `/deep`, group chats, and changing the model,
prompts or claim check.

## Acceptance

With `STUDY_MULTI_USER=true`, two Telegram accounts study different papers at
the same time; each sees only their own lessons, `/usage` and queue position; a
third, uninvited account gets only the invite-only note; the owner's `/usage`
shows real spend under the ceiling; and every test above passes in CI.
