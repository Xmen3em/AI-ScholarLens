# HF/Groq public synthetic reproduction

This local bundle contains exact public synthetic request bodies and bounded
observations. It contains no credentials, authorization headers, paper data,
Telegram identifiers, provider completion, reasoning or raw error body. It has
not been submitted to anyone. These files do not authorize another inference call.

On 2026-10-15, the frozen five-case qualification passed scope, then stopped at
relevance after HTTP 400 / `json_validate_failed` / `invalid_request_error` from
`openai/gpt-oss-120b:groq` through `https://router.huggingface.co/v1/`. Failed usage
is unknown. Initial free RAM was 1,302.12 MiB; minimum live free RAM was 1,253.19 MiB.
The local check with 30 selector candidates rejected before outbound work. Source,
frozen input, corpus and model preservation all passed. The model remains unqualified.

`failing-request.json` is that exact relevance body. The earlier approved clarity
pair passed both positive and negative cases; `passing-control-request.json` is
its exact positive body. The two bodies have identical schema, system, model,
strict flag, temperature, reasoning and token controls. Only the embedded question
in the user message differs: "Which passages does neural AI retrieval select?"
versus "What kind of passages does neural AI retrieval select?" This is a comparison
of single observations at different times, not a controlled repeated experiment.
Question wording is a difference, not a proven cause of HTTP 400.

Earlier failures also occurred with 512 output tokens and with unrelated evidence.
Their bounded error observations reported an empty `failed_generation` string.
They do not reveal an actual malformed generation or prove token exhaustion,
unsupported arrays, ignored strict mode, a routing defect or a semantic answer.
Do not reconstruct a discarded response from usage or labels.

Groq currently documents GPT-OSS 120B as supporting strict constrained decoding
with required fields and `additionalProperties: false`; its guide requests
reproductions for unexpected HTTP 400 errors. Our request has those settings.
This does not establish what happened inside the HF relay or provider.
[Groq structured-output documentation](https://console.groq.com/docs/structured-outputs).
HF advises selecting a specific provider/model to avoid schema incompatibilities.
[HF structured-output guide](https://huggingface.co/docs/inference-providers/guides/structured-output).

`observations.json` retains only the status, allowlisted error labels and validation
flags. Input files can be reviewed offline. Any future live comparison requires
a separately frozen, explicitly approved scope and persistent attempt accounting.
Original fixtures, labels, counters and application defaults remain unchanged.
