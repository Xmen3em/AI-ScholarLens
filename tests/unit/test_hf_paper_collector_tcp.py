import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
import src.commands.evaluate_hf_agent as collector
from src.commands import hf_paper_client as funded
from src.commands.agent_collection import build_jobs
from src.commands.hf_evaluation import qualify
from src.commands.hf_paper_profile import load_profile
from src.commands.hf_qualification import load_revision
from src.commands.hf_schema_execution import load_cerebras, load_selectors

from tests.unit.test_agent_service import EVIDENCE, QUESTION
from tests.unit.test_hf_client import envelope
from tests.unit.test_hf_collector import CountedStubSearch
from tests.unit.test_hf_paper_client import client as funded_client


@pytest.mark.anyio
@pytest.mark.parametrize("path,transport,source_failure", [
    ("baseline", "json", False), ("baseline", "sse", False),
    ("agent", "json", False), ("agent", "sse", False), ("baseline", "json", True),
])
async def test_funded_real_loopback_collection_uses_chosen_pair_and_stops_client_breaches(
    tmp_path, monkeypatch, stub_httpx, path, transport, source_failure,
):
    original_http = httpx.AsyncClient
    qualification = load_cerebras()["cases"] + load_selectors()["cases"]
    outputs = [case["expected"] or {"query": "neural retrieval"} for case in qualification]
    outputs += ([{"in_scope": True}, {"relevant_markers": ["[1.1]"]}] if path == "agent" else []) + [{"answer": "E1"}]
    changed = False
    count = 0

    def answer(request):
        nonlocal count, changed
        count += 1
        response = httpx.Response(200, json=envelope(json.dumps(outputs.pop(0)), usage={"prompt_tokens": 100, "completion_tokens": 20}))
        if count == 5 and source_failure: changed = True
        return response

    calls = stub_httpx(answer)
    hf, grant = funded_client(tmp_path, monkeypatch)
    monkeypatch.setattr(funded, "source_hashes", lambda: {"changed": "source"} if changed else hf.source.copy())
    monkeypatch.setattr(httpx, "AsyncClient", original_http)

    def forbidden(*args, **kwargs):
        raise AssertionError("The funded factory must own every model call")

    monkeypatch.setattr(collector, "MeasuredHF", forbidden)
    search_client = SimpleNamespace(close=Mock())
    monkeypatch.setattr(collector, "OpenSearch", lambda **kwargs: search_client)
    monkeypatch.setattr(collector, "CountedSearch", lambda *args: CountedStubSearch())
    monkeypatch.setattr(collector, "CountedEmbedder", lambda *args: None)
    monkeypatch.setattr(collector, "free_memory_mib", lambda: 4096)

    async def immediate_window(*args): pass

    async def synthetic_qualification(client, profile, **kwargs):
        return await qualify(client, profile, memory=lambda: 4096, **kwargs)

    original_collect = collector.collect_hosted_attempt

    async def synthetic_collect(*args):
        return await original_collect(*args, memory=lambda: 4096)

    monkeypatch.setattr(collector, "wait_window", immediate_window)
    monkeypatch.setattr(collector, "qualify", synthetic_qualification)
    monkeypatch.setattr(collector, "collect_hosted_attempt", synthetic_collect)
    paper = {"arxiv_id": "2609.99999", "sections": [{"content": ""}, {"content": ""}, {"content": EVIDENCE}]}
    chunk = {"arxiv_id": "2609.99999", "section_index": 2, "chunk_index": 3, "section_title": "Method", "content": EVIDENCE}
    all_jobs = build_jobs([{"id": "case", "query": QUESTION}], modes=("bm25",), transports=(transport,))
    jobs = all_jobs if source_failure else [job for job in all_jobs if job["path"] == path]
    try:
        completion = await asyncio.wait_for(collector.run_collection(
            hf.settings, jobs, [paper], [chunk], tmp_path, load_profile(), 261,
            revision=load_revision(), hf_factory=lambda *args, **kwargs: hf,
        ), 20)
        assert completion["attempts"] == 1
        assert completion["status"] == ("stopped" if source_failure else "collected")
        assert completion["outbound_attempts"] == grant.used == len(calls) == (5 if source_failure else 8 if path == "agent" else 6)
        assert all(json.loads(request.content)["model"] == "openai/gpt-oss-120b:cerebras" for request in calls)
        record = json.loads((tmp_path / "records.jsonl").read_text())
        assert record["ok"] is (not source_failure)
        if not source_failure:
            assert record["response"]["model"] == "openai/gpt-oss-120b:cerebras"
        assert hf._client.is_closed
        search_client.close.assert_called_once()
    finally:
        await hf.aclose()
