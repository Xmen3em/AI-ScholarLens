# paper-tutor: interactive Egyptian teaching

Status: extension spec, 21 October 2026. Inherits [shared rules](researcher-app.md).
Depends on paper-evidence and learning-session. Optional research reports are
supplied by the coordinator and never replace original evidence.

## Objective and baseline

Turn a paper into a guided learning conversation: explain a concept, give a
faithful example, invite an attempt, correct a specific misunderstanding and
offer the next step. Existing `Lesson` contracts, Egyptian prompts, follow-ups
and source review are the baseline. Current semantic review has accepted an
incorrect numeric comparison; it must not be treated as proof of correctness.

## Provider contracts and teaching flow

Extend via a versioned `TeachingArtifact`: source identity, selected goal/depth,
short orientation, typed sections, supporting refs, coverage/uncertainty,
explicit example/background origins and finite next actions. Preserve current
Lesson rendering through an adapter until new consumers migrate.

`LearningAction`: explain, simplify, example, method, result, equation, quiz,
check_attempt. `ComprehensionTask`: a bounded question, expected concept/rubric,
source refs and task version. `LearnerAttempt` binds the answer to that task;
`Feedback` identifies supported correct points, one misconception, an explanation
and a suggested next action. The rubric is application data, not an exposed
hidden reasoning trace. One response need not emit every possible lesson section.

Default journey: short orientation → choose a goal/section → one focused
explanation → optional attempt → feedback. Prerequisites use labeled background;
paper mechanisms/results use evidence. If the question is ambiguous, clarify
before a costly broad research job. Help/capability/status text stays local.

## Scientific and language rules

Preserve mechanisms, token/sentence granularity, equation signs, experiment
settings and uncertainty. A fictional analogy is visibly educational and must
not imply an unsupported mechanism. A prerequisite gap is not a missing paper
result. Egyptian wording should be natural and respectful, retaining standard
English search terms and original quotations. Apply [mixed-text reading](arabic-reading.md).

Deterministic identity/numeric checks run before final semantic review. Rejected
content gets a bounded explanation or remains unpublished; no unchecked repair.
Freeze prompt/schema revisions with the same input fixtures. Plain source IDs
alone do not qualify correctness; evaluate feedback on correct and incorrect
learner attempts separately from paper answering.

## Implementation, style and commands

Existing `tutor.py` and `service.py` remain compatible. Proposed small
`teaching.py`/`comprehension.py` modules use strict typed enums and injected model
transport. Each change keeps the four-call admission and reserves review capacity.
Later comparison accepts two explicitly selected versioned papers, independent
evidence per side and a metric-compatibility report; no global "winner" from
incompatible datasets. Keep comparison outside ordinary one-paper context.

```powershell
.venv-win/Scripts/python.exe -m pytest tests/unit/test_study_tutor.py tests/unit/test_study_feedback.py tests/unit/test_study_service.py -q -o cache_dir=tests/test_output/study-pytest --basetemp tests/test_output/tutor-contract
```

Use hand-reviewed misconception/feedback fixtures and stubbed transport first;
later hosted evaluation has its own scope. Use common lint/type checks and the
shared scientific/learning rubric; do not create tests that just repeat prompts.

## Acceptance and open choices

PT-1: A first lesson is useful and short, its supported claims inspectable, and
background/examples/uncertainty distinguishable. Unsupported sections are omitted
or labeled instead of filled with plausible guesses.

PT-2: Two focused teach→attempt→feedback turns stay with the same paper/goal,
correct an observed misunderstanding and permit skip/back without regeneration.

PT-3: Fixed scientific negatives fail, correct learner answers are not marked
wrong for wording, and the shared unseen scientific/Egyptian rubric is reported.
No claim of learning gains without a separate human study.

Model choice remains the current HF route until comparison. A richer default
goal menu can be refined after the owner uses the first interactive slice.
