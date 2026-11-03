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

## Memory layers (added 3 November 2026)

Five layers, after the common agent-memory split (working, episodic, semantic,
procedural, meta). One rule spans all of them: the **paper is never memory**.
Source text stays the only truth; memory holds facts about the learner and the
study. A model-written claim saved as memory would be served back later as
truth, which is the contradiction failure this design exists to avoid.

| Layer | ScholarLens contract | Written by | Read when | Task |
| --- | --- | --- | --- | --- |
| Working | Selected evidence, last four turns (24 h), depth, question. Prior replies are not evidence. | Each request | That request only | Existing |
| Episodic | `StudyEvent`: append-only, owner/PaperRef-scoped, finite types (opened, section studied, question asked, attempt graded, bookmark, artifact accepted), time, references to artifacts/attempts. No provider text. | The application after each terminal job or action | Resume ("you stopped at the training step") and a bounded deterministic summary for the tutor | S1 |
| Semantic | `LearnerConcept`: one record per (PaperRef, concept ID): `new`/`shaky`/`understood`, misconception labels, and the attempt + source quote behind each change. Updated in place; history stays in episodes. | Graded attempts (T2) and explicit learner confirmation only | Choosing quiz targets and the next step; adapting depth | T2 |
| Procedural | Failure ledger: review rejections (`rejected_sections`, issue labels), screen reasons, failure stages and prompt revision per job, already stored as finite labels. | Offline aggregation command | A person reviewing patterns before changing a prompt, screen or fixture | Q0 |
| Meta | One retention table across layers, deterministic compaction of old episodes into counts/last position, and `/forget` deleting every learner layer. | Scheduled/threshold maintenance plus `/forget` | Never by the model | S2 |

Constraints:

- Concept IDs come from accepted artifacts or a graded task's own concept
  field, never from free-text matching of model output. A concept from an old
  paper version stays attached to that version.
- No runtime self-modifying prompts. Procedural changes are versioned
  (`PROMPT_REVISION`, screens, fixtures), reviewed by a person, and regression
  tested against the frozen science cases before shipping. The 3 November loop
  (observed error → fixture → prompt v6 and screen) is the manual baseline.
- Summaries for the tutor are built deterministically from events and concept
  records; a model-made summary still follows the rule above (generated context,
  admitted budget, user correction wins).
- Memory never admits a model call, changes owner/source identity, or counts as
  evidence in a lesson. A learner correction overrides any stored status.

LS-4: Study A, answer one graded question wrong, restart, open A: the bot offers
the saved position and targets the missed concept with zero extra generation;
paper B shows none of A's concepts.

LS-5: `/forget` removes every episodic and semantic learner record and the tutor
summary; the failure ledger keeps only label counts with no learner text, and
spent-call accounting is unchanged.

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
