# Local monitoring observation — 2026-10-13

After [local activation](week6-local-activation.md), the user approved a short
observation through the existing Gradio client and preparation for off-machine
backup/recovery. Eight sequential BM25 requests ran in an isolated browser: four
inspected questions, each repeated once. This is a controlled sample through the
normal UI, not naturally collected user traffic, a quality evaluation or load test.
No selector, prompt, model, API, dependency or system setting was changed.

## Results

| Question case | Cache miss, ms | Repeat hit, ms |
| --- | ---: | ---: |
| KBEVO | 16,476 | 579 |
| UndoBench design | 7,372 | 276 |
| Atomic Visual Entailment | 7,611 | 263 |
| Kandinsky | 7,238 | 284 |

All eight responses completed successfully, with matching rendered outputs in
each pair. Four misses were stored; all four repeats avoided retrieval and
generation. The 50% hit rate follows directly from the chosen pairs. There were
zero API failures, retries, validation failures, authentication/quota rejections
or uncaught browser errors in these eight requests. Normal global quota windows
were respected; one repeat waited about 2.3 seconds for the window to reset.

Server full-response latency p50 was 579 ms and p95/p99 16,476 ms. With eight
samples these percentiles are descriptive; they do not establish normal-user
service levels. The four real Ollama generations recorded 3,214 prompt tokens,
54 output tokens and 36.51 seconds of aggregate model duration. Cached requests
added no generation tokens. No provider cost is estimated.

The initial KBEVO miss began with no model loaded and took 16.48 seconds; model
load accounted for about 4.91 seconds. Further misses used the loaded model.
Memory was sampled during the cold request and the continuation, including
60 seconds of idle observation after the last pair. Minimum available Windows
memory was **539 MiB**, below the earlier activation's 600 MiB acceptance margin.
The 384 MiB emergency floor was not reached. Minimum commit headroom was
12,022 MiB; final free memory was about 1,699 MiB. This is actual memory pressure,
not a model-quality failure. The remaining six requests had at least 1,529 MiB
available. Keep Langfuse, Airflow and Dashboards stopped during local RAG use;
sustained concurrency, default hybrid retrieval and concurrent Langfuse capacity
were not assessed. No permanent watchdog or automatic alert was installed.

## Harness corrections and preservation

The initial browser attempts selected Chrome's component-extension background
target, so navigation aborted before any API questions ran. Selecting only the
fresh `about:blank` page resolved it. A subsequent harness used cross-system
timestamps and attributed the first repeat to the previous request ID. Retained
events prove the actual second unique ID was a successful 579 ms hit with no
retrieval/generation. The erroneous report remains untouched; a separate
correction records the evidence. The remaining pairs used new-ID correlation.
No application source repair or assertion suppression was needed.

The API and normal Gradio client were healthy at the end. All service running
states, original container IDs/images/configuration/resource settings/mounts,
active image/container identity, original key, workspace source, configuration
and evaluations match their baselines. Full database/index/vector fingerprints,
alias targets and installed model digests match: 58 papers, 58 paper documents,
1,221 v1 chunks and 2,775 v2 chunks. The API remains one worker with authenticated
volatile Redis and file monitoring; the retained original API and heavy services
remain stopped. No deployment, tuning, ingestion, reindexing, model download,
commit, push or merge occurred.

Evidence is under restricted-ACL
`test_output/week6-observation-20261013-01/`: `completion.json`,
`monitoring-combined.html/json`, `corrected-first-pair.json`,
`continuation-05/observation.json`, screenshot, original failed harness reports,
`data-before.json` and `backup-readiness.json`. Monitoring metadata contains no
questions, answers, evidence, prompts or keys. Private browser outputs and case
definitions are retained separately; do not publish the evidence directory.

## Backup and replacement-machine status

The frozen recovery bundle was verified read-only against its own manifest:
**233 files, 8,970,337,129 bytes** (about 8.35 GiB), no mismatches. Its manifest
SHA-256 is `a17b2ac49f8f44b74a5090510668e5c93d1fadd7afdd547b4090f350d1fb7685`.
It includes private credentials. The bundle remains unchanged and still captures
the verified runtime from before the new caching/monitoring activation; it does
not contain these later Week 6 additions.

Attached storage is on two internal NVMe disks, with no mapped off-machine share
found. The user was asked for a protected external-device or network-folder path.
**No off-machine copy has occurred:** the destination is still missing. Preserve
the local bundle and use a new receiving directory, then verify every receiving
file plus the manifest against the source. Follow the existing bundle's
`RECOVERY.md` for its already tested isolated replacement procedure on the
separate machine; that machine and its receiving evidence path also remain to be
provided. Do not repeat the completed same-machine recovery drill or refresh the
frozen bundle as a substitute for these steps.
