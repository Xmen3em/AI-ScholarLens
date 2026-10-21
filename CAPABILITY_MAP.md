# Capability map: interactive paper learning

**Whole implementation planning — 21 October 2026.** The owner requested a
complete plan and specifications using the engineering skills. Retain the nine
stable module IDs below. Their detailed contracts are now indexed here and in
the [whole-app specification](docs/specs/researcher-app.md). The existing
`docs/specs/` convention is retained rather than creating duplicate root specs.
This request covers preparing the map, specifications and plan together; this
change does not activate features, inference, external writes or deployment.

| Module id | Current baseline | Detailed specification |
| --- | --- | --- |
| `paper-intake` | Versioned arXiv resolution and explicit title selection | [Paper identity and intake](docs/specs/paper-intake.md) |
| `paper-content` | Isolated native PDF extraction; OCR adapter disabled | [Structured content and OCR](docs/specs/paper-content.md) |
| `paper-evidence` | Exact snippets and bounded selection; scientific validity still needs work | [Evidence and claims](docs/specs/paper-evidence.md) |
| `learning-session` | Owner SQLite state, four recent turns, explicit depth, forget | [Learning state and memory](docs/specs/learning-session.md) |
| `paper-tutor` | Egyptian lessons/follow-ups; real scientific mistakes documented | [Interactive teaching](docs/specs/paper-tutor.md) |
| `learning-visuals` | Reading-order map; method visuals remain planned | [Visual teaching](docs/specs/learning-visuals.md) |
| `study-research` | Isolated Deep Agents/MCP; live Deep failure unresolved | [Bounded research](docs/specs/study-research.md) |
| `learning-delivery` | Private Telegram and local API; rich study view planned | [Telegram and study workspace](docs/specs/learning-delivery.md) |
| `study-notes` | `/notes` lesson/quote output; Notion export unconnected | [Notes and export](docs/specs/study-notes.md) |

