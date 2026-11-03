# First-lesson latency on GLM-5.3: where the time goes

Status: investigation for the owner, 3 November 2026. No paid calls were made, and
none of the options below is implemented; each needs the owner's approval, and
most need a paid development rerun before production.

Sources: `data/eval/paper-benchmark/holdout-control/jobs.jsonl` (69 timed jobs on
18 papers) and `dev-rerun-2-control/jobs.jsonl` (48 jobs on 12 papers). They hold
each job's wall time and each call's token usage, but no per-call time. The split
between the lesson writer and the claim check (`grounding_review`) is therefore
estimated from tokens. A least-squares fit over the 110 two-call jobs gives about
9.6 s of fixed time per job plus 15.8 ms per output token (about 63 tokens/s). The
fit explains only half the variance (R² 0.48), for the reason given in finding 3.
The scenario numbers scale each job by its own measured seconds per output token.
They reproduce the holdout's reported nearest-rank p95 of 94.5 s.

## Findings

1. **Output tokens set the time; input size does not.** A first lesson makes about
   3,000 output tokens across its two calls. The writer makes a median of 1,880
   (range 1,540–2,300) and the check a median of 1,090 (range 640–2,770). The fitted
   input cost is zero within noise, even though the writer reads about 12,400 tokens
   and the check about 5,900.
2. **The writer is steady and the check is what varies.** At the median the writer
   takes about 30 s and the check about 22 s; the rest is fixed time. On the two
   slowest lessons (107 s and 100 s) the check wrote more than the writer: 2,769
   and 2,155 tokens.
3. **Hidden reasoning in the check makes the slowest lessons slow.** The check
   reasons even at `reasoning_effort: low`: a median of 215 tokens per lesson, but
   1,789 and 1,140 tokens on the two slowest (about 28 s and 18 s). The writer
   reasons little (median 53 tokens).
4. **Provider speed varies by run.** Effective speed ranged from 35 to 93 output
   tokens/s per lesson. The holdout median was 50 tokens/s and the dev rerun 69, for
   the same token counts. This explains most of the gap between the holdout p95
   (94.5 s) and the dev p95 (68.5 s), and nothing in our code controls it.
5. **The study map is not the problem.** Rendering it locally takes 0.5 s per
   lesson (measured on the 29 saved lessons).
6. **The bot added up to 20 s that the benchmark never saw.** The bot looks for
   finished jobs only between long polls of 20 s, so a finished lesson waited about
   10 s on average before it reached the student. The progress change in this same
   branch shortens the wait to 3 s while a job runs; see
   [learning-delivery](specs/learning-delivery.md).

## Options

The p95 column replays the holdout (current 94.5 s, gate 90 s); the dev column
replays the dev rerun (current 68.5 s). Every saving assumes the remaining output
stays the same, which only a paid rerun can confirm.

| Option | Holdout p95 | Dev p95 | Lesson median (holdout) | Quality risk | Cost |
| --- | --- | --- | --- | --- | --- |
| Today | 94.5 s | 68.5 s | 60.6 s | — | — |
| A. Claim check without reasoning | 82.4 s | 46.1 s | 57.2 s | Medium: the check may approve more weak claims; needs the judge's unfaithful rate | Slightly lower |
| B. Claim check in 2 parallel halves | 77.6 s | 54.8 s | 50.7 s | Low: each verdict sees the same claim, quote and block | One more call per lesson (3 of the 4-call budget) |
| C. A and B together | 75.4 s | 41.1 s | 49.5 s | As A | As B |
| D. Writer and check without reasoning | 80.9 s | 46.1 s | 55.7 s | Higher: the writer's claim quality may drop | Slightly lower |
| E. First lessons capped at 12 claims (median today 16) | 77.6 s | 51.9 s | 51.9 s | Medium: thinner lessons; kept claims would fall below today's 9.5 | Lower |
| F. Lower check `max_tokens` from 3,000 | No faster | No faster | No change | High: cuts off long checks, which then fail | — |
| G. Fewer opening evidence blocks (12 → 4) | No faster | No faster | No change | Medium: less of the problem and method for the writer | Lower input cost |

Notes on each option:

- **A. No reasoning in the check.** Send `chat_template_kwargs: {"enable_thinking": false}`
  (the switch the benchmark already qualified) or `reasoning_effort: "none"`, for
  `grounding_review` only. This removes the largest variable cost. The check copies
  spans and the application verifies them, so reasoning matters less here than in
  the writer. Whether DeepInfra honours either switch for GLM-5.3 is unverified. It
  needs one approved qualification call, then a dev rerun with the judge.
- **B. Two parallel checks.** Split the items into two groups. Each group goes with
  only the cited blocks it needs, and both calls run at once. This needs three code
  changes: the model client's single-call lock and single connection must allow two
  calls for one job; attempt accounting stays as it is (3 calls, within the job's
  4); and the claim-check spec's "one call" becomes "one or two calls". Running them
  one after the other would be slower than today. The risk is provider rate limits
  (HTTP 429) on two simultaneous requests.
- **E. Fewer claims.** Every claim costs writer tokens and check tokens. A smaller
  cap shortens both calls but trades away coverage. The benchmark's kept-claims
  figure is one of the reasons GLM-5.3 was chosen.
- **F. Lower `max_tokens`.** This does not make anything faster. A call stops when
  its answer is done, and `max_tokens` only cuts off answers that run long. At 2,000,
  six of the 29 measured checks (3 holdout, 3 dev) would have been cut off and their
  lessons would have failed. At 2,500 one would have failed. The current 3,000 is
  right.
- **G. Fewer opening blocks.** Input size has no measurable effect on time (finding
  1), so this saves input cost, not seconds.
- **Not costed: another provider or route for GLM-5.3.** Finding 4 suggests provider
  speed matters as much as any code change. Measuring other providers is a paid
  qualification and would change the benchmarked configuration.

## Recommendation

Approve one paid qualification call for option A. If the provider honours the
switch, approve a dev rerun of A, and of C if A alone misses the gate. Judge its
unfaithful rate against the current dev result before any production change. B is
the lowest-risk saving that needs no model behaviour change, but it costs code and
spec work. Start it only if A fails qualification or loses faithfulness. The
progress messages and the shorter poll (finding 6) already lower the wait the
student feels, with no change to the model calls.

The analysis scripts are local and not committed. They read only the two
`jobs.jsonl` files and make no network calls.
