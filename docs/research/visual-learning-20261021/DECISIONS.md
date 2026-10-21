# Visual paper learning: research and implementation decisions

Checked 21 October 2026. This is public-source research and a proposed implementation
sequence. No inference, training, local model weights, new subscription, runtime
change or Telegram test message was initiated. The unresolved Deep diagnosis and
its pending eight-call request remain separate; that request cannot fund visual
model experiments. Metadata and cached-source hashes are in [models.json](models.json)
and [sources.json](sources.json).

## What “like Kimi” means here

Moonshot's K3 material describes native visual understanding, coding, interactive
research presentations, and Widgets/Dashboard in Kimi Work. These product features
combine the model with tools, execution and a presentation layer. They do not show
that a raw model completion is already a working ScholarLens widget. K3 is the
newer checked family member; K2.5 is not described here as the latest model.
[K3 publisher overview](https://www.kimi.com/en/blog/kimi-k3),
[K2.6 design examples](https://www.kimi.com/en/blog/kimi-k2-6).

Our design inference: reproduce the useful learning interaction—inspect a method,
step through a mechanism, ask about a component and inspect its source—using a
bounded application workflow. Choose a model after evaluating scientific fidelity,
Egyptian Arabic and its actual hosted route. Product demos and coding scores do
not qualify scientific teaching.

## Model shortlist and hosted availability

All provider states below are the public HF snapshot, not successful inference.
Model revisions, all provider entries and metadata hashes are recorded in the
JSON. `live` does not establish usable images, strict schemas or tool history on
that particular provider.

| Candidate | Checked role and availability | Decision |
| --- | --- | --- |
| `moonshotai/Kimi-K3` | Native vision/coding candidate; HF maps Together, Fireworks, Featherless, Baseten and DeepInfra as live; card license name `kimi-k3` | First Kimi candidate for a bounded comparison; not enabled |
| `moonshotai/Kimi-K2.7-Code` | Coding/vision candidate; Novita, Featherless and DeepInfra live; other entries include errors; `modified-mit` | Secondary option if it improves the measured artifact task |
| `moonshotai/Kimi-K2.6` | Vision/coding; Novita, Featherless and DeepInfra live; `modified-mit` | Older comparison candidate; no automatic fallback |
| `moonshotai/Kimi-K2.5` | Vision/coding; the same three live routes; `modified-mit` | Historical reference behind the initial visual-agent examples |
| `Qwen/Qwen3.5-35B-A3B` | Vision/text; Novita and DeepInfra live; Apache2.0 | Alternative for scientific-visual and Arabic evaluation |
| `openai/gpt-oss-120b` | Text-generation card; current user-selected Cerebras route appears live; Apache2.0 | Keep as text-planning baseline; it is not a screenshot/figure reader |

Primary model pages:[K3](https://huggingface.co/moonshotai/Kimi-K3),
[K2.7Code](https://huggingface.co/moonshotai/Kimi-K2.7-Code),
[K2.6](https://huggingface.co/moonshotai/Kimi-K2.6),
[K2.5](https://huggingface.co/moonshotai/Kimi-K2.5),
[Qwen](https://huggingface.co/Qwen/Qwen3.5-35B-A3B),
[GPT-OSS](https://huggingface.co/openai/gpt-oss-120b).
License names are recorded as published, not interpreted as equivalent terms.

The official K3 quickstart documents image input, JSON Schema and tool calls.
The separate generic JSON-mode page demonstrates `json_object`; those are different
contracts. An HF route must be qualified independently. Our Cerebras-specific
`reasoning_effort`, history rules and o200k token admission cannot be assumed to
apply unchanged to Kimi. No credential or endpoint migration is part of this work.
[K3 API](https://platform.kimi.ai/docs/guide/kimi-k3-quickstart),
[JSON mode](https://platform.kimi.ai/docs/guide/use-json-mode-feature-of-kimi-api).

## Scientific visualization research

**PaperVizAgent / PaperBanana:** the official Google Research repository separates
reference retrieval, planning, styling, visualization and critique. Its examples
use image-generation services and iterative refinement. It is a research reference,
not a ready HF adapter or proof of our Arabic learning quality. The repository
itself identifies its implementation as a demonstration.
[Official implementation](https://github.com/google-research/papervizagent),
[publisher research page](https://research.google/pubs/paperbanana-automating-academic-illustration-for-ai-scientists/).

**PaperBanana-Interact:** the paper studies multi-turn feedback and reports drift
and loss of previously satisfied requirements during revision. This supports our
decision to version artifacts, retain locked source facts and apply focused edits.
Its reported authoring results do not establish learner understanding in Egyptian
Arabic.[Paper](https://arxiv.org/abs/2608.30241).

**Crafter / CraftEditor:** this work investigates scientific-figure generation
and editable SVG outputs. It motivates inspectable components and local revisions.
We do not infer that arbitrary generated SVG is correct or safe to execute.
[Paper](https://arxiv.org/abs/2605.30611).

## Chosen architecture

Use one finite LangGraph workflow with four logical responsibilities:

1. Source analyst: obtain the selected paper's cited facts/regions.
2. Teaching planner: choose a learning goal and structured `VisualSpec`.
3. Renderer: application-owned SVG/PNG and later approved interactive templates.
4. Critic: deterministic source/number checks, semantic review and visual QA.

These are responsibilities, not four required concurrent agents or four different
models. Initial planning/review can use one hosted text model; vision is added
only for tasks needing figure/screenshot input. No swarm, shell or self-generated
application code is required for the first slice. Deep Agents remains an optional
bounded source-reading path after its current failure is actually diagnosed.
[LangGraph workflow/agent distinction](https://docs.langchain.com/oss/python/langgraph/workflows-agents).

The model emits a small declarative plan and evidence IDs. Application code draws
approved shapes and binds approved interactions. Numerical charts select verified
table-cell IDs; they do not accept invented model data. Teaching simulations carry
an explicit example label and never masquerade as paper results. Semantic review
still needs a separately evaluated rubric and human scientific checks.

## Rendering and delivery choices

- First: deterministic SVG plus PNG using existing Arabic-capable drawing paths;
  no new inference or browser dependency in normal bot startup.
- Desktop study view: application-authored HTML/SVG controls for step selection,
  component details and original evidence. Model labels are escaped data.
- Later numeric charts: consider Vega-Lite's declarative parameters/selections.
  Translate our restricted chart contract into application-owned specs; disallow
  model-provided URLs/expressions. Pin dependencies only when that slice begins.
  [Vega-Lite parameters](https://vega.github.io/vega-lite/docs/parameter.html).
- Mermaid can support static diagrams, but its default strict security disables
  diagram click actions. Keep it for static exports or build interaction outside
  its untrusted diagram input; do not enable loose mode to obtain clicks.
  [Mermaid security options](https://mermaid.js.org/config/usage.html#securitylevel).
- Telegram receives PNG and normal private text actions first. A richer Telegram
  Mini App is a later web integration with server-validated `initData`; the PC's
  loopback address is not reachable from a separate phone. No public tunnel,
  domain or BotFather configuration change is made here.
  [Telegram Mini Apps](https://core.telegram.org/bots/webapps).

## Next concrete slice

Build an offline, source-bound **RAG method explainer**, starting with the existing
public `2005.11401v4` cache. Separate inference and training views. In training,
keep the document encoder/index fixed and show updates to the query encoder and
BART generator, as stated in section 2.4. Inference and training arrows have
different meanings. Later token/sequence animation must preserve marginalization
over the retrieved set; it must not imply a fresh retrieval for every token.
[Original paper](https://arxiv.org/pdf/2005.11401v4).

Use curated test facts to prove schema validation, Arabic layout, source inspection
and deterministic step changes before integrating a new model. This prototype
does not establish arbitrary-paper support. Then qualify candidate hosted models
on the same input fixtures under a separately authorized inference ceiling.
See the [implementation specification](../../specs/learning-visuals.md) and the
[ordered tasks](../../../tasks/todo.md#learning-visuals--next-implementation).