Shared [Arabic reading](docs/specs/arabic-reading.md), model/context/runtime rules
and release evidence in the whole-app spec apply to these modules; they are not
new services. Detailed build order and checkpoints are in
[the plan](tasks/plan.md#whole-app-implementation--21-october-2026) and
[the tasks](tasks/todo.md#whole-app-implementation--task-index).
Historical 17 October context below explains the implemented starting point;
the new specs distinguish existing behavior from each proposed extension.

## Historical 17 October baseline

**Execution authorized — 17 October 2026.** The user requested research followed
by implementation, autonomous routine decisions, and questions deferred until
the implementation report. This authorizes the next iteration using the module
boundaries below; implementation decisions and verification are recorded in the
[iteration specification](docs/specs/paper-learning.md). Earlier review gates
are superseded by that explicit instruction, not silently bypassed.
Current code is preserved at `a7a0746` on `codex/telegram-prototype-checkpoint`.
Documentation and this proposal live on `codex/paper-learning-plan`.

**Implementation update:** the initial arXiv/PDF learning loop, Egyptian lessons,
paper context, study maps, restricted Deep Agents and optional stdio MCP are now
implemented on `codex/paper-intake`. See the [measured implementation](docs/paper-study-implementation.md).
OCR qualification, source figure/equation interpretation, external research and
application Notion export remain extensions. The map below retains the broader
intended scope; it is not a claim that every proposed capability shipped.

**Visual-learning research update —21October2026:** the existing`learning-visuals`
module now has a[proposed implementation contract](docs/specs/learning-visuals.md),
[Kimi/model/agent research](docs/research/visual-learning-20261021/DECISIONS.md),
and an[Egyptian overview](docs/visual-learning-next.ar.md). The next offline slice
is a source-linked RAG method explainer; interactive mechanisms and charts are
not claimed as delivered by the current reading-order map.

## Product promise

الباحث يبعت ورقة، والتطبيق يبدأ يساعده يفهمها بالمصري: شرح واضح من الدليل،
رسمة مناسبة، مثال، وسؤال يكشف هو فهم إيه ولسه محتاج إيه.

The next iteration centers on a **user-selected paper**. Weekly discovery and
digest delivery are outside this iteration. Existing batch ingestion remains
available as infrastructure; this documentation does not change its schedule.

## Working assumptions

- First user remains the existing private Telegram owner on the current PC.
- Teaching defaults to Egyptian Arabic; preserve English terminology, titles,
  code and mathematical notation alongside accessible Arabic explanation.
- Deliver a useful initial lesson after ingestion without requiring the user
  to invent the first question. Offer optional depth/goal selection afterward.
- Keep hosted reasoning. Choose a new HF extraction/OCR model later, after
  measuring representative papers and deployment requirements.
- Use the existing LangGraph/evidence foundations. Evaluate Deep Agents for
  longer study tasks; its integration and model compatibility are unproven.
- Notion is an optional study destination. It must not be required to learn.

## Proposed modules

Dependency arrows mean consumer → required provider. Provider interfaces live
in the module specifications linked above. Optional reports/artifacts are passed
by the delivery/workflow coordinator; providers do not import their consumers.

| Stable module id | Responsibility | Depends on |
| --- | --- | --- |
| `paper-intake` | Resolve URL, title or arXiv ID; disambiguate titles; record canonical version and availability | Existing owner authentication |
| `paper-content` | Queued acquisition, structured extraction, OCR fallback and source/page provenance | `paper-intake` |
| `paper-evidence` | Paper-scoped retrieval and traceable support for claims, figures, equations and results | `paper-content` |
| `learning-session` | Owner/paper/version context, learning preferences, progress and deletion lifecycle | `paper-intake` |
| `paper-tutor` | Automatic first lesson, grounded Egyptian Arabic explanations and guided follow-ups | `paper-evidence`, `learning-session` |
| `learning-visuals` | Source-linked concept diagrams, figure explanations and charts from verified numeric data | `paper-evidence` |
| `study-research` | Bounded external research and Deep Agents compatibility experiment | `paper-evidence` |
| `learning-delivery` | Telegram interaction controls; later web study view for rich visuals | `paper-tutor`; optional `learning-visuals`, `study-research` |
| `study-notes` | Preview and export a study artifact; optional private Notion destination | `paper-tutor`; optional `learning-visuals` |

```mermaid
flowchart LR
    I[paper-intake] --> C[paper-content]
    I --> S[learning-session]
    C --> E[paper-evidence]
    E --> T[paper-tutor]
    S --> T
    E --> V[learning-visuals]
    E --> R[study-research]
    T --> D[learning-delivery]
    V -. optional .-> D
    R -. optional .-> D
    T --> N[study-notes]
    V -. optional .-> N
```

The diagram shows **build/data flow from provider to consumer**, the reverse
of the dependency notation in the table. There are no circular dependencies.

## Build order to discuss

1. `paper-intake` → `paper-content` → `paper-evidence`, with `learning-session`
   following identity resolution. Verify one explicit paper and its version.
2. `paper-tutor` plus the first Telegram slice of `learning-delivery`: a short
   lesson and a follow-up anchored to that same paper.
3. `learning-visuals`: deterministic diagrams first, inspectable quantitative
   charts next; integrate into delivery after source linkage is reliable.
4. `study-research`: evaluate tool calling and a bounded Deep Agents workflow
   before adding tools to ordinary lessons. `study-notes` can follow a stable
   lesson artifact independently.
5. A richer web study view and, only later, a separately designed multi-user mode.

The first complete learning slice should work without external search, Notion,
or an OCR model download when the paper already has reliable extractable text.

## Proposed first lesson

This is a teaching outline, not a promise that every paper contains every item:

1. «الورقة بتحاول تحل إيه؟» — problem and why it matters.
2. «محتاج تعرف إيه قبلها؟» — two or three prerequisites, with optional help.
3. «الفكرة الجديدة إيه؟» — contribution and a source-linked method sketch.
4. «جرّبوها إزاي؟» — one central experiment with metric, data and baseline.
5. «نقدر نستنتج إيه، وإيه حدود الكلام؟» — evidence, limitations and uncertainty.
6. One small example or labeled analogy, then one comprehension question.

Show a short orientation first; reveal deeper sections on demand. Use separate
labels for paper claims, background explanation, teaching analogies, and outside
research. Do not present generated Arabic paraphrases as exact source quotes.

## Historical decisions and remaining qualification

- The initial arXiv source/version/selection policy is implemented. Broader
  publisher sources and authenticated PDF upload remain later explicit slices.
- Extraction/OCR model, host/provider availability, page limits, quality checks,
  price and measured peak memory. No model is selected here.
- Keep the selected-paper job's current four-attempt ceiling. Any different
  experimental ceiling needs its own applicable authorization; legacy question
  budgets do not fund study/visual jobs.
- Current SQLite session/retention rules are implemented; persistent study
  progress and deletion of new artifacts need the new session contract.
- Whether the first visuals arrive as Telegram images or through a web study
  view; recommend images/buttons first, web interactivity afterward.
- An Arabic/English terminology rubric and fresh unseen paper-learning examples
  to assess factuality, explanation quality, follow-up continuity and comprehension.

See [research and tool choices](docs/paper-learning-research.md) and the detailed
module contracts above. Remaining provider/hosting/Notion decisions are recorded
at the end of the whole-app plan; they do not block offline implementation.
