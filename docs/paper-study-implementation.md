# From a paper-answer bot to a paper-learning workflow

17 October 2026 · implementation branch `codex/paper-intake`

The earlier prototype could explain a general concept or quote evidence from an
indexed collection. A researcher could not choose a new paper in chat and build
understanding across messages. This iteration adds that learning loop while
retaining the original collection, evaluation records and private owner setup.

The user authorized research followed by implementation, with questions deferred
until the review. The [contract](specs/paper-learning.md) records that scope.

## The implemented path

An admitted Telegram message becomes a durable owner-scoped intent before paid
work starts. A finite LangGraph resolves the paper, extracts readable source
blocks, constructs bounded context, teaches and validates. Title search pauses
for selection; it never silently picks the closest paper. A successful lesson
activates one explicit paper/version for subsequent questions.

| Layer | Implementation |
| --- | --- |
| Identity and title selection | `src/services/study/intake.py` |
| Public PDF acquisition and cache | `src/services/study/content.py` |
| Isolated text/render worker | `src/services/study/pdf_worker.py` |
| Exact source catalog | `src/services/study/evidence.py` |
| Durable jobs, attempts and session state | `src/services/study/store.py` |
| LangGraph workflow and commands | `src/services/study/service.py` |
| Egyptian prompts, output contracts and grounding review | `src/services/study/tutor.py` |
| Deterministic study map | `visuals.py`, `render_map.ps1` in the study package |
| Restricted source tools | `src/services/study/tools.py` |
| Optional LangChain/Deep Agents adapter | `src/services/study/deep.py` |
| Optional stdio MCP | `src/services/study/mcp_server.py` |
| Disabled remote OCR candidate | `src/services/study/ocr.py` |

The [user guide](paper-study-guide.md) describes commands, setup, retention and
what each mode actually does. The original indexed-paper answer route is
preserved as a separate behavior.

## Why extraction and teaching use different components

OCR answers “what is printed here?” A teacher explains what that content means.
Mixing those jobs makes it hard to distinguish an extraction error from an
explanation error. This implementation keeps source acquisition, extraction,
teaching and review separate.

