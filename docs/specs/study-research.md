# study-research: bounded tools with a deliverable answer

Status: extension spec, 21 October 2026. Inherits [shared rules](researcher-app.md).
Depends on paper-evidence. The coordinator consumes its report; ordinary lessons
and offline visuals must remain usable when research is disabled or fails.

## Objective and actual status

Answer a question requiring multiple source reads without losing the final
answer/review budget. Existing optional Deep Agents runs in a separate environment
with bounded read-only study tools and optional stdio MCP. A real valid `/deep`
training question failed after two successful transports. Its original cause
was not retained; new safe diagnostics improve observation, not proof of repair.

## Provider contracts and execution

`ResearchRequest`: admitted job, selected source identity, bounded question,
explicit allowed tools, goal and phase budget. Owner/paths/tools are trusted
configuration, never model arguments. `ResearchReport`: evidence refs, supported
findings, missing evidence, operations/attempts and finite outcome category.
Do not expose hidden reasoning or raw provider/SDK exception text.

Start with one coordinator and read-only source tools. Preserve current eight
tool-operation cap and four shared model attempts. Reserve synthesis/review
before research; future tool/model subtasks use the same parent ledger. No
implicit subagent, shell, filesystem writer or generic network fetch. Deep
Agents features are optional and need exact installed-version tests; latest
documentation is not a reason to upgrade the isolated pinned SDK automatically.
[Official capabilities](https://docs.langchain.com/oss/python/deepagents/overview).

Keep protocol models independent of the main app's optional SDK dependencies.
MCP tool schemas include bounded input/output, selected-paper scope, source
identity and safe error types. Model/tool content cannot reauthorize itself.
Protocol negotiation must match the installed client/server; do not copy a
newer spec's wire format into the pinned SDK. Treat remote tools as untrusted
and require explicit application credentials for each integration.
[MCP tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools).

## Diagnosis and later external research

Preserve the pending [eight-attempt diagnosis scope](../deep-repair-execution-20261021.md):
no approval has arrived. Offline contract, replay and failure injection work can
continue. An authorized live diagnosis must record its source, immutable intents
and outcomes; any correction follows the scoped offline repair/one verification
rules. Do not claim a speculative cause or spend closed historical grants.

Later external search is explicit and read-only: primary documents, author-linked
code/docs and bounded results/fetches. Every finding has URL/acquisition/source
hash and is labeled outside the selected paper. External lookup needs its own
fetch/SSRF policy and cannot silently import executable instructions. A failed
search returns the paper-only answer/uncertainty rather than unbounded browsing.

## Implementation and verification

Existing `deep.py`, `tools.py`, `mcp_server.py`, `failures.py` and
`src/commands/study_research.py`; separate SDK tests in `research/tests/`.
Future phase-budget state belongs to the shared admitted-job contract, not a
second local counter. Use finite error enums and existing transport adapters.

```powershell
.venv-win/Scripts/python.exe -m pytest tests/unit/test_study_tools.py tests/unit/test_study_feedback.py -q -o cache_dir=tests/test_output/study-pytest --basetemp tests/test_output/research-contract
.venv-study-research/Scripts/python.exe -m unittest discover -s research/tests -v
```

Test the real installed SDK/tool loop with stubbed HTTP, plus malformed tool
IDs/arguments, context overflow, exhaustion, timeout/cancellation and unknown
attempt recovery. Keep optional imports out of normal startup; common lint/type
checks still apply. Do not add a permissive tool to get a failing example green.

## Acceptance

SR-1: Research cannot use reserved review capacity; every admitted run terminates
with a reviewed artifact or a useful failure/partial state within its budget.

SR-2: A live Deep repair is called qualified only after the authorized exact
question reaches validated answer, review and delivery; offline SDK success alone
is reported as offline success. Unknown causes remain explicitly unknown.

SR-3: Optional MCP/external tools preserve owner/source boundaries, provenance,
attempt accounting and no hidden writes; disabling them leaves core study usable.

Open choices: actual Deep root cause after scoped observation, later search
service and any delegated role only when measurements justify it. None blocks
the offline visual prototype.
