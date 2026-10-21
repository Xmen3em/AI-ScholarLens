# learning-session: resume learning without confusing sources

Status: extension spec, 21 October 2026. Inherits [shared rules](researcher-app.md).
Depends on paper-intake; supplies owner-selected state to the tutor/coordinator.

## Objective and baseline

Resume a paper, its learning goal and open questions after a restart while keeping
different papers separate. Current SQLite stores owner state, four recent turns,
24-hour conversation expiry, explicit depth and up to ten papers. The existing
30-day payload policy is preserved until changed explicitly.

## Provider contracts and memory

`StudySession`: server-owned ID/owner, exact PaperRef, goal, depth, selected
section/visual step, last accepted artifact and updated time. `StudyProgress`:
user-confirmed completed steps, question attempts, open questions and bookmarks.
Do not infer a mastery score from the length of the conversation.

Short context stays bounded: recent turns plus an optional versioned compact
summary of the study task. Summaries are generated context, not source facts;
creating/updating one consumes admitted model budget if it uses a model. Long
memory holds explicit preferences and saved artifacts/progress, not arbitrary
model-written beliefs about the learner. User corrections override summaries.

Store progress in an additive owner-scoped extension, not the paid-attempt ledger.
If a checkpointer is later required, namespace it by owner/session/source and
make its deletion/recovery consistent with application state. It cannot create
new attempts on restart. [LangGraph memory scopes](https://docs.langchain.com/oss/python/langgraph/persistence).

## Behavior, deletion and resource bounds

- List/open the bounded library and resume a saved point without inference.
  An updated paper version gets a separate study identity and a clear old-version
  marker. Context switches cannot move the result of an in-flight job to a new paper.
- Preserve existing retention/caps until additive migrations and a reviewed quota
  policy are tested. New artifact disk limits must be declared before activation;
  exceeding them returns a useful state instead of silently evicting paid work.
- `/forget` deletes new dialogue/preferences/progress/notes/artifacts and cancels
  access to their results. It does not reset attempt ceilings or resurrect old
  intents. Document retained source-cache/nonpersonal audit/tombstone data.

## Implementation, style and commands

Existing `store.py` is the charging/state baseline. Prefer a small new
`session_state.py`/progress store with an additive migration; keep clocks injected,
transactions atomic and two-owner tests explicit. Migration/recovery tests use a
temporary copy, never the live private SQLite file.

```powershell
.venv-win/Scripts/python.exe -m pytest tests/unit/test_study_store.py tests/unit/test_study_service.py -q -o cache_dir=tests/test_output/study-pytest --basetemp tests/test_output/session-contract
```

Add future progress/library tests before running their task-specific commands;
use the common lint/type checks. No model or external persistence service is
needed to verify save/resume/switch/delete behavior.

## Acceptance

LS-1: Paper A→B→A and process restart restore the correct goal/artifact/step with
zero generation and no cross-owner access. Expired turns are not sent to models.

LS-2: Lost/late jobs cannot overwrite the newly selected context. Untrusted model
output cannot change owner, retention, source identity or learner preferences.

LS-3: Forget and retention remove all documented new personal payloads while
preserving spent-call counts and duplicate suppression; backup restoration does
not replay provider/Telegram uncertainty.

Open choice: owner-selected retention beyond 30 days. Until answered, retain the
current policy and explain when saved study progress will expire.
