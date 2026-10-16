# Engineering decisions for the paper-learning iteration

Checked 17 October 2026. Sources below are official documentation, publisher
model cards and public package/model metadata. [models.json](models.json)
records exact Hub revisions and provider mappings. Availability can change;
this snapshot is not an inference or teaching-quality qualification.

## Models: separate extraction from teaching

| Candidate | Verified catalog facts | Decision |
| --- | --- | --- |
| LightOnOCR-2-1B | Apache 2.0; HF lists a live Featherless conversational route; card emphasizes scientific text/math; listed languages do not include Arabic | Preferred remote OCR candidate for English AI papers; qualify image input and extraction before enabling |
| Granite Docling 258M | Apache 2.0; English listed; no HF provider mapping | Useful structured-extraction reference; do not promise an existing hosted route |
| PaddleOCR-VL-1.5 | Apache 2.0; multilingual; no HF provider mapping | Candidate for a later separately hosted extraction worker |
| GLM-OCR | MIT; its listed HF provider currently reports error | Do not select an unavailable route |
| Qwen3-VL-8B | Apache 2.0; Featherless live, Novita error | General vision alternative requiring scientific extraction evaluation |
| Qwen3.5-35B-A3B | Apache 2.0; Novita and DeepInfra live | Candidate for combined multilingual/vision tasks, not a proven Egyptian tutor |
| GPT-OSS-120B | Apache 2.0; current Cerebras route live | Keep the owner's working teaching candidate and test Egyptian Arabic prompts |
| Nile-Chat-4B | Egyptian Arabic/Arabizi specialization; Gemma terms; no HF provider mapping | Valuable dialect comparator; no new local weights or hosting for this PC iteration |
| Jais-2 8B/70B Chat | Apache 2.0 metadata; no HF provider mapping; public card requests returned 401 | Do not claim a read/qualified model card or available hosted integration |
| Aya Expanse 32B | Arabic listed; Cohere route live; CC BY-NC 4.0 metadata | Keep as a research comparator, not the default model for this MIT project |

