# ScholarLens: study a paper in Egyptian Arabic

Implemented on `codex/paper-intake`, 17 October 2026. This is a private PC
development workflow. The earlier paper-answer holdout remains unaccepted;
these development checks do not establish teaching accuracy or a public release.

## Start studying

Use your paired private bot after starting the configured development runtime:

```powershell
.\Telegram.ps1
# After changing source:
.\Telegram.ps1 -Restart
```

In Telegram:

```text
/paper https://arxiv.org/abs/2005.11401v4
```

An arXiv ID or URL sent alone also works. An unversioned ID resolves to the
explicit version returned by arXiv; that version appears in every source link.
To find a title:

```text
/paper Attention Is All You Need
/choose 1
```

Title matches always require selection, including a single match. When no paper
is active, a plain title also starts title search; explicit general questions
continue to the concept assistant. With an active paper, ordinary text is a
follow-up about that paper. Use `/paper` to switch by title.

The first lesson covers the problem, prerequisites, contribution, method, one
experiment when the evidence supports it, limitations, a labeled analogy and a
comprehension question. Unsupported parts are withheld or marked unavailable.
This is a lesson from selected passages, not a claim to have verified every
equation, table or finding in the document.

Current acquisition limits are **20 MiB per PDF and 45 pages**. Larger documents
are refused rather than silently treated as complete. Metadata retains up to
30 author names and records the full author count, so a long author list does
not reject an otherwise supported paper.

Try:

```text
بسّطها
اشرح الفرق بين retriever و generator بمثال بسيط
اشرح الطريقة
اختبر فهمي
```

The keyboard offers these study actions. A quiz is conversational: the model asks
a question and uses the recent dialogue for follow-up. There is no scored exam,
mastery certificate or persistent learning score.

| Command | Result |
| --- | --- |
| `/study` | Current paper/version and how to continue |
| `/notes` | Initial lesson plus the original supporting excerpts, suitable for reviewing/copying into notes |
| `/level beginner` | Simple explanations; default |
| `/level researcher` | More technical explanations |
| `/quiz` | Ask one comprehension question without revealing the answer immediately |
| `/deep <question>` | Optional Deep Agents research within the current paper |
| `/forget` | Clear active paper, recent dialogue, preferences and owner study artifacts |

The drawing is a **study reading order**, with source block references. It does
not invent causal relationships, scientific figures or experimental charts.
Arabic shaping uses Pillow/libraqm where available and a fixed Windows GDI
drawing worker on this PC. Model text is JSON data; it is never drawing code.

## What runs locally

The normal API and bot share one process on `127.0.0.1:8002`. Text generation uses
HF/Cerebras. arXiv study uses public PDFs, a small isolated PDFium worker and
SQLite; it does not query OpenSearch or load embeddings. The older collection
answer route still uses OpenSearch. No local LLM/OCR weights were installed.

Startup retains the 1,024 MiB free-host-RAM requirement; generation retains the
600 MiB floor. Extraction/model work is serialized. The optional research worker
runs only during `/deep`, then exits. These choices reduce local demand but
cannot guarantee headroom while unrelated programs consume RAM.

Ordinary startup uses thin clients and configuration helpers. The old SQL preview,
collection API routers and historical evaluation execution modules load only in
the modes that need them. The existing loopback/configuration checks are shared;
their validation logic was moved intact.

Each study intent allows at most four model attempts across its steps, including
failed/unknown attempts. Normal supported lessons and follow-ups use generation
plus one grounding review. Tool research shares the same ceiling. The existing
API request/generation quotas also apply; commands through the message endpoint
consume its generation quota even when they do not call a model.

An admitted request is not automatically retried. On restart, unfinished work is
marked interrupted. A delivery is claimed before sending, so an uncertain
Telegram acknowledgement is not replayed. `/notes` retrieves the initial lesson;
send a fresh question to request new work. Do not delete the paired offset files.

## Evidence, context and retention

Source identity includes canonical arXiv version, PDF SHA-256, parser revision,
page numbers and stable block IDs. The model chooses IDs from an evidence
catalog. The server copies the exact original excerpts, checks IDs and numeric
literals, then runs a separate model review of factual support and comparisons.
That review can replace unsupported sections with an explicit uncertainty.
Neither mechanical validation nor a second LLM proves semantic correctness.

Recent context is limited to four question/answer pairs for one selected paper,
expires after 24 hours, and is truncated further when building a prompt. Old
assistant answers are labeled dialogue, never primary source evidence. Only an
explicit `/level` selection changes the persistent learning preference.

Owner study associations retain at most ten papers. Completed job question/result
payloads older than 30 days are redacted on the next admission; accounting and
deduplication tombstones remain. `/forget` clears associations and dialogue sooner,
but preserves those tombstones and the public-source cache. Public PDF cache
admission is capped at 256 MiB; it refuses additional acquisition when full.
This iteration does not automatically delete original platform papers or data.

## Optional Deep Agents and MCP

The current Deep Agents SDK requires a newer Pydantic dependency stack than the
baseline bot. Keep the experiment in its own environment:

```powershell
uv venv .venv-study-research --python 3.12
uv pip install --python .venv-study-research/Scripts/python.exe -r research/requirements.lock
.venv-study-research/Scripts/python.exe -m unittest discover -s research/tests -v
.\Telegram.ps1 -Restart
```

`/deep` is available when that interpreter exists. The worker uses Deep Agents
0.7.28, LangChain 1.4.6, LangGraph 1.2.15 and the shared bounded HF transport.
It can inspect the current paper, search evidence and read named blocks. It has
no host filesystem, shell, external web search or subagent delegation. Provider
tool history and usage are preserved; owner identity comes from configuration.
The ordinary lesson path remains available without this environment.

The optional MCP server uses patched `mcp==1.30.0`, local stdio only:

```powershell
.venv-study-research/Scripts/python.exe -m src.commands.study_mcp
# Explicitly start it for a local MCP client:
.venv-study-research/Scripts/python.exe -m src.commands.study_mcp --execute
```

Default mode checks configuration without starting a server. Four read-only
tools expose current-paper metadata, evidence search, block reading and saved
notes. There are no caller-provided owner IDs or paths. Nothing is automatically
installed into Codex, Telegram, or another desktop client's MCP configuration.

## OCR and external integrations

Native PDF extraction is implemented and tested. Scanned pages are detected.
The opt-in LightOnOCR-2-1B/Featherless adapter renders a bounded page, shares the
job budget, and records image/text hashes and OCR provenance. **It is not enabled
in the bot and has not received a live inference qualification.** Its HTTP,
limits, error and accounting behavior is tested locally. It can process at most
two missing pages in one intent; OCR content remains labeled partial.
Its request follows the publisher's image-only shape, and transcription preserves
line breaks in tables and equations. This is still an unqualified candidate.

The newer LightOnOCR-3-4B is an additional extraction/figure-grounding research
candidate, but the checked HF metadata lists no inference provider for it.
No GPU endpoint or subscription was created. See the [model decisions](research/paper-learning-20261017/DECISIONS.md).

Notion export is not connected to the application. The Codex Notion plugin does
not grant the running bot a Notion token. `/notes` provides a reviewable text
artifact now; destination, permissions and export behavior can be decided later.

## Review this iteration

Read the [implementation and measured results](paper-study-implementation.md),
[engineering research](research/paper-learning-20261017/DECISIONS.md) and
[implementation contract](specs/paper-learning.md). Review particularly the
scientific wording, Egyptian terminology, the usefulness of withheld sections,
and what a learner should see after answering a comprehension question.
