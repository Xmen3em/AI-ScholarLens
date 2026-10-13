import asyncio
import json
from pathlib import Path

import httpx
import pytest
from src.commands.agent_collection import build_jobs
from src.commands.hf_evaluation import (
    HF_MANIFEST_SHA256,
    MeasuredHF,
    create_hosted_app,
    hosted_admission,
    hosted_work,
    load_protocol,
    qualify,
    validate_structured,
)
from src.middlewares import RateLimiter
from src.schemas.api.agent import ScopeDecision
from src.services.hf.client import HFGenerationError
from src.services.hf.rag import HostedRAGService

from tests.unit.test_agent_service import Search
from tests.unit.test_hf_client import OPTIONS, envelope, settings
from tests.unit.test_hf_configuration import MODEL, TOKEN


def test_hosted_freeze_references_local_manifest_without_replacing_it():
    profile = load_protocol()
    assert profile["development_jobs"] == 64 and profile["holdout_jobs"] == 192
    assert profile["qualification_calls"] == 5 and len(HF_MANIFEST_SHA256) == 64
    assert Path("evaluation/week7_agent/manifest.json").is_file()


def test_modified_hosted_protocol_is_rejected(tmp_path):
    source = Path("evaluation/week7_hf")
    for name in ("manifest.json", "PROTOCOL.md", "profile.json"):
        (tmp_path / name).write_bytes((source / name).read_bytes())
    (tmp_path / "PROTOCOL.md").write_text("altered policy")
    with pytest.raises(ValueError):
        load_protocol(tmp_path)


def test_hosted_memory_profile_is_separate_and_does_not_lower_local_gate():
    from src.commands.agent_collection import admission

    profile = load_protocol()
    jobs = build_jobs([{"id": "case", "query": "public AI question"}], modes=("bm25",), transports=("json",))
    assert hosted_admission(settings(), jobs, 1024, profile) is None
    assert hosted_admission(settings(), jobs, 1023, profile) == "insufficient_memory"
    jobs[0]["mode"] = "hybrid"
    assert hosted_admission(settings(), jobs, 1535, profile) == "insufficient_memory"
    assert hosted_admission(settings(), jobs, 1536, profile) is None
    assert admission(1536, candidate_count=1, required_installed=True) == "insufficient_memory"


@pytest.mark.parametrize("changes", [{"rag_sentence_candidates_per_passage": 2}, {"agent_deadline_seconds": 91},
                                     {"hf_timeout_seconds": 10}, {"api_generations_per_minute": 7},
                                     {"ollama_embedding_model": "different"}])
def test_hosted_admission_rejects_changed_frozen_controls(changes):
    assert hosted_admission(settings(**changes), [], 4096, load_protocol()) == "policy_changed"


@pytest.mark.parametrize("content", ['{"in_scope":"true"}', '{"in_scope":false,"in_scope":true}',
                                    '{"in_scope":true,"extra":1}'])
def test_structured_observer_rejects_bad_types_duplicates_or_fields(content):
    with pytest.raises(ValueError):
        validate_structured(content, ScopeDecision.model_json_schema())