The [LightOn card](https://huggingface.co/lightonai/LightOnOCR-2-1B) describes a
1B document-to-text model with math and multicolumn support. Those are author
claims, not measurements on ScholarLens papers. The [Nile card](https://huggingface.co/MBZUAI-Paris/Nile-Chat-4B)
specifically describes Egyptian Arabic and Arabizi, but dialect fluency alone
does not demonstrate scientific reasoning, citation fidelity or tool use.
[Qwen's card](https://huggingface.co/Qwen/Qwen3.5-35B-A3B) describes broad
language/vision capability; we still need task-specific evaluation.

Use the same reviewed source passages and tasks when comparing teaching
candidates: explain a method, distinguish an analogy, preserve a numerical
setting, answer an Arabic follow-up, and acknowledge missing evidence. Assess
natural Egyptian wording separately from Arabic script detection. No training
or fine-tuning is justified before a prompting/retrieval baseline is measured.

## Extraction and memory on this PC

Use native structured text first. Prefer arXiv HTML where it reliably preserves
sections and math, otherwise extract PDF pages. Native PDF extraction does not
recover scanned text; OCR is a separate operation.
[PDF extraction limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

Choose PDFium via `pypdfium2` for a small worker that can both extract page text
and render bounded images for remote OCR. Run it in an isolated subprocess with
byte/page/text/pixel caps and a deadline. This avoids installing Torch or OCR
weights in the bot process. Keep the existing Docling/Airflow pipeline intact.
[PDFium helper API](https://pypdfium2.readthedocs.io/en/stable/python_api.html).

Cache public source extraction by canonical version, content hash and parser
revision. Separate those sources from user/session state. Retain bounded recent
turns for continuity, with expiry and explicit forget; persist long-term learning
preferences only when explicitly selected. Never use prior model answers as
primary evidence. [Memory concepts](https://docs.langchain.com/oss/python/concepts/memory).

LangGraph distinguishes thread-scoped checkpoints from cross-thread stores.
For this bounded first workflow, durable application-owned job/session records
can hold validated artifacts and failure state. Do not blindly resume an
uncertain paid call from a checkpoint. If longer resumable graphs are added,
use a real persistent checkpointer with retention, not `InMemorySaver` labeled
as restart persistence. [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

## Context and prompts

Keep instructions, trusted owner/paper identity, preferences, recent dialogue
and source evidence separate. Select small relevant evidence blocks rather
than paste every paper and all chat history into a prompt. Record source and
prompt revisions. [Context engineering](https://docs.langchain.com/oss/python/langchain/context-engineering).

The tutor prompt should ask for Egyptian Arabic, retain English terms, teach
prerequisites, and use progressive detail. Require original evidence references
for paper claims; distinguish background and analogies. Validate response shape,
known source IDs, word/character bounds and numeric context. Mechanical checks
do not prove semantic entailment or dialect quality; those need content review.

## LangChain, LangGraph and Deep Agents

LangGraph remains the explicit main workflow: source acquisition, evidence
selection, teaching and validation are independently testable stages. LangChain
supplies chat/tool interfaces for an optional richer research path. Deep Agents
is a harness built on these foundations, not a replacement source database.
[Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview).

Deep Agents requires a tool-calling LangChain chat model. A strict completion
JSON response does not satisfy that interface. A dedicated adapter must handle
tool calls, usage, cancellation, argument validation and a shared budget before
using the HF/Cerebras route in that harness.
[Model interface](https://docs.langchain.com/oss/python/deepagents/models).

The current harness includes filesystem/context middleware and a general-purpose
subagent by default. Configure the exact pinned SDK, disable unnecessary tools
and delegation, and supply only bounded read tools. Context offloading is useful
for long work, but can also add prompt overhead to short lessons.
[Customization](https://docs.langchain.com/oss/python/deepagents/customization).

Filesystem permission rules do not authorize custom tools or MCP operations.
Backend-specific rules also do not sandbox arbitrary shell execution. Avoid a
host shell; enforce scope, limits and authorization inside each actual tool.
[Permissions](https://docs.langchain.com/oss/python/deepagents/permissions),
[backends](https://docs.langchain.com/oss/python/deepagents/backends).

## MCP and execution tools

Expose the same bounded study operations as local read-only tools: inspect the
active source, retrieve a section, search its evidence and read a lesson.
Trusted owner scope comes from server configuration, never a model argument.
Do not give a model SQL, arbitrary URLs, a host shell or environment access.

Current LangChain documentation uses the beta `langchain.mcp.MCPAdapter` in
`langchain[mcp]>=1.4.0`, backed by FastMCP. Older examples using
`langchain-mcp-adapters` are not interchangeable current APIs. Pin and test the
chosen integration instead of mixing snippets.
[Current LangChain MCP docs](https://docs.langchain.com/oss/python/langchain/mcp).

The standalone Python MCP SDK also has a newer 2.x line. A compatible pinned
1.x server can be an explicit optional component for local stdio use; no server
is automatically installed into the user's desktop configuration. An app's
Notion connection remains separate from the Codex Notion plugin.
[Python SDK](https://github.com/modelcontextprotocol/python-sdk).

## Resource and cost controls

Keep the existing private-runtime RAM admission and live floors. Serialize heavy
work. New study intents need durable admission and attempt accounting, including
failed/unknown requests. Limit development smoke checks explicitly; never reuse
old batch grants. Avoid automatic retries of inference and automatic resume after
an unknown result. No new GPU service, subscription or large model download is
needed for the initial native-text learning path.

## Evidence and remaining validation

The HF connector's model-search tool returned unavailable, so public official
Hub HTTP metadata and author cards were used. Research HTML/Markdown snapshots
and hashes are retained locally under ignored test output. Restricted cards are
marked as unread rather than inferred from a title. Verify the actual selected
provider/model route before activating OCR. A working implementation and a
bounded smoke check are development evidence, not a replacement for an unseen
learning-quality benchmark or a human Egyptian Arabic review.
