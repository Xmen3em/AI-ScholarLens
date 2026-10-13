import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
import src.commands.evaluate_hf_agent as collector
from src.commands.agent_collection import build_jobs
from src.commands.hf_evaluation import MeasuredHF, load_protocol, qualify

from tests.unit.test_agent_service import EVIDENCE, QUESTION
from tests.unit.test_hf_client import envelope, settings
from tests.unit.test_hf_collector import CountedStubSearch


@pytest.mark.anyio
@pytest.mark.parametrize("versioned", [False, True])
async def test_real_loopback_collector_has_no_production_lifespan_and_closes_owned_resources(stub_httpx, monkeypatch, tmp_path, versioned):
    from src.commands.hf_qualification import load_revision

    revision = load_revision() if versioned else None
    original_http = httpx.AsyncClient
    outputs = [{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"query": "neural retrieval evidence"},
               {"answer": "E1"}, {"answer": "E1 E10"}, {"answer": "E1"}]
    stub_httpx(lambda request: httpx.Response(200, json=envelope(json.dumps(outputs.pop(0)),
                                      usage={"prompt_tokens": 100, "completion_tokens": 20})))
    config = settings(agent_enabled=True, api_rate_limit_path=str(tmp_path / "quotas.sqlite3"))
    hf = MeasuredHF(config, outbound_budget=7)
    # Keep only HF on MockTransport; the caller/server use actual loopback TCP.
    monkeypatch.setattr(httpx, "AsyncClient", original_http)
    monkeypatch.setattr(collector, "MeasuredHF", lambda *args, **kwargs: hf)
    search_client = SimpleNamespace(close=Mock())
    monkeypatch.setattr(collector, "OpenSearch", lambda **kwargs: search_client)
    monkeypatch.setattr(collector, "CountedSearch", lambda *args: CountedStubSearch())
    monkeypatch.setattr(collector, "CountedEmbedder", lambda *args: None)
    monkeypatch.setattr(collector, "free_memory_mib", lambda: 4096)

    async def immediate_window(*args):
        pass

    async def synthetic_qualification(client, profile, **kwargs):
        return await qualify(client, profile, memory=lambda: 4096, **kwargs)

    original_collect = collector.collect_hosted_attempt

    async def synthetic_memory_collect(*args):
        return await original_collect(*args, memory=lambda: 4096)

    monkeypatch.setattr(collector, "wait_window", immediate_window)
    monkeypatch.setattr(collector, "qualify", synthetic_qualification)
    monkeypatch.setattr(collector, "collect_hosted_attempt", synthetic_memory_collect)
    paper = {"arxiv_id": "2609.99999", "sections": [{"content": ""}, {"content": ""}, {"content": EVIDENCE}]}
    chunk = {"arxiv_id": "2609.99999", "section_index": 2, "chunk_index": 3, "section_title": "Method", "content": EVIDENCE}
    jobs = build_jobs([{"id": "case", "query": QUESTION}], modes=("bm25",), transports=("sse",))[:1]
    completion = await collector.run_collection(config, jobs, [paper], [chunk], tmp_path, load_protocol(), 7, revision=revision)
    assert completion["status"] == "collected" and completion["outbound_attempts"] == 6
    assert completion["attempts"] == 1 and hf._client.is_closed
    search_client.close.assert_called_once()
    record = json.loads((tmp_path / "records.jsonl").read_text())
    assert record["ok"] and record["hosted"]["usage_complete"]
    assert record["first_delta_ms"] >= 0
    qualification = json.loads((tmp_path / "qualification.json").read_text())
    if versioned:
        assert qualification["fixture_manifest_sha256"] == revision["manifest_sha256"]
        assert all(check["diagnostics"]["expected_match"] for check in qualification["checks"])
