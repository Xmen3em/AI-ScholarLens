# Private Telegram development testing

Update: the owner chose **“Explain concepts and answer paper questions.”** The
development bot now handles both. “What is RAG?” and “understand ML systems”
were each checked live and returned a general explanation using one HF call.
General replies are labeled **model knowledge** and do not claim paper citations.
Paper-specific requests still use the evidence workflow; missing paper evidence
does not fall back to a generated general answer. The two checks went through
the authenticated local API; no old Telegram messages were replayed.

The owner explicitly requested live manual testing while changing the AI agent.
This authorizes an opt-in development runtime with the existing paired account,
HF token and `@AIScholarLensbot`. It does not turn the rejected holdout into an
accepted result. The normal accepted-runtime launchers and evaluation receipts
are unchanged. Interactive questions use HF inference independently of the old,
completed evaluation grants; old unused slots are never transferred.

From the repository root in PowerShell:

```powershell
.\Telegram.ps1
.\Telegram.ps1 -Restart  # after changing the agent
.\Telegram.ps1 -Stop
```

Open [@AIScholarLensbot](https://t.me/AIScholarLensbot), send `/start`, then send
an AI research-paper question. Only the paired owner in their private chat can
use the bot. The PC and Docker Desktop must remain running. There is no Windows
autostart job. A restart loads agent changes; questions are not replayed.

Edit `src/services/development_assistant.py` for concept/paper routing and
explanation instructions, `src/services/agent.py` for paper graph behavior, or
`src/services/ollama/prompts/rag_system.txt` for paper evidence selection.
Restart to load changes.

The API and polling bot share **one Python process**. Generation runs remotely
on `openai/gpt-oss-120b:cerebras`; keyword/BM25 retrieval avoids loading a local
embedding model. SQL is not a dependency of this test mode: its only application
endpoint is the agent question endpoint, plus authenticated development status.
It does not expose the full paper-browsing API. The local SQL credentials were
found invalid during an initial startup; no password, database, container, paper
or private configuration was changed to work around that unrelated dependency.

Startup requires 1,024 MiB free host RAM, and questions/generation retain the
600 MiB live floor. These existing BM25 thresholds are unchanged. One bot question
runs at a time, with the existing six-request/minute quota, at most six model
calls per question, original deadlines and bounded tokenized inputs. Exact
citations, output validation, owner checks, durable update offsets, API key
authentication and no inference replay remain active. Known answer-quality gaps,
including false abstentions and multi-paper evidence handling, remain for the
owner to inspect and improve.

Settings are enabled only in the development process. Global `.env` flags and
credentials are unchanged; original API8000 and existing containers stay intact.
The development API binds only `127.0.0.1:8002`, returns `accepted:false` at
`/api/v1/development`, and uses a separate persistent quota file. It creates no
acceptance lock and never resets the prior evaluation ledgers.

The script launches hidden and records the latest process/log paths in ignored
`data/pc-app/development-process.json`. Logs contain operational messages; bot
HTTP logging suppresses Telegram token URLs. The original paired update offset
remains `data/telegram/offset.json`; do not delete it or its registration to
restart. The stop command requests graceful shutdown of both services, including
after a bot task failure.

For a foreground terminal with Ctrl+C shutdown, use:

```powershell
.venv-win/Scripts/python.exe -m src.commands.run_dev_bot --execute
```

Default/`--check` is offline and writes no state. `--stop` requires no model call.
