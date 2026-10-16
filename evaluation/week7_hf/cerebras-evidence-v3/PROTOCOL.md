# Cerebras bounded evidence catalog v3

This additive profile explicitly admits the corrected evidence experiment for
openai/gpt-oss-120b:cerebras. It grants no calls or runtime activation. All older
hosted/Cerebras manifests and their evidence remain immutable.

Only candidate availability changes from the tokenized v2 profile: offer up to
three whole sentences per passage and at most ten candidates in total. Offer
first candidates across passages before second and third candidates. Preserve
source wording, the original lexical eligibility and sentence-length filters,
quote validation and the three-excerpt/200-word answer bound. Expanded selection
must answer the requested fact; sharing a topic or method name is insufficient.
The clarified scope instruction is source-bound and includes every ingested
category, including robotics, while separating topic from answer availability.
The frozen controller system and all five synthetic qualification payloads stay
unchanged. The oversized thirty-candidate schema must still reject locally.

Every other v2 field remains identical: model and dated rates, semantic coverage,
relevance/abstention/attribution/latency gates, full 64/192 matrices, source/corpus/
model preservation, native input counting and byte caps, 8192-token context,
512-token template reserve, 256/512 output limits, six calls/two retrievals/one
rewrite/eight stages, quota windows, deadlines, and all RAM thresholds.

The saved-citation replay established literal evidence availability, not better
model decisions or task acceptance. Fresh five-case qualification and a complete
reviewed development comparison are still required. Holdout is separately funded
only after accepted development; runtime requires accepted full holdout and an
actual owner Telegram check. No holdout labels are used to tune this profile.

Development has a maximum of 261 attempts, holdout 773. Failed or uncertain work
counts. Preserve the previous 28 schema/prompt attempts and 97 completed failed-
development attempts; their 164 unused slots cannot be silently transferred.
This profile uses separate fixed, source/history-bound receipts and ledgers and
requires explicit new approval. No replay, reset, fallback or inference retry.
