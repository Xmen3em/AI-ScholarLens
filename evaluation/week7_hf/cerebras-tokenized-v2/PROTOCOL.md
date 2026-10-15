# Cerebras task context admission v2

This additive profile corrects the local context accounting of the selected
`openai/gpt-oss-120b:cerebras` route. It grants no execution or app activation.
The original hosted and Cerebras v1 manifests remain immutable and retain their
conservative UTF-8 byte admission. A local zero-HF-call rehearsal showed that the
first development relevance prompt contains 12,276 characters and fails that byte
admission before any model request. Full passages must remain available to grading.

GPT-OSS uses o200k_harmony BPE, not one token per input byte. For this explicit task
profile, count the entire serialized JSON payload with the published ordinary BPE
vocabulary and splitting expression. Treat special-token-looking strings as
ordinary untrusted text. Keep context 8,192 tokens, reserve the original 512 tokens
for provider templates, and reserve the original 256/512 output tokens. Counting
schema and envelope JSON as input conservatively includes structured-output
overhead. Check reported input/output usage against the original native limits.
No paper text, markers, schemas or prompts are shortened or rewritten by admission.

Bound request JSON to 65,536 UTF-8 bytes and schema JSON to 7,168 bytes separately.
The unchanged 30-candidate schema is 9,558 bytes and must still reject locally;
the exact original five synthetic qualification payloads remain unchanged. Native
clients outside this explicit task/runtime retain the original byte admission.

The vocabulary SHA-256 is
`446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d`.
Prepare this small public tokenizer table explicitly in ignored local storage;
runtime verifies its hash and never downloads or repairs it implicitly. No model
weights are downloaded. Use pinned tiktoken 0.14.0 for local encoding.

All other inherited profile fields are unchanged: same model and rates, full
64/192 matrices, semantic/coverage/abstention/attribution/latency gates, exact
canonical qualification cases, six-call work bound, quotas, deadlines, RAM floors,
corpus/model/source preservation, explicit persistent funding and unknown usage.
Development remains at most 261 attempts and holdout at most 773, separately
funded. Every run needs fresh five-case qualification; holdout needs accepted
reviewed development; activation needs accepted full holdout and owner testing.

Primary implementation sources:

- https://github.com/openai/gpt-oss/blob/main/gpt_oss/tokenizer.py
- https://github.com/openai/tiktoken/blob/0.14.0/tiktoken_ext/openai_public.py
- https://github.com/openai/tiktoken/blob/0.14.0/tiktoken/core.py
- https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken

This change replaces one documented admission algorithm in a new profile; it
does not reinterpret or edit the old frozen byte-gate evidence. The local
rehearsal is prompt-size evidence only, never semantic/model/app acceptance.