PDFium was chosen for native extraction and bounded rendering without Torch or
model weights. Each parse runs in a subprocess with a stripped environment,
deadline and byte/page/text/pixel caps. Page/text/bitmap handles are explicitly
closed. This is process isolation, not an OS security sandbox. The worker cannot
guarantee scientific reading order, equation correctness or table reconstruction.
[PDFium API](https://pypdfium2.readthedocs.io/en/stable/python_api.html).

The initial source design also considered arXiv HTML. The delivered path uses
versioned PDF pages first so citation provenance and rendering share one source.
A structured HTML adapter remains an extension. Abstract-only material is never
silently presented as a full-paper lesson.

The [research record](research/paper-learning-20261017/DECISIONS.md) compares HF
OCR/vision and Arabic candidates. The owner's working GPT-OSS/Cerebras route
remains the text teacher. Egyptian wording is prompted and inspected separately
from scientific support; a model's language list does not establish teaching
quality. LightOnOCR-2 is an implemented remote candidate, not an enabled OCR
service. The newer LightOnOCR-3 card warrants a future figure/layout evaluation;
its checked metadata has no provider mapping.

## A live failure changed the citation design

The first live lesson returned plausible Arabic and schema-valid JSON, but the
model abbreviated quotations with ellipses. Literal source verification correctly
rejected those answers. Asking the model to reproduce every quotation was the
wrong boundary for a paraphrasing tutor.

The server now builds a catalog of exact contiguous source snippets. The model
selects known IDs; server code supplies the original quotation. Unknown IDs,
missing support and unsupported numeric literals are rejected. This preserves
exact source text while allowing Egyptian explanations.

Literal equality still does not establish entailment. Inspection of a real
results table exposed the risk of broad comparisons across metrics. A second,
bounded model call checks each paper section against its supplied evidence.
Unsupported sections become a fixed uncertainty message; there is no automatic
regeneration retry. Both calls share the intent's budget. The review is itself
fallible and does not replace a human scientific evaluation.

Follow-up experiments also showed the model repeating the whole first lesson
instead of answering a narrow question. Follow-ups now have a task-specific
instruction and a maximum of three focused sections. That is a product/context
decision, not a larger context window or a model switch.

## Memory stores conversation, not scientific truth

Application-owned SQLite persists jobs and validated artifacts. Recent dialogue
is restricted to one selected paper, four turns and a 24-hour window. Prompt
construction additionally truncates each prior answer. Explicit learner depth
is the only durable preference. Sources and prior generated answers remain
separate fields.

This follows LangGraph's distinction between thread-scoped state and persistent
cross-thread memory. The graph has no in-memory checkpointer advertised as
restart persistence. An interrupted outbound attempt remains consumed and is
not automatically resumed. [LangChain memory concepts](https://docs.langchain.com/oss/python/concepts/memory),
[LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

Payload retention, ten-paper owner history and a public-cache admission cap keep
storage bounded in the places carrying substantial content. `/forget` removes
study associations and dialogue, while deduplication/accounting tombstones
remain. It cannot reset the development smoke budget.

## Deep Agents is an optional harness with real boundaries

The isolated SDK experiment uses a LangChain `BaseChatModel` adapter over the
same bounded HF transport and attempt store. It preserves tool IDs, structured
arguments, provider tool-history fields and token usage. Real tool execution is
limited to inspecting/searching/reading the selected paper. Eight tool operations
and the shared per-intent model ceiling bound the worker.

The SDK includes filesystem and delegation features by default. This harness
disables the general-purpose subagent, hides built-in tools, narrows filesystem
middleware to its SDK-required virtual read tool, and independently rejects
every operation outside the source-tool allowlist. No host backend or shell is
provided. Automatic summarization is disabled for this short bounded workflow.
These execution checks matter because tool exclusions are model-facing
configuration, not an authorization boundary.
[Deep Agents customization](https://docs.langchain.com/oss/python/deepagents/customization),
[permissions](https://docs.langchain.com/oss/python/deepagents/permissions).

The latest SDK needs newer Pydantic dependencies than the baseline bot. An
attempt to synchronize it into the active Windows environment hit a locked
native file. Baseline Pydantic/core and LangChain-core were restored and checked;
the SDK now runs in a separate environment and a short-lived child process.
The bot does not import that SDK during ordinary operation.

MCP exposes the same source operations over optional local stdio. No arbitrary
URL, SQL, owner argument or shell is exposed. A dependency audit identified
vulnerabilities in the initially considered MCP 1.26.0; the delivered research
environment pins patched 1.30.0. No known vulnerabilities were reported by the
final audit of that pinned environment. This is an audit result on this date,
not a continuing guarantee.

## Measured development evidence

The smoke scope reserved **one immutable 12-attempt ceiling**, separate from all
historical evaluation grants. All twelve slots were used; all were valid
transport completions, including outputs subsequently rejected by content
checks. No uncertain attempt was automatically replayed.

| Inspected case | Attempts | Result |
| --- | ---: | --- |
| First lesson v1/v2, free-form quotes | 2 | Rejected quotation mismatches |
| Catalog lesson v3 | 1 | Completed; later content inspection motivated semantic review |
| Follow-up v1 | 1 | Rejected unsupported numeric/index literal |
| Lesson v4 | 1 | Rejected percentage formatting mismatch; numeric value handling corrected and unit context delegated to review |
| Lesson v5 with review | 2 | Completed; two unsupported sections withheld |
| Follow-up v2 | 1 | Rejected an unrequested, unsupported results claim |
| Focused follow-up v3 with review | 2 | Completed in Egyptian Arabic with verified source IDs |
| Actual Deep Agents / HF tool loop | 2 | Completed: one source search, then a cited Egyptian answer |
| Live OCR / unsupported-question smoke | 0 | Not run; ceiling exhausted; OCR stays disabled |

The public source was arXiv `2005.11401v4`. No private paper or unsolicited
Telegram test message was sent. Source/render artifacts, complete case outcomes
and attempt counts remain in ignored `data/study/`. Provider reasoning is not
published in reports or exposed to the user.

Offline checks use real PDFs, SQLite, the drawing backend and the optional SDK;
HTTP/model boundaries are stubbed. They cover owner isolation, URLs/versions,
invalid and oversized PDFs, cache reuse, source IDs/numbers, review redaction,
context/retention/forget, interrupted attempts, replay prevention, delivery
claims and tool boundaries. The final unit/API suite passed **1,467 tests**
with two existing deprecation warnings in823.74seconds on source `a358444`.
Mypy passed all151 source files, Ruff passed src/tests/research, and the separate
SDK/protocol environment passed five tests. The [checkpoint](session-checkpoint.md)
records proof locations and runtime status.

The Arabic map was rendered and visually inspected. Its arrows mean study
order. The native results page was inspected to assess a generated comparison.
These inspected examples are development data, not an unseen learning benchmark.

A Windows process-tree sample on this PC observed about **45.16 MiB** peak
working set for extracting that 19-page PDF, and **123.34 MiB** for importing the
optional Deep Agents SDK. The sample includes virtualenv launcher descendants;
it excludes the normal API, OS and other services. These single runs are not
universal resource bounds or a total system-RAM requirement. Startup/live
admission thresholds remain unchanged.

Cold startup initially imported the older SQL preview, API routers and evaluation
runners through shared helper imports. The helper bodies were moved intact into
small configuration/client modules, with lazy imports for the optional legacy
contracts. A fresh-process regression test checks that ordinary startup loads no
evaluation runners, SQL ORM or database API modules. In the same local probe,
private committed allocation for importing the launcher fell from **101.67 MiB
to 85.07 MiB**. This metric is private allocation, not total physical system RAM.

All existing Docker containers were already stopped when inspected. A one-time
WSL clean-cache reclamation during debugging recovered host headroom; no apps
were closed or containers restarted. It is not installed as an automatic memory
workaround. The normal launcher then passed its unchanged admission and started
the paired bot. Authenticated status and study delivery checks returned 200;
the same status request without a key returned 401. No inference or Telegram
test message was sent by these runtime checks.

A post-implementation concurrency review found that the general-question route
could overlap initial paper preparation. Regression tests reproduced the gap.
Both API paths now share a busy guard, including the period before a paper is
active. Empty commands do not start work, and photo delivery requires a valid
message acknowledgement. The final full-suite result includes these fixes.

Additional failure-path checks cover a visible Egyptian API/quota error message
and no duplicate message after uncertain Telegram delivery. The OCR candidate
now follows the publisher's image-only input and preserves table/equation line
breaks. Metadata keeps a bounded author list with its full count instead of
rejecting a paper solely because it has more than thirty authors.

## What remains a separate decision

No deployment, new GPU endpoint, public multi-user access or fine-tuning was
performed. Native-text arXiv study is the working initial path. Scanned papers,
reliable figure/equation interpretation, external web research, a richer web
study view, scored learning progress and application-level Notion export remain
extensions. The [review note](paper-study-review.ar.md) collects the user's
remaining choices without blocking this implementation.

The [next evaluation design](paper-study-evaluation.md) covers scientific support,
Egyptian teaching, learning interaction, OCR, memory/tool isolation and complete
response latency. It authorizes no additional inference.
