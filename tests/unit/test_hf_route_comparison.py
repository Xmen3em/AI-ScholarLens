import copy
import json
from pathlib import Path

import httpx
import pytest
from src.commands.hf_qualification import load_revision
from src.commands.hf_route_comparison import RouteHF, compare_routes, load_comparison, verify_mapping
from src.middlewares import RateLimiter
from src.services.hf.client import HFGenerationError

from tests.unit.test_hf_client import envelope, settings
from tests.unit.test_hf_configuration import MODEL, TOKEN


def test_comparison_freezes_sdk_mapping_endpoints_and_parent_contract(tmp_path):
    profile = load_comparison()
    assert profile["route_order"] == ["unified", "provider-relay"]
    assert profile["maximum_outbound_attempts"] == 2 and not profile["qualification_accepted"]
    root = Path("evaluation/week7_hf/route-comparison-v1")
    for file in root.iterdir():
        (tmp_path / file.name).write_bytes(file.read_bytes())
    (tmp_path / "sources.json").write_text("changed mapping")
    with pytest.raises(ValueError):
        load_comparison(tmp_path)


@pytest.mark.parametrize("changes", [{"providerId": "different"}, {"status": "staging"}, {"task": "text-generation"}])
def test_live_mapping_cannot_silently_change_model_or_task(changes):
    row = {"providerId": "openai/gpt-oss-120b", "status": "live", "task": "conversational"} | changes
    with pytest.raises(ValueError):
        verify_mapping(row)


@pytest.mark.parametrize("first_passes", [True, False])
@pytest.mark.anyio
async def test_two_predeclared_routes_use_identical_contract_and_shared_quota(stub_httpx, tmp_path, first_passes):
    def respond(request):
        if request.url.path == "/v1/chat/completions" and not first_passes:
            return httpx.Response(400, json={"error": {"code": "json_validate_failed", "type": "invalid_request_error", "message": TOKEN}})
        return httpx.Response(200, json=envelope('{"relevant_markers":["[1.1]"]}', usage={"prompt_tokens": 100, "completion_tokens": 20}))

    calls = stub_httpx(respond)
    config = settings(api_rate_limit_path=str(tmp_path / "quota"))
    result = await compare_routes(config, memory=lambda: 4096)
    assert result["qualification_accepted"] is False and result["outbound_attempts"] == len(calls) == 2
    assert [row["route"] for row in result["arms"]] == ["unified", "provider-relay"]
    assert calls[0].url == "https://router.huggingface.co/v1/chat/completions"
    assert calls[1].url == "https://router.huggingface.co/groq/openai/v1/chat/completions"
    payloads = [json.loads(call.content) for call in calls]
    assert payloads[0]["model"] == MODEL and payloads[1]["model"] == "openai/gpt-oss-120b"
    assert [call.headers["Authorization"] for call in calls] == ["Bearer " + TOKEN] * 2
    normalized = [copy.deepcopy(payload) for payload in payloads]
    for payload in normalized:
        del payload["model"]
    assert normalized[0] == normalized[1]
    assert result["arms"][0]["contract_payload_sha256"] == result["arms"][1]["contract_payload_sha256"]
    assert all(payload["response_format"]["json_schema"]["strict"] is True for payload in payloads)
    assert TOKEN not in json.dumps(result) and "relevant_markers" not in json.dumps(result)
    quota = RateLimiter(config)
    assert not any(quota.reserve(generation=True) for _ in range(4)) and quota.reserve(generation=True)


@pytest.mark.anyio
async def test_relay_has_one_attempt_and_never_changes_original_client_or_result_identity(stub_httpx):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope('{"relevant_markers":["[1.1]"]}',
        usage={"prompt_tokens": 100, "completion_tokens": 20})))
    client = RouteHF(settings(), route="provider-relay")
    case = load_revision()["cases"][1]
    try:
        result = await client.generate(MODEL, case["prompt"], system=case["system"], response_format=case["schema"],
            options={"temperature": 0, "num_predict": 256, "num_ctx": 8192})
        assert result.model == MODEL
        with pytest.raises(HFGenerationError):
            await client.generate(MODEL, case["prompt"], response_format=case["schema"])
        assert len(calls) == 1
    finally:
        await client.aclose()


@pytest.mark.parametrize("route", ["auto", "https://example.com/", "provider-relay?url=evil"])
def test_arbitrary_endpoint_or_routing_strategy_rejected_before_client_creation(route):
    with pytest.raises(ValueError):
        RouteHF(settings(), route=route)


@pytest.mark.anyio
async def test_timeout_does_not_schedule_second_arm(stub_httpx, tmp_path):
    def timeout(request):
        raise httpx.ReadTimeout("private timeout")

    calls = stub_httpx(timeout)
    result = await compare_routes(settings(api_rate_limit_path=str(tmp_path / "quota")), memory=lambda: 4096)
    assert len(calls) == result["outbound_attempts"] == 1
    assert len(result["arms"]) == 1 and result["stop_reason"] == "uncertain_or_resource_work"


@pytest.mark.anyio
async def test_transport_error_stops_before_relay(stub_httpx, tmp_path):
    def disconnected(request):
        raise httpx.ReadError("private transport detail")

    calls = stub_httpx(disconnected)
    result = await compare_routes(settings(api_rate_limit_path=str(tmp_path / "quota")), memory=lambda: 4096)
    assert len(calls) == 1 and result["stop_reason"] == "uncertain_or_resource_work"


@pytest.mark.parametrize("memory", [599, float("nan")])
@pytest.mark.anyio
async def test_insufficient_or_unavailable_memory_starts_no_provider_work(stub_httpx, tmp_path, memory):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope()))
    result = await compare_routes(settings(api_rate_limit_path=str(tmp_path / "quota")), memory=lambda: memory)
    assert not calls and result["outbound_attempts"] == 0 and not result["arms"]


@pytest.mark.anyio
async def test_resource_margin_loss_stops_between_arms(stub_httpx, tmp_path):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope('{"relevant_markers":["[1.1]"]}',
        usage={"prompt_tokens": 100, "completion_tokens": 20})))
    result = await compare_routes(settings(api_rate_limit_path=str(tmp_path / "quota")), memory=lambda: 4096 if not calls else 500)
    assert len(calls) == 1 and result["outbound_attempts"] == 1
    assert result["stop_reason"] == "uncertain_or_resource_work"
