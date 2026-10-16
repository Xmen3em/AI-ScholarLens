# Private Telegram app with LangGraph

> Current status, 16 October 2026: private owner development testing is running
> with concept explanations and cited paper questions. Follow
> [telegram-development.md](telegram-development.md) for that opt-in mode.
> This document retains the original qualified-runtime contract and pairing
> procedure; its older disabled/acceptance notes do not describe the development
> launcher's current state. The formal paper-quality holdout remains rejected.

The user chose LangGraph like the course reference, a bot private to their own
account, and initial operation on their current PC. This supersedes earlier
optional-Telegram/no-LangGraph planning, while preserving application guards,
existing API/key, local data/models, runtime and exhausted HF allowances.

Build order: migrate the existing bounded agent to LangGraph, then add a separate
private polling client of the authenticated API. Existing source/service/API tests
remain mandatory. User choices authorize the framework dependency and bot source
integration. Live Telegram startup requires the privately configured bot token and
owner ID. HF remains disabled until separately approved live qualification passes.

## LangGraph contract

Use a compiled StateGraph with validation, retrieval, grading, rewrite, answer and
abstention nodes and conditional edges. Keep the original request, prompts,
evidence ownership, selector/rendering and quotas unchanged. Request-local counters
still bound eight stages, two retrievals, one rewrite, six generation calls and the
original deadline. Graph recursion limits are an additional bound. No arbitrary
tools, checkpointing, history or new model calls.

