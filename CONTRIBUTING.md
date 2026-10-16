# Contributing to ScholarLens

ScholarLens is a development prototype moving toward interactive AI-paper
learning in Egyptian Arabic. Start with the [README](README.md),
[codebase guide](codebase-overview.html), and [proposed capability map](CAPABILITY_MAP.md).
The map describes future work; it does not imply that those features exist.

## Local development

Use Python 3.12. On Windows, `Telegram.ps1` expects `.venv-win`:

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-win"
uv sync --frozen
```

Use your own `.env`, service instances, and bot. The checked-in environment
example describes settings, not credentials or a preloaded corpus. Do not
commit tokens, private chat messages, user IDs, local logs, or runtime state.
The Telegram bot remains owner-only until a separately designed multi-user mode.

## Changes that help

- Report a missed paper answer with the exact question, public paper/version,
  expected supporting passage and a redacted response.
- Review Egyptian Arabic explanations for clarity and scientific accuracy.
- Add small extraction fixtures for equations, tables, figures and reading order.
- Improve citations, deterministic validation and failure messages.
- Discuss a capability's boundaries before starting a large implementation.

## Workflow

1. Create a short-lived branch, using `codex/` for Codex-managed branches.
2. Make one focused change. Keep runtime changes separate from documentation.
3. Add meaningful tests for changed behavior; documentation edits need link,
   command and factual checks rather than new unit tests.
4. Run the relevant checks and describe their results in the pull request.
5. Explain the user-visible change, limits and any migration needed.

```powershell
.venv-win/Scripts/python.exe -m pytest tests/unit/test_development_assistant.py tests/unit/test_development_bot.py -q
.venv-win/Scripts/python.exe -m ruff check src tests
```

Run [the wider test suite](TESTING.md) when shared behavior changes. Integration
checks may require Docker. Do not run paid inference, paper downloads, or live
Telegram messages as an unnoticed part of a unit test.

## Evidence and learning content

Preserve the distinction between a quotation, a paper-grounded explanation,
background knowledge, and a teaching analogy. Numbers need the original metric,
dataset, baseline and conditions. A valid quotation alone does not prove that
it answers the question. Keep frozen evaluation sources, labels and results
immutable; put new experiments in new, versioned artifacts.

Egyptian Arabic is the target teaching language. Keep paper titles, identifiers,
mathematical symbols and useful English terms intact. Review right-to-left
layout alongside left-to-right formulas and code. The current bot's English
examples do not establish Arabic teaching quality.

## Tools, privacy and reporting

Tools must receive server-validated identity and bounded inputs. Treat paper
text and retrieved pages as untrusted material. Plan URL validation, redirects,
resource limits and provenance before adding chat ingestion. A desktop MCP
connection is not automatically a credential or integration for the deployed bot.

For a suspected credential leak or access-control bug, do not put tokens,
private account details or exploit instructions in a public issue. Use a
private reporting channel listed by the maintainer; if none is available,
request one without disclosing the issue. Share a redacted reproduction and
rotate exposed credentials through the issuing service.

Contributions are covered by the [MIT license](LICENSE). Preserve upstream
attribution and third-party license notices.
