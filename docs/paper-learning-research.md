# Research notes: an Egyptian Arabic paper tutor

Research date: **16 October 2026**. Status: **proposal**, with no runtime,
dependency, model-selection or inference-budget changes. This supports the
[capability map](../CAPABILITY_MAP.md); it is not a module specification.

## What the current prototype establishes

The owner-supplied transcript shows successful general explanations and cited
answers for a dataset, SpeechGym failures and TTPO. It also shows insufficient
evidence for some valid questions. These are useful manual observations, not a
representative learning evaluation. The [formal holdout](hf-cerebras-paced-holdout-result.md)
remains rejected. No raw chat transcript or private account data is included here.

The current graph retrieves evidence and renders quotations. It does not yet
track an active paper or learner progress. The development HF client validates
structured completion content; that does not establish a tool-calling chat
adapter for Deep Agents. Read [the implementation story](build-story.md) for
current boundaries.

The existing question/quotation contract also cannot simply become a lesson:
questions are bounded to 500 characters and replies use constrained evidence
selection. A lesson needs its own artifact and source mapping, with a reviewed
budget. Egyptian Arabic questions against English papers need a cross-language
retrieval check. The current lexical evidence gate is already a source of false
abstentions; matching source words is insufficient for evaluating translated
teaching claims. Preserve exact source attribution while testing a separate
paper-grounded explanation policy on fresh examples.

## Deep Agents: what it offers and what still needs proof

