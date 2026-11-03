# learning-delivery: Telegram and a usable study workspace

Status: extension spec, 21 October 2026. Inherits [shared rules](researcher-app.md).
Consumes tutor artifacts and optional visuals/research reports; uses the trusted
coordinator for source and session operations. Keep provider modules UI-agnostic.

## Objective and baseline

Make it clear what the app is doing and let the researcher continue learning
without unnecessary generation. Current paired private Telegram, local API,
progress text, study commands and PNG maps work. Polling accepts message updates;
callback-query handling and a phone-accessible study viewer are not implemented.

**Staged progress (3 November 2026).** While a lesson or follow-up job runs, the
bot edits its own acknowledgement message once per stage and sends no other message:
`reading` (1 of 3), `writing_lesson` / `writing_answer` / `researching` (2 of 3)
and `checking` (3 of 3, the claim check). The service keeps the stage of each running
job in memory only, `/study/pending` lists it as `running: [{id, stage}]`, and the
bot maps known stage names to fixed Egyptian Arabic lines, so no paper, model or
provider text reaches the progress message. Telegram can edit only a message sent
without a reply keyboard, so the acknowledgement of an admitted job goes without
one; the result restores it. Progress is best effort: a failed edit is not retried
and never blocks delivery. While a job runs, `getUpdates` waits 3 s instead of 20 s,
so progress and the result reach the student within seconds of each stage.

## Contracts and API behavior

`StudyView`: selected source/version, coverage, goal/position, accepted artifact,
finite available actions and safe job status. `StudyAction`: known action enum,
artifact/session ID, expected version and stable intent. Owner is server-owned;
clients cannot submit filesystem paths, arbitrary URLs or model configuration.
Use bounded IDs and strict input/output models.

New action requests are a discriminated union: `resource_kind` is `session` or
`artifact`, `resource_id` is a server-issued 32-character hex ID, `intent` is
1–120 characters and `expected_version` is a positive integer. `action` is a
fixed enum; `target_id` is null or a known 1–64-character ID within the resource.
Initial artifact actions are `select_step`, `select_component`, `open_source`;
session actions are `resume`, `save_position`. Invalid action/resource/target
combinations fail before state changes. More actions require a schema/test update.
The coordinator resolves owner/source/hash from storage; no caller identity field.
Responses return the accepted resource version, selected IDs and StudyView.
Illustrative request to the proposed actions route:

```json
{
  "intent": "visual-action:owner-update-123:step-2",
  "resource_kind": "artifact",
  "resource_id": "00000000000000000000000000000001",
  "expected_version": 1,
  "action": "select_step",
  "target_id": "training-2"
}
```

The ID is a synthetic example, not a live artifact or authorization token.

Proposed additive routes under `/api/v1/study/`:

| Route | Input/output | Admission |
| --- | --- | --- |
| `POST /actions` | Strict StudyAction → StudyView or version conflict | Request quota; no inference |
| `GET /artifacts/{id}` | Owner-scoped accepted artifact metadata/text | Request quota; no inference |
| `GET /artifacts/{id}/assets/{kind}` | Fixed asset enum; validated bytes/type | Request quota; no path traversal |
| `GET /library` | Bounded cursor/limit → owner paper summaries | Request quota; no inference |

Implement route models from this proposed contract before wiring their handlers;
add bounded asset-kind/cursor response schemas in the matching task. Keep existing `messages`,
`pending`, `claim` and HTTPException detail behavior compatible. Never use the
currently generation-rated `/messages` endpoint for every next/previous action.
Generation remains an explicit admitted request under existing quotas.

Same intent/same payload returns its prior/pending result; changed payload is
409 conflict, invalid schema 422, missing auth 401, inaccessible owner artifact
404 and exhausted quota 429. Asset caches are private and keyed to accepted
version/hash. Expected-version checks prevent stale controls changing new state.

## Telegram behavior and uncertainty

Reuse private owner, forwarded-message, update-intent, claim/ack and replay gates.
Start with validated text commands for method/step/source actions. If later adding
inline callbacks, specify their owner/chat/message/action binding, expiry,
acknowledgement and duplicate behavior first. Do not assume message polling
already accepts callback updates.

Keep paragraphs readable and UTF-16 bounded. Apply the separate
[Arabic/English adapter](arabic-reading.md), not browser HTML. Test Desktop and
the actual mobile client before claiming client parity. Source links/commands
remain copyable and text stays available when an image fails.

Admission acknowledgment is not final completion. Display only actual stages,
terminal outcome and a safe job/support ID. Poll/status controls are local.
Cancellation stops future work and signals workers; a sent/unknown provider call
still counts. A Telegram timeout can leave delivery unknown: retain that state
and provide owner-invoked result access; do not promise exactly-once or blindly
resend. New durable delivery states need migration/crash tests before rollout.

## Workspace and hosting stages

First local desktop viewer is a trusted app-authored HTML/SVG export: source/
coverage panel, concise explanation, visual steps, component/source inspector,
notes and text alternative. State changes are deterministic. No credentials are
embedded and no generated code is executed. Follow RTL/keyboard/copy/zoom rules.

A later authenticated workspace integrates library, study position, PDF/region
view and notes. Keep loading/empty/partial/unsupported/error states functional,
with prior accepted artifacts visible while a new job runs. A lightweight static
frontend is the default; add a framework only for a demonstrated need, pinned
in a separate slice. No browser process starts with the bot.

Phone access/Mini App requires reachable HTTPS, validated server-side `initData`,
owner allowlisting, freshness/replay checks and secure session handling. Never
trust `initDataUnsafe` or ship the bot token/API key to the client. The PC's
loopback URL is not a phone deployment. Keep this after private hosted readiness.
[Telegram validation](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).

## Implementation and commands

Existing `src/services/telegram_bot.py`, study `api.py`/`service.py` and
`Telegram.ps1`; proposed `actions_api.py`, dedicated visual/viewer modules and
trusted static assets. Use strict models, finite action handlers and bounded
payloads. Keep thin routing adapters; do not put storage/model logic in handlers.

```powershell
.venv-win/Scripts/python.exe -m pytest tests/unit/test_study_api.py tests/unit/test_study_telegram.py tests/unit/test_telegram_bot.py -q -o cache_dir=tests/test_output/study-pytest --basetemp tests/test_output/delivery-contract
```

New action/workspace tests precede their focused commands. Browser QA inspects
real DOM, console/network, keyboard order and actual exports. Use the common
regression/lint/type checks. Live maintenance replies need applicable explicit
authorization; no unsolicited Telegram smoke messages during planning.

## Acceptance

LD-1: Private source→lesson→follow-up→saved-point journey survives duplicate
updates/restart; status/help/navigation generate no new model call.

LD-2: Unauthorized, forwarded, wrong-version and replayed actions fail safely;
assets are inert/owner-scoped. A failed image/worker leaves readable source/text.

LD-3: Local viewer passes the visual/RTL suite; later phone delivery has recorded
client/auth/restore evidence before being called continuously available.

Open choices: later public host/domain and whether a Mini App improves the
measured study workflow over an ordinary web workspace. Desktop work proceeds now.
