# study-notes: inspectable notes and deliberate export

Status: extension spec, 21 October 2026. Inherits [shared rules](researcher-app.md).
Consumes accepted tutor artifacts and optional visual artifacts; receives owner
and selected-session context from the coordinator. It never writes source facts.

## Objective and baseline

Let the researcher keep their understanding, questions and citations and carry
them to another study tool. Current `/notes` exposes the lesson and original
quotes. User-editable notes, packaged export and application Notion integration
remain extensions; the bot has no inherited Codex Notion authorization.

## Provider contracts

`StudyNote`: server ID/owner, source identity, note version, author origin
(`user`, `accepted_assistant`), bounded text, source refs and timestamps. Separate
personal interpretations from exact quotations and from proposed model notes.
Edits use expected versions; source/version changes do not rewrite old notes.

`ExportPreview`: immutable snapshot of selected note/lesson/visual versions,
destination kind, included fields/source refs, content digest and stable intent.
`ExportResult`: pending/succeeded/failed/unknown with the same digest and a safe
destination reference. No model decides the destination or gains write access.

## Behavior and boundaries

Start with local editable notes and a UTF-8 Markdown export plus source links;
include standalone visual files by accepted hash when selected. Markdown retains
canonical logical text; a later HTML/PDF export uses the tested RTL presentation
adapter. Document format limitations instead of assuming every note app supports
browser bidi markup. Basic export needs no inference or Notion connection.

Notion follows an application-owned connection, explicit allowed page and a
reviewable preview/action. Prefer a narrow adapter over exposing broad write
tools to the teaching agent. Record intent before a write; an uncertain response
is reconciled by the stored identity/read-back where supported, not a blind page
creation retry. Do not claim the provider supports arbitrary idempotency keys.
Disconnected/permission-revoked states leave local notes available.
[Notion connection model](https://developers.notion.com/guides/mcp/overview).

Respect `/forget` and retention for local personal notes/exports. External notes
already exported are not silently deleted: explain their destination ownership
and provide explicit deletion instructions/action if supported. Do not copy full
paper text into export when selected short quotations and links are sufficient.

## Implementation, style and checks

Proposed `notes.py`, separate `exports.py`/Notion adapter and owner-scoped store
extension, split into small tasks. Reuse strict schema/version checking, fixed
formats and safe path allocation; no caller/model-controlled file path or shell.
The current notes route remains compatible during migration.

```powershell
.venv-win/Scripts/python.exe -m pytest tests/unit/test_study_service.py tests/unit/test_study_store.py -q -o cache_dir=tests/test_output/study-pytest --basetemp tests/test_output/notes-contract
```

Add future note/export tests for edit conflict, wrong owner/source, escaping,
missing images, duplicate/uncertain external writes and forget. Use stubbed
Notion HTTP first; an actual export needs the chosen connection/destination
and authorized action. Apply common lint/type and Arabic copy checks.

## Acceptance and decisions

SN-1: User notes, generated explanation and original quotation remain visibly
distinct, correctly versioned and editable without generating a new lesson.

SN-2: Previewed local export includes exactly the selected versions/refs and
is readable/copied correctly in Arabic/English; it contains no private tokens.

SN-3: Optional Notion export cannot write before its explicit action, duplicate
or unknown writes cannot create untracked pages, and a disconnected account
does not block ordinary study. Local deletion has documented external limits.

Deferred: owner chooses Notion page/connection at integration time. No personal
workspace changes or messages are initiated by this specification task.
