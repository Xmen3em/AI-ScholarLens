# Cerebras diagnostic using the existing remainder

The user selected `openai/gpt-oss-120b:cerebras` after the Groq schema run stopped.
There are **23 used attempts and three unspent slots within the existing ceiling
of 26**. This diagnostic reallocates those three slots to the selected route;
it does not infer approval of additional calls.

The three cases are the unchanged scope, relevance and rewrite fixtures from
qualification-v2. Only the model/provider string changes. Original controller
systems, instructions, question wording, schemas, expected values, temperature,
low reasoning, context, output-token limits, deadlines, quotas and memory gates
remain fixed. One call per case, with a stop at the first failed check. Failed
or uncertain requests consume their slots. No retries or provider fallback.

Manifest: `7513c590330757c45c023c7c202c94e4b03b7c35af7c1126e0390044b02aeb0a`.
Frozen files are in `evaluation/week7_hf/cerebras-remaining-v1/`. The public HF
catalog advertises the chosen route live/structured. Its frozen diagnostic rates
are $0.35 input and $0.75 output per million tokens. Only the measurement copy adds
those rates; the original hosted profile, model pairs and prices stay immutable.
Advertised support does not establish qualification or billing for failed requests.

An ignored allocation record under `tests/test_output/hf-cerebras-execution-20261015-01/`
records the user's exact provider instruction and retained budget. Once present,
the fixed stopped Groq ledger refuses further reservations, so its three slots
cannot also be spent. Its original rows, marker and approved receipt remain intact.
Independent test/candidate ledgers stay unaffected. A new fixed three-arm Cerebras
ledger binds that allocation and all retained old evidence. Missing registration
or changed allocation fails closed; no ledger is reset, refunded or reconstructed.
Authorization is recorded as the provider instruction plus remaining approved
budget, not a fabricated approval of three new calls.

Both generation methods require exact provider/manifest/arm receipt matching,
source/frozen input/resource preservation and reservation before network work.
Default and proposal modes read no credentials, initialize no funding and contact
no service. Live execution checks the original 1,024 MiB admission and 600/384 MiB
runtime gates. Source, frozen inputs, corpus and model fingerprints are checked.
Only synthetic prompts are sent; no paper data, Telegram request or app startup.
Only bounded flags/counts, usage, timing, memory and safe error labels are retained.

Even three successful cases cannot satisfy the unchanged **five-case** qualification.
The selector cases, reviewed development/locked holdout and private PC/Telegram
acceptance remain pending. Global HF, agent and Telegram settings remain disabled.
The existing private HF token is used through the HF router; no native Cerebras
credential or model download is required.

```powershell
.venv-win/Scripts/python.exe -m src.commands.qualify_hf_schema --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/hf-cerebras-new-plan --experiment cerebras-remaining-v1
```

Prepared evidence is under `tests/test_output/hf-cerebras-prep-20261015-01/`.
Public catalog: [HF router models](https://router.huggingface.co/v1/models).

Preparation verification: **1,184 tests pass, zero skips**, 17 new, including 15
budget/diagnostic checks and two configuration/telemetry checks. Mypy checks 116
source files; Ruff passes. All 329 protected files match, including old grants,
receipts, stopped results, immutable profiles, pairing/configuration and recovery.
Actual pending execution rejects before private Settings/network/funding. The
first full run exposed the old expected rejection of this newly selected model;
that case now rejects the unreviewed 20B model and keeps its assertion. Explicit
120B acceptance and safe Cerebras labels have positive coverage. No tests skipped,
removed or weakened. Defaults and unregistered-provider rejection remain intact.

## Executed result

The user's provider instruction and existing three-slot remainder were recorded
under `tests/test_output/hf-cerebras-execution-20261015-01/`. The fixed new ledger
settled all three cases at one attempt each. Old Groq reserve was independently
confirmed blocked, with its original two used rows and receipt unchanged.

Run `tests/test_output/hf-cerebras-live-20261015-01/` **passed scope, relevance and
rewrite**, including exact expected relevance, supplied-marker membership and no
duplicates. All usage is complete, with no schema violation. Source, frozen input,
corpus and model preservation all pass. Initial RAM was 1,907.91 MiB and minimum
live RAM 1,545.66 MiB. Client durations were about 2.16–2.21 seconds per request.

**All 26 approved attempts are used; zero active slots remain.** The allocation
reused the three old slots and did not increase that ceiling. Known added usage
estimate is $0.00046240; cumulative known estimate $0.00137020 plus 11 older
unknown-cost failures. Estimates are not invoices. No paper data or Telegram
request was sent, and no app process or runtime flag was activated.

This is a passing three-case diagnostic, not full five-case or app acceptance.
The next bounded scope is the original selector-1 and selector-10 cases on the
same Cerebras route, with separate additional-call approval. Then complete the
retained reviewed task/holdout and private owner acceptance gates.
