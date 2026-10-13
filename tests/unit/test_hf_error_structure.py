import json

import pytest
from src.commands.hf_error_structure import inspect_error
from src.commands.hf_qualification import load_revision

from tests.unit.test_hf_client import PRIVATE_QUESTION
from tests.unit.test_hf_configuration import TOKEN


def body(generation, **error):
    return json.dumps({"error": {"code": "json_validate_failed", "type": "invalid_request_error",
                                 "message": TOKEN + PRIVATE_QUESTION, "failed_generation": generation} | error}).encode()


def inspect(generation):
    return inspect_error(body(generation), load_revision()["cases"][1])


def test_expected_rejected_generation_is_reported_without_content():
    result = inspect('{"relevant_markers":["[1.1]"]}')
    assert result["body_complete"] and result["body_json_valid"] and result["error_object"]
    assert result["failed_generation_present"] and result["failed_generation_string"]
    assert result["generation_json_valid"] and result["generation_object"]
    assert result["schema_valid"] and result["expected_match"]
    assert result["supplied_marker_membership"] and not result["duplicate_markers"]
    assert result["marker_count"] == 1 and result["property_count"] == 1
    assert result["starts_object"] and result["ends_object"]


@pytest.mark.parametrize("generation,schema_valid,expected,membership,duplicates,count", [
    ('{"relevant_markers":[]}', True, False, True, False, 0),
    ('{"relevant_markers":["unknown"]}', True, False, False, False, 1),
    ('{"relevant_markers":["[1.1]","[1.1]"]}', True, False, True, True, 2),
    ('{"relevant_markers":"[1.1]"}', False, False, None, None, None),
    ('{"relevant_markers":[1]}', False, False, None, None, 1),
    ('{"relevant_markers":["[1.1]"],"private_extra":"secret"}', False, False, True, False, 1),
])
def test_schema_and_expected_decision_are_distinct(generation, schema_valid, expected, membership, duplicates, count):
    result = inspect(generation)
    assert result["schema_valid"] is schema_valid and result["expected_match"] is expected
    assert result["supplied_marker_membership"] is membership and result["duplicate_markers"] is duplicates
    assert result["marker_count"] == count


@pytest.mark.parametrize("generation", [
    '{"relevant_markers":["[1.1]"]',
    '```json\n{"relevant_markers":["[1.1]"]}\n```',
    '<think>private reasoning</think>{"relevant_markers":["[1.1]"]}',
    '{"relevant_markers":[],"relevant_markers":["[1.1]"]}',
    '{"relevant_markers":[NaN]}',
], ids=["truncated", "code-fence", "reasoning", "duplicate", "nonfinite"])
def test_malformed_duplicate_or_reasoning_content_is_never_repaired(generation):
    result = inspect(generation)
    assert result["generation_json_valid"] is False
    assert result["schema_valid"] is None and result["expected_match"] is None
    assert result["code_fence_prefix"] is generation.startswith('```')
    assert result["reasoning_prefix"] is generation.startswith('<think>')


def test_recursive_generated_json_is_bounded_without_propagating_the_parser_error():
    # Python 3.12's C JSON decoder permits 1100 levels independently of the
    # Python recursion limit; 3000 reproduces its RecursionError within 8 KiB.
    result = inspect('[' * 3000 + '0' + ']' * 3000)
    assert result["generation_json_valid"] is False and result["schema_valid"] is None


@pytest.mark.parametrize("value,string", [(None, False), (True, False), ({"secret": TOKEN}, False), ([], False), (42, False)])
def test_failed_generation_type_is_reported_only_as_boolean(value, string):
    result = inspect(value)
    assert result["failed_generation_present"] and result["failed_generation_string"] is string
    assert result["generation_json_valid"] is None


@pytest.mark.parametrize("raw,body_valid,error_object,present", [
    (b'not JSON', False, None, None),
    (b'{"error":{"failed_generation":"one","failed_generation":"two"}}', False, None, None),
    (b'{"error":NaN}', False, None, None),
    (b'\xff', False, None, None),
    (b'[]', True, False, None),
    (b'{"error":"secret"}', True, False, None),
    (b'{"error":{}}', True, True, False),
])
def test_missing_malformed_and_duplicate_envelopes_have_no_fabricated_diagnostics(raw, body_valid, error_object, present):
    result = inspect_error(raw, load_revision()["cases"][1])
    assert result["body_json_valid"] is body_valid and result["error_object"] is error_object
    assert result["failed_generation_present"] is present
    assert result["schema_valid"] is None


def test_counts_are_bounded_and_all_outputs_are_fixed_primitives():
    generation = json.dumps({"relevant_markers": [TOKEN] * 100, **{str(i): PRIVATE_QUESTION for i in range(100)}})
    result = inspect(generation)
    # Oversized provider bodies cannot supply any parsed diagnostics.
    assert result["body_complete"] is False and result["body_json_valid"] is None
    result = inspect(json.dumps({"relevant_markers": ["x"] * 40, **{str(i): 0 for i in range(40)}}))
    assert result["marker_count"] == result["property_count"] == 31
    assert result["schema_valid"] is False
    private = inspect(json.dumps({"relevant_markers": [TOKEN, PRIVATE_QUESTION], "arbitrary_key": TOKEN}))
    assert TOKEN not in json.dumps(private) and PRIVATE_QUESTION not in json.dumps(private)
    assert "arbitrary_key" not in json.dumps(private)
    for name, value in private.items():
        assert value is None or type(value) is bool or name in {"marker_count", "property_count", "generated_char_count"} and type(value) is int


def test_exact_error_body_boundary_is_not_silently_relaxed():
    raw = body('{"relevant_markers":[]}')
    padded = raw + b' ' * (8192 - len(raw))
    assert inspect_error(padded, load_revision()["cases"][1])["body_json_valid"]
    result = inspect_error(padded + b' ', load_revision()["cases"][1])
    assert result["body_complete"] is False and result["failed_generation_present"] is None
