# paper-intake: identity before learning

Status: extension spec, 21 October 2026. Inherits engineering, verification and
scope rules from [the whole-app spec](researcher-app.md). Depends on existing
owner authentication; provides identity to content and learning-session.

## Objective and baseline

Resolve the paper the researcher intended, including its version, before any
teaching job. Existing `intake.py` supports arXiv URL/ID/title and explicit
candidate selection. Preserve that behavior and the 500-character input bound.
Do not select the first title hit or a newer version silently.

## Provider contract

`PaperRef` is application-owned: supported origin, canonical ID, explicit version,
canonical abs/PDF URLs, title, bounded authors/categories and acquisition time.
The existing `StudyPaper` stays compatible; add an internal adapter when an
extended identity is needed. Content adds the PDF hash after acquisition.

`IntakeDecision` is one of `resolved`, `selection_required`, `unsupported`,
`not_found`, `temporarily_unavailable`. A selection token binds owner, normalized
query, result IDs/versions and expiry. It cannot be reused against another owner
or changed candidate list. Returning candidates does not spend inference.

## Behavior and boundaries

- Reuse existing origin validation and bounded metadata parsing, including
  forbidden XML entities, spoofed hosts, credentials, redirects and malformed IDs.
- Show the selected title/version plus coverage status once content is known.
  Version updates create a new source identity and leave old notes attached.
- Unsupported publishers return a clear supported-source route. Later PDF upload
  uses a separate authenticated attachment contract, content hash and unverified
  bibliographic identity; a filename or model guess is not an arXiv identity.
- Owner selection is explicit for ambiguous titles; expired/changed selections
  require a fresh search and cannot trigger a job implicitly.

## Implementation, style and commands

Extend `src/services/study/intake.py` and a small new identity model only when
needed; keep HTTP clients injected and reuse strict `StudyPaper` validation.
Tests belong beside `tests/unit/test_study_intake.py`, including selection/store
integration. No network or model is required for these checks.

```powershell
.venv-win/Scripts/python.exe -m pytest tests/unit/test_study_intake.py tests/unit/test_study_service.py -q -o cache_dir=tests/test_output/study-pytest --basetemp tests/test_output/intake-contract
```

Use a fresh basetemp and the common lint/type checks. Always preserve version
identity and source policy; later uploads/publisher fetching need their own
bounded security slice, not an exception to the arXiv URL validator.

## Acceptance

PI-1: URL, ID and selected title resolve to the same explicit version in fixtures;
spoofed/expired/wrong-owner inputs produce no content fetch or inference.

PI-2: Switching or updating a version never reattaches an old lesson/visual
without a source-identity match. Duplicate selection preserves one intent.

PI-3: Unsupported sources explain the available next action without inventing
metadata. Deferred upload support is displayed as unavailable until implemented.

Open choice: which non-arXiv origins to support after private native-text study.
It does not block the current intake/identity integration.
