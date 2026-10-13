import copy
import json
from pathlib import Path

import httpx
import pytest
from src.commands.hf_reproduction import ReproductionHF, load_reproduction, reproduce
from src.services.hf.client import HFGenerationError

from tests.unit.test_hf_client import envelope, settings

ARMS = ("minimal-boolean-256", "exact-relevance-512", "without-maxitems-256", "without-maxitems-512")


def test_frozen_arms_isolate_limits_and_one_schema_keyword():
    profile = load_reproduction()
    assert tuple(profile["arms"]) == ARMS
    exact = profile["arms"][ARMS[1]]["payload"]
    low = profile["arms"][ARMS[2]]["payload"]
    high = profile["arms"][ARMS[3]]["payload"]
    assert low | {"max_tokens": 512} == high
    stripped = copy.deepcopy(exact)
    del stripped["response_format"]["json_schema"]["schema"]["properties"]["relevant_markers"]["maxItems"]
    assert stripped == high
    assert all(arm["payload"]["response_format"]["json_schema"]["strict"] is True for arm in profile["arms"].values())


def test_changed_freeze_rejects_before_network(tmp_path):
    root = Path("evaluation/week7_hf/reproduction-v1")
    for path in root.iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / "requests.json").write_text("{}")
    with pytest.raises(ValueError):
        load_reproduction(tmp_path)


@pytest.mark.anyio
@pytest.mark.parametrize("arm", ARMS)
async def test_sends_only_frozen_public_payload_and_discards_success_text(stub_httpx, tmp_path, arm):
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quota.db")})
    case = load_reproduction()["arms"][arm]["case"]
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope(
        json.dumps(case["expected"]), usage={"prompt_tokens": 80, "completion_tokens": 12})))
    result = await reproduce(config, arm, memory=lambda: 4096)
    assert len(calls) == 1 and json.loads(calls[0].content) == load_reproduction()["arms"][arm]["payload"]
    assert str(calls[0].url) == "https://router.huggingface.co/v1/chat/completions"
    assert result["category"] == "passed" and result["outbound_attempts"] == 1
    assert result["qualification_accepted"] is False
    assert "content" not in json.dumps(result) and "Authorization" not in json.dumps(result)


@pytest.mark.anyio
@pytest.mark.parametrize("arm", ARMS)
async def test_failed_generation_is_content_free_and_unknown_cost(stub_httpx, tmp_path, arm):
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quota.db")})
    calls = stub_httpx(lambda request: httpx.Response(400, json={"error": {
        "code": "json_validate_failed", "type": "invalid_request_error", "message": "private-error-text",
        "failed_generation": "private-reasoning-text"}}))
    result = await reproduce(config, arm, memory=lambda: 4096)
    assert result["category"] == "provider_json_validation" and len(calls) == 1
    assert result["work"]["unknown_usage_attempts"] == 1
    assert result["error_structure"]["generated_char_count"] == len("private-reasoning-text")
    assert "private-error-text" not in json.dumps(result) and "private-reasoning-text" not in json.dumps(result)


@pytest.mark.anyio
@pytest.mark.parametrize("response,category", [
    ('{"relevant_markers":[]}', "expected_mismatch"),
    ('{"relevant_markers":["[9.9]"]}', "expected_mismatch"),
    ('{"relevant_markers":[1]}', "schema_invalid"),
    ('{"relevant_markers":[],"extra":"private-generated-text"}', "schema_invalid"),
])
async def test_local_original_contract_and_expected_answer_still_apply(stub_httpx, tmp_path, response, category):
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quota.db")})
    stub_httpx(lambda request: httpx.Response(200, json=envelope(response)))
    result = await reproduce(config, "without-maxitems-256", memory=lambda: 4096)
    assert result["category"] == category and result["qualification_accepted"] is False
    assert "private-generated-text" not in json.dumps(result)


@pytest.mark.anyio
async def test_memory_floor_prevents_calls_and_releases_client(stub_httpx, tmp_path):
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quota.db")})
    calls = stub_httpx(lambda request: pytest.fail("unadmitted network"))
    result = await reproduce(config, ARMS[0], memory=lambda: 599)
    assert not calls and result["outbound_attempts"] == 0 and result["category"] == "resource_stop"


@pytest.mark.anyio
async def test_one_attempt_cap_prevents_second_request(stub_httpx):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope()))
    hf = ReproductionHF(settings(), ARMS[0])
    case = hf.arm["case"]
    options = {"temperature": 0, "num_predict": 256, "num_ctx": 8192}
    try:
        await hf.generate(hf.settings.hf_default_model, case["prompt"], system=case["system"], response_format=case["schema"], options=options)
        with pytest.raises(HFGenerationError):
            await hf.generate(hf.settings.hf_default_model, case["prompt"], system=case["system"], response_format=case["schema"], options=options)
        assert len(calls) == 1
    finally:
        await hf.aclose()


@pytest.mark.anyio
async def test_unknown_arm_rejects_before_client_creation(stub_httpx):
    calls = stub_httpx(lambda request: pytest.fail("unknown arm network"))
    with pytest.raises(ValueError):
        await reproduce(settings(), "unfrozen", memory=lambda: 4096)
    assert not calls


@pytest.mark.anyio
async def test_removed_wire_keyword_does_not_remove_original_thirty_marker_guard(stub_httpx, tmp_path):
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quota.db")})
    stub_httpx(lambda request: httpx.Response(200, json=envelope(json.dumps({"relevant_markers": ["[1.1]"] * 31}))))
    result = await reproduce(config, "without-maxitems-512", memory=lambda: 4096)
    assert result["category"] == "schema_invalid" and result["schema_valid"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("kind,category", [("timeout", "timeout"), ("transport", "transport_or_response_error"),
                                          ("length", "transport_or_response_error"), ("status", "provider_error")])
async def test_failures_are_fixed_categories_without_provider_content(stub_httpx, tmp_path, kind, category):
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quota.db")})

    def handler(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("private-network-text")
        if kind == "transport":
            raise httpx.ConnectError("private-network-text")
        if kind == "status":
            return httpx.Response(503, json={"error": {"message": "private-network-text"}})
        value = envelope("private-network-text")
        value["choices"][0]["finish_reason"] = "length"
        return httpx.Response(200, json=value)

    calls = stub_httpx(handler)
    result = await reproduce(config, ARMS[0], memory=lambda: 4096)
    assert result["category"] == category and len(calls) == 1
    assert result["work"]["unknown_usage_attempts"] == 1
    assert "private-network-text" not in json.dumps(result)


@pytest.mark.anyio
async def test_frozen_arm_cannot_send_changed_controls_or_prompt(stub_httpx):
    calls = stub_httpx(lambda request: pytest.fail("changed request"))
    hf = ReproductionHF(settings(), ARMS[0])
    try:
        with pytest.raises(ValueError):
            await hf.generate(hf.settings.hf_default_model, "changed prompt", response_format=hf.arm["case"]["schema"])
        assert not calls and hf.attempts == 0
    finally:
        await hf.aclose()
