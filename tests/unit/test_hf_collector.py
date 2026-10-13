import json
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from src.commands.agent_collection import build_jobs
from src.commands.evaluate_agent import Measurements
from src.commands.evaluate_hf_agent import collect_hosted_attempt, plan_collection, validate_selection
from src.commands.hf_evaluation import MeasuredHF, create_hosted_app, load_protocol

from tests.unit.test_agent_collection import substantive
from tests.unit.test_agent_service import EVIDENCE, QUESTION, Search
from tests.unit.test_hf_client import envelope, settings
from tests.unit.test_hf_configuration import KEY, MODEL


class CountedStubSearch(Search):
    def search_chunks(self, query, **controls):
        from src.commands.evaluate_agent import _count

        _count("retrieval_calls")
        return super().search_chunks(query, **controls)

    search_hybrid = search_chunks


def test_offline_holdout_plan_is_fixed_and_never_requires_credentials():
    plan = plan_collection(Path("tests/test_output/week7-source-review-20261013-01"), split="holdout", model=MODEL)
    assert plan["status"] == "offline_plan" and not plan["inference_started"]
    assert len(plan["jobs"]) == 192 and plan["outbound_budget"] == 773
    assert "query" not in plan["jobs"][0]
    assert plan["configuration"]["model"] == MODEL


def test_versioned_pilot_plan_binds_fixture_and_remaining_approval():
    from src.commands.hf_qualification import REVISION_SHA256

    plan = plan_collection(Path("tests/test_output/week7-source-review-20261013-01"), split="development", model=MODEL,
        case_ids=["week7-development-narrative-rubrics-literal"], modes=["bm25"], transports=["json"], qualification_v2=True)
    assert plan["fixture_manifest_sha256"] == REVISION_SHA256
    assert plan["planned_outbound_budget"] == 13 and plan["outbound_budget"] == 11
    assert not plan["inference_started"]
    with pytest.raises(ValueError):
        plan_collection(Path("tests/test_output/week7-source-review-20261013-01"), split="holdout", model=MODEL, qualification_v2=True)


def test_holdout_cannot_subset_or_select_an_unqualified_model():
    with pytest.raises(ValueError):
        plan_collection(Path("tests/test_output/week7-source-review-20261013-01"), split="holdout", model=MODEL, case_ids=["case"])
    with pytest.raises(ValueError):
        plan_collection(Path("tests/test_output/week7-source-review-20261013-01"), split="development", model="unregistered")
    with pytest.raises(ValueError):
        validate_selection({"model": MODEL}, MODEL)


@pytest.mark.anyio
async def test_real_asgi_collection_accounts_for_hf_calls_and_unchanged_citations(stub_httpx, tmp_path):
    import logging

    from src.operations import request_context

    outputs = [{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "E1"}]
    stub_httpx(lambda request: httpx.Response(200, json=envelope(json.dumps(outputs.pop(0)),
                                  usage={"prompt_tokens": 100, "completion_tokens": 20})))
    config = settings(agent_enabled=True, api_rate_limit_path=str(tmp_path / "limits"))
    hf = MeasuredHF(config, outbound_budget=3)
    app = create_hosted_app(config, CountedStubSearch(), hf)
    handler = Measurements()
    logger = logging.getLogger("src.operations")
    previous = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    paper = {"arxiv_id": "2609.99999", "sections": [{"content": ""}, {"content": ""}, {"content": EVIDENCE}]}
    chunk = {"arxiv_id": "2609.99999", "section_index": 2, "chunk_index": 3, "section_title": "Method", "content": EVIDENCE}
    job = build_jobs([{"id": "case", "query": QUESTION}], modes=("bm25",), transports=("json",))[1]
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": KEY}) as client:
            record = await collect_hosted_attempt(client, job, handler, [paper], [chunk], hf, load_protocol(), memory=lambda: 4096)
        assert record["ok"] and record["hosted"]["outbound_attempts"] == 3
        assert record["measured"]["generation_calls"] == 3 and record["hosted"]["usage_complete"]
        assert record["response"]["model"] == MODEL and record["response"]["answer"] == f'"{EVIDENCE}" [1.1]'
        assert not hf.ledger and "query" not in record["hf_calls"][0]
        assert request_context.get() is None
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)
        await hf.aclose()


@pytest.mark.anyio
async def test_unknown_usage_prevents_collection_acceptance_even_when_answer_is_valid(stub_httpx, tmp_path):
    import logging

    stub_httpx(lambda request: httpx.Response(200, json=envelope('{"answer":"E1"}')))
    config = settings(agent_enabled=True, api_rate_limit_path=str(tmp_path / "limits"))
    hf = MeasuredHF(config, outbound_budget=1)
    app = create_hosted_app(config, CountedStubSearch(), hf)
    handler = Measurements()
    logger = logging.getLogger("src.operations")
    previous = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    response = substantive()
    paper = {"arxiv_id": "2609.99999", "sections": [{"content": ""}, {"content": ""}, {"content": EVIDENCE}]}
    chunk = {"arxiv_id": "2609.99999", "section_index": 2, "chunk_index": 3, "section_title": "Method", "content": EVIDENCE}
    job = build_jobs([{"id": "case", "query": response["query"]}], modes=("bm25",), transports=("json",))[0]
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": KEY}) as client:
            record = await collect_hosted_attempt(client, job, handler, [paper], [chunk], hf, load_protocol(), memory=lambda: 4096)
        assert record["ok"] and not record["hosted"]["usage_complete"]
        assert record["hosted"]["unknown_usage_attempts"] == 1
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)
        await hf.aclose()
