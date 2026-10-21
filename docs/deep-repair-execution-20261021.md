# Pending bounded live diagnosis: private Deep Agents path

Prepared21October2026. **Not approved or executed.** Earlier evaluation grants
remain closed; the independent12-attempt smoke ceiling is exhausted. This plan
does not transfer unused slots or reset any counter.

## One request, at most four attempts

Use the current paired private development API with its normal authentication.
Admit exactly one job, with stable intent:

```text
development:deep-repair-20261021:v1
```

Frozen question:

```text
/deep اشرح طريقة تدريب الـretriever والـgenerator خطوة بخطوة من الدليل
```

Require active public paper`2005.11401v4` and the patched worker error categories.
Frozen application source checkpoint:`1bf7c9a`. Documentation-only commits may
follow; verify application source still matches this revision before admission.
The request sends that question, bounded public source excerpts and the recent
selected-paper dialogue used by the existing workflow to HF/Cerebras. It uses
`openai/gpt-oss-120b:cerebras`, the isolated research environment and the existing
read-only source tools. It does not enable OCR, web research, Notion or another
provider. Record the exact source commit before admission.

The single durable job's existing immutable`max_calls=4` is the ceiling, shared
by tool-planning/generation and grounding review. Failed, reserved and uncertain
outcomes count. Do not create a second intent, retry a failed job, delete its
records or reuse historical receipts. Repeating the same intent returns its
stored job; it is not a new allowance. If the run fails, inspect the safe
failure code and stop; offline diagnosis can continue separately.

The bot may deliver the resulting success or failure message to the paired
owner's private Telegram chat. Approval must cover this test reply as well as
the four-call ceiling; no message to other users is involved.

## Before admission

- Obtain the owner's explicit approval for this scope and record it locally.
- Confirm the active paper/version, paired owner and idle runtime.
- Preserve startup/live RAM admission and all source validation rules.
- Record job count/attempt count and exact source revision; do not print secrets.
- Reuse the existing source cache; do not change the model or prompt during the run.

## Inspect afterwards

Read the durable job status, attempt purposes/states and allowlisted failure
category. On success inspect each scientific claim, the quoted evidence, training
roles and source pages before claiming the path works. Transport success alone
does not qualify the answer. Keep provider reasoning and credentials out of the
report. Do not describe a single result as an unseen benchmark or a public launch.

If four attempts are insufficient to reach a valid reviewed answer, report that
limitation. Do not silently increase the job budget or skip the review.