@pytest.mark.anyio
async def test_measured_client_keeps_unknown_usage_unknown_and_never_persists_text(stub_httpx):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope('{"in_scope":true}')))
    client = MeasuredHF(settings(), outbound_budget=1)
    try:
        await client.generate(MODEL, "private question", response_format=ScopeDecision.model_json_schema(), options=OPTIONS)
        work = hosted_work(client.ledger["administrative"], load_protocol(), MODEL)
        assert work["outbound_attempts"] == 1 and work["unknown_usage_attempts"] == 1
        assert work["known_usage_cost_usd"] == 0 and not work["usage_complete"]
        assert "private question" not in json.dumps(work) and TOKEN not in json.dumps(client.ledger)
        with pytest.raises(HFGenerationError):
            await client.generate(MODEL, "another question", options=OPTIONS)
        assert len(calls) == 1
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_usage_and_schema_observer_does_not_change_application_output(stub_httpx):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope('{"in_scope":"true"}',
        usage={"prompt_tokens": 100, "completion_tokens": 10})))
    client = MeasuredHF(settings(), outbound_budget=1)
    try:
        result = await client.generate(MODEL, "question", response_format=ScopeDecision.model_json_schema(), options=OPTIONS)
        assert result.response == '{"in_scope":"true"}'
        work = hosted_work(client.ledger["administrative"], load_protocol(), MODEL)
        assert work["schema_violations"] == 1 and work["usage_complete"]
        assert work["known_usage_cost_usd"] == pytest.approx(0.0000225)
        assert len(calls) == 1
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_qualification_failure_stops_before_any_case_work_without_retry(stub_httpx, tmp_path):
    calls = stub_httpx(lambda request: httpx.Response(400, json={"error": TOKEN}))
    client = MeasuredHF(settings(api_rate_limit_path=str(tmp_path / "limits")), outbound_budget=5)
    try:
        result = await qualify(client, load_protocol(), limiter=RateLimiter(client.settings), memory=lambda: 4096)
        assert not result["qualified"] and len(calls) == 1
        assert len(result["checks"]) == 1 and TOKEN not in json.dumps(result)
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_synthetic_qualification_checks_all_schemas_and_large_input_rejection(stub_httpx, tmp_path):
    outputs = [{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"query": "neural retrieval evidence"},
               {"answer": "E1"}, {"answer": "E1 E10"}]

    def respond(request):
        return httpx.Response(200, json=envelope(json.dumps(outputs.pop(0)), usage={"prompt_tokens": 100, "completion_tokens": 20}))

    calls = stub_httpx(respond)
    client = MeasuredHF(settings(api_rate_limit_path=str(tmp_path / "limits")), outbound_budget=5)
    try:
        result = await qualify(client, load_protocol(), limiter=RateLimiter(client.settings), memory=lambda: 4096)
        assert result["qualified"] and len(calls) == 5
        assert result["large_schema_preflight_rejected"]
        assert all(check["ok"] for check in result["checks"])
        assert "neural retrieval evidence" not in json.dumps(result)
    finally:
        await client.aclose()


@pytest.mark.parametrize("markers", [[], ["1.1"], ["[1.1]", "[1.1]"]])
@pytest.mark.anyio
async def test_valid_schema_with_wrong_synthetic_decision_stops_qualification(stub_httpx, tmp_path, markers):
    outputs = [{"in_scope": True}, {"relevant_markers": markers}]
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope(json.dumps(outputs.pop(0)),
        usage={"prompt_tokens": 166, "completion_tokens": 50})))
    client = MeasuredHF(settings(api_rate_limit_path=str(tmp_path / "limits")), outbound_budget=13)
    try:
        result = await qualify(client, load_protocol(), limiter=RateLimiter(client.settings), memory=lambda: 4096)
        assert not result["qualified"] and len(calls) == client.attempts == 2
        assert len(result["checks"]) == 2 and result["checks"][0]["ok"]
        failed = result["checks"][1]
        assert failed["id"] == "relevance" and not failed["ok"] and failed["error_class"] == "ValueError"
        assert failed["calls"][0]["schema_valid"] is True
        assert failed["work"]["schema_violations"] == 0 and failed["work"]["usage_complete"]
        assert "relevant_markers" not in json.dumps(result) and "prompt" not in json.dumps(result)
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_hosted_app_has_no_production_lifespan_or_database(stub_httpx, tmp_path):
    stub_httpx(lambda request: httpx.Response(200, json=envelope()))
    config = settings(agent_enabled=True, api_rate_limit_path=str(tmp_path / "limits"))
    hf = MeasuredHF(config, outbound_budget=5)
    try:
        app = create_hosted_app(config, Search(), hf)
        assert type(app.state.rag) is HostedRAGService and app.state.rag.cache is None
        assert not hasattr(app.state, "database")
    finally:
        await hf.aclose()
