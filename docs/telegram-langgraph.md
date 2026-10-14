# Private Telegram app with LangGraph

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
existing application quota through the API, with no model retries or fallback.
Persist only an update offset in a local ignored file so restarts do not repeat
uncertain paid work; no question/answer history. A local single-instance lock guards
the offset. Offset advances before work; failure/uncertainty does not replay a query.

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
