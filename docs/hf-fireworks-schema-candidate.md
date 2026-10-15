# HF Fireworks schema candidate

The user subsequently selected `openai/gpt-oss-120b:cerebras`. This Fireworks
candidate is preserved as tested source and historical pending scope. No Fireworks
approval is requested, and no inference was sent to it. The next active work is
the user-selected Cerebras diagnostic within the three remaining call slots.

The approved Groq qualification passed scope and failed relevance with HTTP 400 /
`json_validate_failed`. It stopped after two calls. **23 attempts are used in total;
three Groq calls remain unspent and held by that run's frozen stop rule.** Those
calls do not authorize testing another provider.

This separate candidate proposes **up to five additional public synthetic calls**
to `openai/gpt-oss-120b:fireworks-ai` through the same HF router and private HF token.
Fireworks is already in the application registry and original hosted profile.
A credential-free read of the public HF catalog advertises it live with structured
output. This advertisement does not establish compatibility or qualify the model.

The exact five payloads change only the model/provider string from the original
Groq schema check. They retain the same scope, relevance, rewrite, selector-1 and
selector-10 fixtures, prompts, expected values, strict schemas, patterns and order.
Controllers use 256 output tokens and selectors 512, temperature 0, low reasoning,
context 8,192, and the original deadlines, quotas and 1,024/600/384 MiB RAM gates.
The schema with 30 candidates must reject locally before an outbound attempt.
No clearer-question substitution, label change, retry or provider fallback.

Manifest: `507ed295c7b59b5bb57e1a4f87569ec129b19c1092c297a992695484d56dc820`.
Frozen files are under `evaluation/week7_hf/provider-alternative-v1/`. The new
counter would be `tests/test_output/hf-fireworks-schema-allowance-20261015/allowance.sqlite3`.
Its receipt binds this manifest, all three exhausted old allowances, and the
preserved stopped Groq receipt/counter/result showing exactly two settled arms.
Old counters and their unused arms remain unchanged. There is no new approval
or funded candidate ledger yet.

Both generation methods validate the receipt against the exact provider experiment,
check source/resources/frozen inputs and reserve a named arm before outbound work.
A Groq approval cannot fund Fireworks, and a Fireworks approval cannot fund Groq.
Named arms never repeat after failure, uncertainty, restart or a fresh output
directory. Missing registered evidence requires recovery. The first failed check
stops the run; unknown usage prevents qualification.

Default and proposal modes read no credentials, initialize no allowance and contact
no service. The actual pending proposal is under
`tests/test_output/hf-fireworks-schema-approval-proposal-20261015-01/`.
Execution with it was rejected before private Settings, network or funding.

```powershell
.venv-win/Scripts/python.exe -m src.commands.qualify_hf_schema --snapshot tests/test_output/week7-source-review-20261013-01 --output tests/test_output/hf-fireworks-new-plan --experiment provider-alternative-v1
```

The explicit live command additionally needs a separately approved receipt, fresh
output, `--execute --approval`, and the same experiment selection. It sends only
public synthetic fixtures. No paper data, Telegram traffic, app activation or
native provider credential is included. Output contains only bounded diagnostics,
hashes, usage, timing, memory and allowlisted error labels; generated text and
reasoning are discarded.

Passing would establish schema qualification only. Reviewed development, locked
holdout and private PC/Telegram acceptance remain required. HF, agent and Telegram
global settings stay disabled; the original API and all retained data/models stay
intact. Preparation evidence is under
`tests/test_output/hf-fireworks-schema-prep-20261015-01/`.

Catalog source: [HF router model catalog](https://router.huggingface.co/v1/models).
Provider selection guidance: [HF structured outputs](https://huggingface.co/docs/inference-providers/guides/structured-output).
