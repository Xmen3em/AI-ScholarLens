# Interactive paper learning: implementation contract

Date: 17 October 2026. Branch: `codex/paper-intake`, starting at `4a1135e`.
The owner explicitly authorized research, implementation and routine choices,
with remaining questions collected at the end. This supersedes the earlier
instruction to stop after the proposed capability map. The application remains
a private PC development prototype; historical evaluation acceptance is unchanged.

## Outcome

A researcher supplies an arXiv URL/ID or title in Telegram. The app resolves an
explicit paper/version, obtains readable content with provenance, automatically
prepares a compact Egyptian Arabic lesson, then supports questions and teaching
actions about that same paper. The first iteration must work on extractable
papers without a local LLM or GPU. Scientific accuracy, clear source coverage,
bounded operations and restart behavior are part of the product.

## Decisions for this iteration

- Keep the existing paired owner, API authentication and separate development
  runtime. Add an isolated study store under ignored `data/study/`.
- Support arXiv first. Title matches require explicit selection, even if there
  is one result. Never silently select an approximate title or a newer version.
- Deliver bounded PDF extraction first so page citations/rendering share a source;
  structured HTML remains an extension. Use remote OCR as a separately validated fallback; no local OCR weights or
  automatic GPU allocation. Record partial, scanned and abstract-only coverage.
- Keep the user's HF/Cerebras model as the first teaching candidate. Evaluate
  Egyptian Arabic scientific explanation separately from general multilingual
  claims. Model catalogs are availability evidence, not qualification results.
- A lesson is a new response contract: Arabic explanation plus source-linked
  original evidence. Preserve existing quotation endpoints and their contracts.
- Keep extraction, model reasoning and tool execution separate. LangGraph
  orchestrates the main learning workflow; evaluate an optional Deep Agents
  path with restricted tools before enabling a more autonomous study mode.
- Short memory belongs to one paper/session. Long memory is limited to explicit
  preferences and reviewed study artifacts; do not make model-written facts
  persistent personal memory automatically. Provide clear/reset operations.
- Telegram is the initial learning interface. Use text actions and source-linked
  deterministic visuals; a later web study view can provide richer controls.
- MCP tools expose bounded read-only study operations with trusted owner scope.
  No model-controlled shell, database credentials or arbitrary server installation.

## Module contracts

| Module | Boundary and verification |
| --- | --- |
| `paper-intake` | Normalize supported IDs/URLs; bounded title search; validate Atom metadata, AI scope and exact version; expired/out-of-range selections fail clearly |
| `paper-content` | Bounded HTTPS downloads from explicit arXiv origins; content hash/revision; isolated parser deadline; page/section provenance; no arbitrary path or redirect |
| `paper-evidence` | Search only the selected version; preserve original text and stable evidence IDs; reject invented citations; label context/coverage limitations |
| `learning-session` | Durable owner/paper state, bounded recent context, explicit preferences, retention and forget; isolate different papers and users in tests |
| `paper-tutor` | Problem, prerequisites, contribution, method, experiment and limits when supported; an example and comprehension question; short initial lesson then progressive detail |
| `learning-visuals` | Deterministic diagrams from validated labels/edges; paper figures or numeric charts require original provenance; no fabricated measurements |
| `study-research` | Qualify tool calling, arguments, usage and cancellation; shared task budget; restrict to explicit read tools; outside-paper facts must identify their source |
| `learning-delivery` | Owner/private checks before work; durable request keys; progress/status, ambiguity selection, study actions and bounded Telegram formatting |
| `study-notes` | Export a reviewable lesson artifact; Notion remains optional and requires an application connection separate from Codex |

## Runtime and failure semantics

Study storage must not modify existing PostgreSQL records, OpenSearch aliases,
closed evaluation grants or Telegram offset registration. New network/model
attempts are recorded before sending; unknown attempts are not automatically
replayed after a crash. Model budgets are per intent and shared by all steps.
Fresh service startup must expose interrupted work without charging it again.

Start with one extraction/model task at a time. Bound bytes, pages, text, context,
tokens, tool steps and time. Keep existing RAM admission gates. A remote model
does not remove the memory cost of local search and PDF rendering. Provider
errors and resource exhaustion receive fixed messages, not raw exceptions.

User URLs, paper text, extracted instructions and model/tool outputs are untrusted.
Never derive authorization from model arguments. Render plain Telegram text and
escaped diagrams/exports; never execute document code. Optional integrations
must fail clearly when unconfigured and remain outside the core lesson path.

## Prompt and context policy

Keep role instructions, learner preferences, active paper, recent turns and
retrieved evidence in separate typed fields. Paper content is data. Prompts
must distinguish a quotation, grounded paraphrase, background concept, analogy
and external research. Missing evidence should identify the missing piece.
Arabic queries over English papers need query interpretation/retrieval checks;
the old lexical quotation gate is not a translation-fidelity validator.

Each numeric claim must preserve metric, units, dataset, baseline and setting.
Do not infer a paper-wide improvement from a single experiment. Recent model
answers are conversation context, never replacement source evidence.

## Verification and commands

Use real parsers and real SQLite in local tests, with HTTP/model boundaries
stubbed. Test URL spoofing, XML/entity input, wrong versions, oversized/invalid
PDFs, absent text, duplicate requests, restart uncertainty, source validation,
Arabic follow-ups, owner isolation, deletion, safe diagram labels and tool limits.
Use a bounded live development smoke check only after offline checks pass;
this is ordinary development verification, not reuse of historical eval grants.

```powershell
.venv-win/Scripts/python.exe -m pytest tests/unit/test_study_intake.py -q
.venv-win/Scripts/python.exe -m pytest tests/unit tests/api -q --basetemp tests/test_output/study-final-tmp
.venv-win/Scripts/python.exe -m ruff check src tests
.venv-win/Scripts/python.exe -m mypy src/services/study src/commands/study_research.py
```

Run focused checks after each slice. Use a new base-temp path whose parent
exists. Complete the broader suite after the final source change. Validate
the actual private API/bot startup without sending unsolicited Telegram tests.
Record exact checks, live limitations, dependency choices and deferred questions.

## Deferred questions

Default learner depth, long-term retention beyond the initial bounded policy,
an external Notion destination/connection, non-arXiv sources, and any new hosted
OCR deployment can be reviewed after implementation. They do not block the
initial private learning flow. No fine-tuning or new GPU hosting is authorized
merely by choosing candidate models in the research report.