Deep Agents is a separate agent harness using LangGraph. It offers tools,
context management, filesystem backends and subagents. Task planning is opt-in
in current documentation, so older examples should not be copied unchanged.
This makes it a candidate for a bounded study task, rather than evidence that
it will improve teaching quality. [Official overview](https://docs.langchain.com/oss/python/deepagents/overview).

Its model interface requires a LangChain chat model supporting tool calling.
The existing `openai/gpt-oss-120b:cerebras` route is the starting candidate, not
a verified Deep Agents integration. LangChain's `provider:model` syntax and HF's
`model:provider` suffix have different meanings; never substitute the strings
blindly. [Model requirements](https://docs.langchain.com/oss/python/deepagents/models).

**Proposed compatibility experiment, before adoption:** pin a candidate package
version; wrap the chosen HF route; make a bounded read-only tool call; validate
arguments and tool results; check structured output, usage, errors, cancellation,
context size and Arabic explanations. All child calls must share the parent
budget. The current structured-output checks are not this experiment.
[HF function-calling guide](https://huggingface.co/docs/inference-providers/guides/function-calling).

Start with one coordinator and explicit tools. Only add a method analyst,
experiment analyst or teaching reviewer when a measured task benefits. Isolated
subagent context can separate work, but it cannot certify the facts returned.
Keep source references in each report. [Subagent documentation](https://docs.langchain.com/oss/python/deepagents/subagents).

Long tasks may need scratch artifacts and resumable state. Store paper sources,
learner/session state and temporary agent notes separately. Choose a backend
and retention policy for each purpose; a filesystem abstraction is not a
replacement for the existing corpus or access controls.
[Backend documentation](https://docs.langchain.com/oss/python/deepagents/backends).

## Paper acquisition and extraction

Recommend starting with arXiv URLs/IDs and title resolution. An ambiguous title
must produce candidates for the user to select. Preserve canonical identity,
version, download hash and extraction revision. Other publisher URLs should be
separate support work, including access and format limitations.

**Proposed extraction order:** reuse reliable structured text when available;
otherwise parse the PDF; request OCR for pages that need it. Existing Docling
support is a baseline to evaluate. Docling documents OCR engines and a separate
vision-language pipeline; the repository's installed parser must be checked
against those capabilities before changing it.
[Docling OCR](https://docling-project.github.io/docling/concepts/ocr/),
[VLM example](https://docling-project.github.io/docling/examples/minimal_vlm_pipeline/).

No new OCR model is selected. Later HF candidate review should assess:

| Dimension | Evidence needed |
| --- | --- |
| Scientific structure | Columns, section order, captions, formulas and table cells on reviewed pages |
| Provenance | Page and region references that survive retrieval and rendering |
| Deployment | Exact model/provider availability, request format, limits and license |
| Resource cost | Measured peak RAM/VRAM, time per page and hosted cost when applicable |
| Failure behavior | Scanned pages, missing text, corrupted PDFs and extraction-quality flags |

A model being on the Hub does not prove an inference provider serves it. Verify
the exact route and supported input task later. The existing text-generation
route is not an OCR deployment. [HF image-text-to-text documentation](https://huggingface.co/docs/inference-providers/tasks/image-text-to-text).

## Teaching design in Egyptian Arabic

The lesson should move through **problem → idea → method → evidence → limits**.
Default to a concise first explanation, then offer depth. Teach an unfamiliar
prerequisite before an equation that depends on it. Keep scientific terminology
searchable: «الـbaseline، يعني المقارنة اللي بنقيس عليها».

Example wording only, without claiming a result from a particular paper:

> «بص، خلّينا الأول نحدد الباحثين بيحاولوا يحلّوا إيه. بعد كده نمشي في
> الطريقة خطوة خطوة، ونشوف التجربة فعلًا بتثبت إيه. تحب نبدأ بمثال بسيط؟»

Preserve the original claim and its source next to the explanation. For numeric
results, include metric, units, dataset/split, baseline and experimental setting;
the same model can have different improvements in different experiments.
Do not translate a paraphrase into something presented as an exact quotation.

Follow-up controls can include «بسّطها»، «مثال»، «اشرح المعادلة»، «ليه كده؟»
and «اختبر فهمي». Start with one diagnostic question and useful feedback, then
adapt. Count comprehension and correction quality, not response length, as
signals of whether the teaching helps.

## Visuals and delivery

| Need | Proposed first tool | Delivery |
| --- | --- | --- |
| Method or concept map | Validated Mermaid or deterministic SVG | Rendered image in Telegram; source-linked study page later |
| A paper's figure | Original crop, caption and accessible Arabic explanation | Source page/figure reference; no invented reconstruction |
| Quantitative comparison | Plotting from verified table values | Chart with units, baseline and inspectable input data |
| Equation walkthrough | Typeset equation plus a worked example | Short steps with English/LTR notation preserved |
| Interactive exploration | A small web study view | Link from Telegram; accessible RTL controls and reset |

A static picture in Telegram is not an interactive simulation. Start with
images and callback buttons. For rich controls, consider an ordinary web view
or Telegram Mini App after the lesson artifact is stable. Mini Apps are a
distinct web application surface with their own integration requirements.
[Telegram Mini Apps documentation](https://core.telegram.org/bots/webapps).

Generated illustrations can help with analogies, but they should not supply
experimental data or replace faithful method diagrams. No image-model choice
is needed for the first deterministic visual slice.

## Research tools, MCP and Notion

Prefer the paper and its author-linked code/data first. Add primary-source web
research only when it resolves a concrete gap. Tag every added source as outside
the paper. Search, fetch and source lookup should be read-only and bounded.
An agent should not browse indefinitely to manufacture a complete-looking lesson.

MCP is one way to expose tools. Evaluate exact tool contracts, authentication,
limits and provenance instead of installing many servers. Notion's hosted MCP
provides a connection for AI tools, but the user's Codex connection is not
automatically available to the bot running on their PC.
[Notion MCP overview](https://developers.notion.com/guides/mcp/overview).

The user explicitly requested a Notion study page for this research now. A
private draft can link their existing Deep Agents notes. Future app exports
need their own connection and a preview, destination and retry-safe identity.
Learning should still work if Notion is disconnected.

## Memory, failure handling and quality

Keep hosted inference and a single extraction worker initially. Reuse extraction
results by paper/version/hash, process bounded pages, and serialize heavy work.
Measure actual memory for the selected parser before setting new limits. Do not
promise that remote generation alone solves Docker or OCR memory consumption.
The current 1,024/600 MiB development gates remain unchanged by this proposal.

Plan progress states such as resolving, acquiring, extracting, preparing a lesson,
ready and failed. Handle duplicates, cancellation, unavailable full text,
low-quality extraction, provider errors and partial lessons explicitly. An
abstract-only explanation must identify its limited source coverage.

Before accepting a learning slice, use fresh papers and questions with Arabic
paraphrases, continuation references, missing evidence and numeric ambiguity.
Review citations, translation fidelity, scientific meaning, diagram accuracy,
teaching clarity and comprehension feedback. Include owner/paper isolation,
untrusted-document instructions, URL redirects and bounded resource use in
verification. The old inspected holdout remains historical evidence.

## Next review

Review the module boundaries in [CAPABILITY_MAP.md](../CAPABILITY_MAP.md), then
specify `paper-intake` first. Defer model purchases, OCR downloads, dependency
changes and an autonomous research loop until their concrete requirements and
tests are clear. This research session used documentation tools, not model
inference or a new paid evaluation grant.
