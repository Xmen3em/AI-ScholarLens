import json
from pathlib import Path

import httpx
import pytest
from src.commands import hf_reproduction
from src.commands.hf_reproduction import reproduce
from src.commands.hf_success_diagnostics import (
    BOOLEAN_FIELDS,
    COUNT_FIELDS,
    SUCCESS_DIAGNOSTICS_SHA256,
    inspect_relevance,
    load_success_contract,
)

from tests.unit.test_hf_client import envelope, settings

CASE = {"expected": {"relevant_markers": ["[1.1]"]}, "supplied_markers": ["[1.1]", "[1.2]"]}


@pytest.mark.parametrize(
    "markers,empty,membership,duplicate,missing,extra",
    [
        (["[1.1]"], False, True, False, 0, 0),
        ([], True, True, False, 1, 0),
        (["[1.2]"], False, True, False, 1, 1),
        (["private-generated-marker"], False, False, False, 1, 1),
        (["[1.1]", "[1.1]"], False, True, True, 0, 0),
    ],
)
def test_fixed_flags_distinguish_mismatch_without_returning_markers(markers, empty, membership, duplicate, missing, extra):
    result = inspect_relevance({"relevant_markers": markers}, CASE)
    assert set(result) == set(BOOLEAN_FIELDS + COUNT_FIELDS)
    assert result["returned_empty"] is empty and result["supplied_marker_membership"] is membership
    assert result["duplicate_markers"] is duplicate and result["missing_expected_marker_count"] == missing
    assert result["unexpected_marker_count"] == extra and result["marker_count"] == len(markers)
    assert all(type(result[key]) is bool for key in BOOLEAN_FIELDS)
    assert all(type(result[key]) is int and 0 <= result[key] <= 30 for key in COUNT_FIELDS)
    assert "private-generated-marker" not in json.dumps(result)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        {},
        {"relevant_markers": "private-text"},
        {"relevant_markers": [1]},
        {"relevant_markers": ["x"] * 31},
        {"relevant_markers": [], "private-extra-field": "private-text"},
    ],
)
def test_invalid_shapes_or_over_cap_values_cannot_become_diagnostics(raw):
    with pytest.raises(ValueError):
        inspect_relevance(raw, CASE)


def test_negative_expected_object_can_identify_false_positive():
    case = {**CASE, "expected": {"relevant_markers": []}}
    result = inspect_relevance({"relevant_markers": ["[1.1]"]}, case)
    assert result["expected_empty"] is True and result["expected_match"] is False
    assert result["unexpected_marker_count"] == 1 and result["missing_expected_marker_count"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"expected": None},
        {"expected": {"relevant_markers": ["not-supplied"]}},
        {"expected": {"relevant_markers": ["[1.1]", "[1.1]"]}},
        {"supplied_markers": ["[1.1]", "[1.1]"]},
        {"supplied_markers": [1]},
    ],
)
def test_invalid_local_labels_fail_without_retaining_fixture_values(changes):
    with pytest.raises(ValueError) as exc:
        inspect_relevance({"relevant_markers": []}, {**CASE, **changes})
    assert "not-supplied" not in str(exc.value) and "[1.1]" not in str(exc.value)


def test_count_boundary_and_order_mismatch_are_not_repaired():
    markers = [f"[{i}.1]" for i in range(30)]
    case = {"supplied_markers": markers, "expected": {"relevant_markers": markers}}
    result = inspect_relevance({"relevant_markers": list(reversed(markers))}, case)
    assert result["expected_match"] is False and result["marker_count"] == 30
    assert result["missing_expected_marker_count"] == result["unexpected_marker_count"] == 0
    assert result["supplied_marker_membership"] is True and result["duplicate_markers"] is False


def test_measurement_contract_is_frozen(tmp_path):
    load_success_contract()
    for path in Path("evaluation/week7_hf/success-diagnostics-v1").iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / "profile.json").write_text("{}")
    with pytest.raises(ValueError):
        load_success_contract(tmp_path)


@pytest.mark.anyio
@pytest.mark.parametrize("kind,empty", [("empty", True), ("unknown", False), ("http400", None), ("invalid", None)])
async def test_reproduction_adds_only_bounded_success_measurements(stub_httpx, tmp_path, kind, empty):
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quota.db")})

    def handler(request):
        if kind == "http400":
            return httpx.Response(
                400, json={"error": {"code": "json_validate_failed", "message": "private-text", "failed_generation": ""}}
            )
        raw = {"relevant_markers": [] if kind == "empty" else ["private-generated-marker"] if kind == "unknown" else [1]}
        body = envelope(json.dumps(raw))
        body["choices"][0]["message"]["reasoning_content"] = "private-reasoning-text"
        return httpx.Response(200, json=body)

    calls = stub_httpx(handler)
    result = await reproduce(config, "concise-positive", memory=lambda: 4096, experiment="prompt-comparison-v1")
    assert len(calls) == 1 and result["qualification_accepted"] is False
    assert result["success_diagnostic_manifest_sha256"] == SUCCESS_DIAGNOSTICS_SHA256
    if empty is None:
        assert result["decision_diagnostics"] is None
    else:
        assert result["decision_diagnostics"]["returned_empty"] is empty
    assert "private-generated-marker" not in json.dumps(result) and "private-reasoning-text" not in json.dumps(result)


@pytest.mark.anyio
async def test_boolean_response_has_no_relevance_measurements(stub_httpx, tmp_path):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope()))
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quota.db")})
    result = await reproduce(config, "minimal-boolean-256", memory=lambda: 4096)
    assert len(calls) == 1 and result["category"] == "passed"
    assert result["decision_diagnostics"] is None


@pytest.mark.anyio
async def test_unverified_measurement_contract_blocks_before_client_or_call(monkeypatch, stub_httpx):
    def rejected():
        raise ValueError("Success measurement input differs")

    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope()))
    monkeypatch.setattr(hf_reproduction, "load_success_contract", rejected)
    with pytest.raises(ValueError):
        await reproduce(settings(), "minimal-boolean-256", memory=lambda: 4096)
    assert calls == []
