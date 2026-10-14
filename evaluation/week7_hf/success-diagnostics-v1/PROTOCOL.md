# Bounded relevance decision measurements v1 — 2026-10-14

Diagnostic-only metadata after original canonical relevance schema validation.
Fixed fields: expected_match,expected_empty,returned_empty,
supplied_marker_membership,duplicate_markers,marker_count,expected_marker_count,
missing_expected_marker_count,unexpected_marker_count. Boolean fields are actual
booleans; counts are integers0–30. Extra fields/types/shapes are rejected.

Expected markers must be unique members of the bounded supplied marker list.
Generated arrays retain original30-item/string constraints. Generated duplicates
and unknown markers are observed, not repaired/accepted. Expected object equality
remains the existing mandatory guard. No generated strings,reasoning,arbitrary
keys,error messages or content-derived hashes are retained. Invalid schema/HTTP
errors/non-relevance decisions keep null successful-response measurements.

This contract does not alter requests,original schema/system/prompts/limits,
app/defaults,error handling or qualification acceptance. It cannot reconstruct
old discarded outputs. Old frozen input artifacts and records are immutable.
Future diagnostic records include this measurement manifest hash separately from
their input manifest. All original13 and extension6 attempt slots are exhausted;
no live work/new allowance is authorized by this offline implementation.
