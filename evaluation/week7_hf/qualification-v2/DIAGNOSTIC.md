# One-attempt diagnostic protocol

Frozen before diagnostic inference on2026-10-13. Parent fixture manifest
762bbc82e159bd873d41185059bcb838a641b4fa81d8636805b1eec1417a6464.
Preserve the rejected qualification-v1/v2 trials and their original evidence.

This diagnostic reproduces the single failing request for error classification.
Its result cannot qualify the model or open case collection.
Submit exactly the frozen v2 relevance prompt/system/schema once to the same
approved HF/Groq pair. Record only original bounded timing/usage/schema metadata,
content-free decision diagnostics if available and allowlisted provider error
code/type labels if returned. Read at most8192 error-body bytes transiently;
discard error messages, failed generations and all unrecognized labels. Retain
the30s attempt deadline, canonical schema and every original adapter/workflow
limit. No schema/prompt changes, JSON downgrade, fallback, retry or paid probes.

Reserve one attempt from the existing cumulative13-call pilot allowance. Trial04
used2,trial05used2:9 remain before this diagnostic. Use the fixed same SQLite
allowance file; interrupted or uncertain work remains charged conservatively.
Keep1024MiB BM25 host admission,600MiB margin/384MiB cancellation,6/min owned
quota,source/corpus/model pre/post fingerprints. No production app or local
generation model loads. No public-paper question/passages are sent for inference.

Always report qualification_accepted=false,even if this one response succeeds.
No complete development/holdout or answer-quality conclusion follows. A provider
error label indicates what that provider reported,not a proof of underlying
cause. Preserve private settings/key/data/models/indexes/containers/recovery,
disabled defaults,and no deployment,push,merge or selector tuning.
