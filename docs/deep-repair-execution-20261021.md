# Pending bounded live diagnosis: private Deep Agents path

Prepared21October2026. **Not approved or executed.** Earlier evaluation grants
remain closed; the independent12-attempt smoke ceiling is exhausted. This plan
does not transfer unused slots or reset any counter.

## One ceiling: diagnosis and one verification, at most eight attempts

Use the current paired private development API with its normal authentication.
Admit at most two jobs, each with its existing immutable four-attempt maximum.
Their stable intents are:

```text
development:deep-repair-20261021:diagnosis
development:deep-repair-20261021:verification
```

Frozen question:

```text
/deep اشرح طريقة تدريب الـretriever والـgenerator خطوة بخطوة من الدليل
```

Require active public paper`2005.11401v4` and the patched worker error categories.
The diagnostic application source checkpoint is`1bf7c9a`. Verify it before that
job. If diagnosis identifies a repair, make and test the correction offline,
record its exact new source commit, then use the single verification intent.
This scope explicitly includes that correction and one verification; it is not
a transfer of an older grant to a different source. If diagnosis succeeds and
there is no correction to verify, skip the second job.
The request sends that question, bounded public source excerpts and the recent
selected-paper dialogue used by the existing workflow to HF/Cerebras. It uses
`openai/gpt-oss-120b:cerebras`, the isolated research environment and the existing
read-only source tools. It does not enable OCR, web research, Notion or another
provider. Record the exact source commit before admission.

One ceiling of eight covers both jobs; each job's immutable`max_calls=4` is
shared by tool-planning/generation and grounding review. Failed, reserved and
uncertain outcomes count. No third job, replacement intent, retry of a failed
job, deletion or reused historical receipt is allowed. Repeating an intent
returns its stored job, not a fresh allowance. Stop at a failed job and inspect
the safe failure category before doing any offline repair. Start verification
only if a concrete tested repair follows; do not blindly replay the question.
After verification, stop regardless of outcome. Unused slots expire with this
scope and are not a general evaluation allowance.

The bot may deliver up to two resulting success/failure replies to the paired
owner's private Telegram chat. Approval must cover these test replies as well
as the eight-call ceiling; no message to other users is involved.

## Before admission

- Obtain the owner's explicit approval for this one eight-call scope and record it locally.
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

If a job's four attempts are insufficient to reach a valid reviewed answer,
report that limitation. Do not silently increase its budget or skip review.
