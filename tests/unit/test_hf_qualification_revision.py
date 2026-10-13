import json
from pathlib import Path

import httpx
import pytest
from src.commands.hf_evaluation import MeasuredHF, load_protocol, qualification_cases, qualify
from src.commands.hf_qualification import decision_diagnostics, load_revision
from src.middlewares import RateLimiter
from src.operations import request_context
from src.services.agent import CONTROLLER_SYSTEM

from tests.unit.test_hf_client import envelope, settings


def test_revision_freezes_exact_inputs_and_retains_original_contracts():
    revision = load_revision()
    assert revision["version"] == "qualification-v2" and len(revision["manifest_sha256"]) == 64
    for case, original in zip(revision["cases"], qualification_cases(), strict=True):
        assert case["id"] == original["id"] and case["schema"] == original["schema"]
        assert case["expected"] == original["expected"]
    for case in revision["cases"][:3]:
        assert case["system"] == CONTROLLER_SYSTEM and "\nData:\n" in case["prompt"]
    relevance = revision["cases"][1]
    data = json.loads(relevance["prompt"].split("\nData:\n")[1])
    assert data["passages"][0]["marker"] == "[1.1]"
    for case in revision["cases"][3:]:
        data = json.loads(case["prompt"].split("\nData:\n")[1])
        assert data["target"] == case["expected"]
        assert len(data["evidence_catalog"]) == int(case["id"].split("-")[1])


def test_changed_prompt_or_expected_value_invalidates_revision(tmp_path):
    root = Path("evaluation/week7_hf/qualification-v2")
    for file in root.iterdir():
        if file.is_file():
            (tmp_path / file.name).write_bytes(file.read_bytes())
    path = tmp_path / "fixtures.json"
    fixture = json.loads(path.read_text())
    fixture["cases"][1]["prompt"] = "changed"
    path.write_text(json.dumps(fixture))
    with pytest.raises(ValueError):
        load_revision(tmp_path)


@pytest.mark.parametrize("markers,expected", [([], (False, True, False, 0)),
    (["1.1"], (False, False, False, 1)), (["[1.1]", "[1.1]"], (False, True, True, 2)),
    (["[1.1]"], (True, True, False, 1))])
def test_mismatch_diagnostics_are_bounded_and_never_include_decision_text(markers, expected):
    result = decision_diagnostics({"relevant_markers": markers}, load_revision()["cases"][1])
    assert tuple(result.values()) == expected
    assert all(type(value) in {bool, int} for value in result.values())


@pytest.mark.anyio
async def test_qualification_uses_frozen_wire_inputs_and_records_private_diagnostics(stub_httpx, tmp_path):
    revision = load_revision()
    outputs = [{"in_scope": True}, {"relevant_markers": ["1.1"]}]
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope(json.dumps(outputs.pop(0)),
        usage={"prompt_tokens": 100, "completion_tokens": 20})))
    config = settings(api_rate_limit_path=str(tmp_path / "limits"))
    hf = MeasuredHF(config, outbound_budget=11)
    try:
        result = await qualify(hf, load_protocol(), limiter=RateLimiter(config), memory=lambda: 4096, revision=revision)
        assert not result["qualified"] and len(calls) == 2
        assert result["fixture_manifest_sha256"] == revision["manifest_sha256"]
        failed = result["checks"][1]
        assert failed["diagnostics"]["expected_match"] is False
        assert failed["diagnostics"]["supplied_marker_membership"] is False
        assert "fixture_sha256" in failed and "relevant_markers" not in json.dumps(result)
        wire = json.loads(calls[1].content)
        assert wire["messages"] == [{"role": "system", "content": revision["cases"][1]["system"]},
                                     {"role": "user", "content": revision["cases"][1]["prompt"]}]
    finally:
        await hf.aclose()


@pytest.mark.anyio
async def test_remaining_run_ceiling_stops_before_twelfth_outbound_call(stub_httpx):
    from src.services.hf.client import HFGenerationError

    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope(usage={"prompt_tokens": 100, "completion_tokens": 20})))
    hf = MeasuredHF(settings(), outbound_budget=11)
    scope = load_revision()["cases"][0]
    try:
        for index in range(12):
            token = request_context.set({"request_id": str(index)})
            try:
                work = hf.generate(hf.settings.hf_default_model, scope["prompt"], system=scope["system"],
                    response_format=scope["schema"], options={"temperature": 0, "num_predict": 256, "num_ctx": 8192})
                if index == 11:
                    with pytest.raises(HFGenerationError):
                        await work
                else:
                    await work
            finally:
                request_context.reset(token)
        assert len(calls) == hf.attempts == 11
    finally:
        await hf.aclose()