Graph state contains routing metadata only. Request/context stay in runtime
context. Expose only typed operation status and validated final responses through
custom streaming; never forward raw graph streams. Pause before model/search work
until the caller resumes consuming the status, preserving cancellation and deadline
behavior. Disable external LangSmith tracing even if ambient environment enables it;
keep existing metadata-only local monitoring. Follow official
[graph API](https://docs.langchain.com/oss/python/langgraph/graph-api),
[custom streaming](https://docs.langchain.com/oss/python/langgraph/streaming), and
[tracing context](https://docs.langchain.com/langsmith/trace-without-env-vars).

LangGraph migration implemented with pinned `langgraph==1.2.15`. The dependency
lock adds its required packages; the only previous package version change is
jsonpointer3.0.0 ->3.2.1 for new jsonpatch requirements. All228 installed packages
pass `uv pip check`. Actual-ASGI disconnect initially exposed delayed framework
node cancellation; shielded cleanup now cancels and joins that node before returning.
Full953 tests pass,zero skips,62focused,mypy102,Ruff. No application activation,
HF inference, external tracing or Telegram messages occurred in this increment.

## Private bot contract

Separate explicit launcher, disabled by default, with one configured positive
Telegram owner ID, SecretStr token and original server-side API key. Accept only
ordinary text messages sent by that owner in their matching private chat; reject
groups, forwarded messages, other users and malformed/oversized updates before any
API/generation/message action. No discovery from usernames and no public access.

Use HTTPS to Telegram and the fixed loopback ScholarLens API. Long polling requires
no public webhook or inbound port. Do not alter a preexisting webhook or discard
pending updates silently. One bot instance and one question at a time; reserve the
existing application quota through the API. The bot makes one API attempt per
question, without provider fallback.
Persist only an update offset in a local ignored file so restarts do not repeat
uncertain paid work; no question/answer history. A local single-instance lock guards
the offset. Offset advances before work; failure/uncertainty does not replay a query.

The implementation also retains a fixed registration marker beside the offset.
Missing/corrupt state or registration requires explicit recovery instead of silent
reinitialization. The bot never retries an API question; the agent retains its
original bounded selector retry. A question interrupted after admission can be
lost, which is preferable to replaying uncertain hosted work. Restart uses the same
state path; moving to a fresh path is not recovery of an already used bot.

Commands: /start and /help explain use; /ask question or plain text calls the
authenticated agent API. Return validated answer, markers and bounded paper links
as plain text, without Telegram parse modes. Split within Telegram's message limit;
generic errors never expose credentials, exception text, prompts or reasoning.
Bound HTTP bodies, polling/update batches, question size, generated reply size,
request deadlines and retry delay. Poll errors may reconnect with backoff; inference
and outbound messages are not retried on uncertain completion. Actual owner test
requires the user to start their bot after explicit launch setup. Official
[BotFather tutorial](https://core.telegram.org/bots/tutorial#obtain-your-bot-token)
and [Bot API](https://core.telegram.org/bots/api#getupdates).

## Verification and rollout

Use synthetic mocked model/search/HTTP responses with real graph, validation and
API boundaries. Preserve existing agent cancellation tests. Add graph routing,
state privacy, ambient tracing, Telegram access/replay/output/secret/error tests.
Run focused pytest, full pytest, mypy, Ruff and dependency/lock review before local
checkpoint. No paid HF calls, live Telegram messages, broad Compose restart, data
ingestion or runtime replacement during this source implementation.

Remaining live gates: bot creation/private token and owner ID; a separately approved
bounded HF allowance, reliable exact-schema qualification and paper evaluation;
explicit local runtime activation and owner's end-to-end Telegram test. Local
source tests alone do not establish HF quality, deployment or final app acceptance.

## Local setup

The user created `@AIScholarLensbot` and saved its token privately on 2026-10-15.
Read-only `getMe` verified the token against that username; `getWebhookInfo`
confirmed no webhook. A fresh private code verified the owner's account and saved
only its numeric ID in the private `.env`. Pairing is complete and its challenge
is consumed. Leave `TELEGRAM_ENABLED=false` until the reviewed local rollout.

The setup command reads no HF credentials, sends no messages, and starts neither
the bot nor the API. Default/`--check` performs no network calls or state writes:

```powershell
.venv-win/Scripts/python.exe -m src.commands.setup_telegram --check
.venv-win/Scripts/python.exe -m src.commands.setup_telegram --prepare --username AIScholarLensbot
```

Preparation verifies the expected bot identity and absence of a webhook, then
prints a one-hour pairing link. Open it in your own Telegram account and press
Start. If needed, send the exact `/start setup_...` code from the link manually.
Keep the link private: possession of its random code proves control of the account
that sends it. The bot does not reply during pairing.

```powershell
.venv-win/Scripts/python.exe -m src.commands.setup_telegram --verify
```

Verification reads one bounded batch of pending updates without an offset or an
`allowed_updates` change, so it neither confirms nor drops existing messages.
Only the fresh exact code in an ordinary private message from a non-bot account
whose chat ID matches its sender ID can supply the owner. Forwarded, old, unrelated,
group and ambiguous-owner proofs fail closed. A full 100-update batch requires
review rather than advancing past it. No raw update or message text is saved.

Successful verification changes only `TELEGRAM_OWNER_ID` in the private `.env`,
preserving all other bytes and leaving Telegram/HF/agent disabled. Existing owner
replacement, changed tokens and an already enabled bot require review. The local
challenge is consumed; state is under ignored `data/telegram/`, protected by a
single-instance lock and path checks. Missing/corrupt state is not silently repaired.
Expired challenges require explicit renewal:

```powershell
.venv-win/Scripts/python.exe -m src.commands.setup_telegram --prepare --username AIScholarLensbot --renew
```

The setup never calls `sendMessage`, changes a webhook, or creates/advances the
production polling offset. Follow Telegram's official
[deep-linking mechanism](https://core.telegram.org/bots/features#deep-linking) and
[update confirmation rules](https://core.telegram.org/bots/api#getupdates).

The new fields are documented in `.env.example`; `.env.test` explicitly shields
tests from private Telegram settings. Source installation preserved existing
private settings; pairing adds only the verified owner field.
The following command performs no network calls and creates no offset or lock:

```powershell
.venv-win/Scripts/python.exe -m src.commands.run_telegram --check
```

After private credentials, accepted HF model and candidate API are ready, the
explicit launcher is:

```powershell
.venv-win/Scripts/python.exe -m src.commands.run_telegram --execute
```

The retained running API is still the Week6 image, without the new LangGraph
workflow. Source changes have not activated/rebuilt/replaced that API. Prepare an
isolated candidate API on port8002 for the reviewed local rollout and set
`TELEGRAM_API_BASE_URL=http://127.0.0.1:8002/api/v1`; the bot permits only the
loopback API paths on8000/8002. Preserve original8000/runtime/rollback throughout.
Changing Telegram configuration cannot enable HF or the backend agent by itself.
Source is ready; credentials, runtime activation and live owner acceptance remain.

## Dependency compatibility finding

LangGraph's required packages add zstandard, which changes HTTPX's default
Accept-Encoding negotiation. The preserved OpenSearch endpoint returns zstd
headers but stalls the body. Identity-encoding reads work and reproduce original
corpus hashes. The unchanged OpenSearch application driver does not advertise
zstd and successfully reads all2775 documents. The isolated hosted snapshot helper
now explicitly requests identity encoding for localhost audit reads; regression
tests reproduce the timeout and retain model-digest rejection. No inference
payload, HF client, schema, prompt, provider, selector or runtime policy changed.

The graph's tracing context is scoped to each advancement/cleanup, never across
public event yields. A dedicated regression verifies the caller's tracing settings
remain unchanged while model/node tracing stays off.

## Completed source verification

**1,011 full tests pass,zero skips**,62new since432c5d6,128focused,mypy105,Ruff.
Two owner/admission mutations were detected and exact bytes restored. Both strict
environment-template checks are extended to the real standalone settings reader;
no test exclusions or weaker assertions. Private credentials and state-path checks,
malformed batches, uncertain calls, canonical quotation validation, Unicode limits,
restart/cancellation/lock behavior and generic errors are covered with mocked HTTP.
Actual full corpus/index/model digests and64 existing frozen checks match. All15
retained container identities/images/states,privateAPI/settings,old evaluation/
frozen/recovery artifacts and both exhausted allowances remain unchanged.

Ignored evidence is under `tests/test_output/telegram-langgraph-prep-20261014-01/`:
graph/bot verification, mutation, protected-file/container snapshots, dependency
metadata and live-preservation audits. No paid calls or actual Telegram traffic.
This is a source checkpoint, not live HF qualification or final app activation.

Owner setup added36 tests on 2026-10-15: **1,047 full tests pass, zero skips**,91
focused Telegram checks,mypy106,Ruff. Two RED cases reproduced the missing command
and an implicit null-state replacement; both are fixed. All35 audited private/
evaluation/allowance/recovery files remain unchanged before owner pairing, and
source secret scans pass. After the user sent the code, verification completed
pairing with an exact owner-only `.env` change and all34 other protected files
preserved. Eight read-only Telegram calls total;zero Telegram messages/zero HF
calls. The bot's silence during pairing is expected; it is not running yet.
Setup evidence, including `owner-verification.json`, is under ignored
`tests/test_output/telegram-owner-prep-20261015-01/`. Source checkpoint290fef7;
no source changes or repeat tests after the live owner-only configuration step.
