import asyncio
import gzip
import json

import httpx
import pytest
from src.commands.evaluate_retrieval import digest
from src.commands.hf_error_structure import StructuralHF, diagnose_structure
from src.commands.hf_qualification import load_revision
from src.services.hf.client import HFGenerationError, HFTimeoutError

from tests.unit.test_hf_client import OPTIONS, envelope, settings
from tests.unit.test_hf_configuration import MODEL, TOKEN
from tests.unit.test_hf_error_structure import body


class CountedStream(httpx.AsyncByteStream):
    def __init__(self, chunks, *, blocked=None):
        self.chunks, self.blocked = chunks, blocked
        self.reads = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.reads += 1
            yield chunk
        if self.blocked:
            self.blocked.set()
            await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


@pytest.mark.anyio
@pytest.mark.parametrize("compressed", [False, True])
async def test_error_observer_replays_decoded_bytes_and_original_labels_without_content(stub_httpx, compressed):
    case = load_revision()["cases"][1]
    raw = body('{"relevant_markers":["wrong"]}')
    stream = CountedStream([gzip.compress(raw) if compressed else raw])
    calls = stub_httpx(lambda request: httpx.Response(400, stream=stream, headers={"Content-Encoding": "gzip"} if compressed else {}))
    hf = StructuralHF(settings())
    try:
        with pytest.raises(HFGenerationError) as error:
            await hf.generate(MODEL, case["prompt"], system=case["system"], response_format=case["schema"], options=OPTIONS)
        assert hf.attempts == len(calls) == 1 and stream.closed
        assert error.value.status_code == 400 and error.value.error_code == "json_validate_failed"
        assert hf.observer.diagnostics["schema_valid"] is True
        assert hf.observer.diagnostics["expected_match"] is False
        wire = json.loads(calls[0].content)
        del wire["model"]
        assert digest(wire) == "931ef8f69542e6e68308765a0f948978bd2299772b881889546b6039237934f3"
        serialized = json.dumps(hf.observer.diagnostics) + json.dumps(hf.ledger) + str(error.value)
        assert TOKEN not in serialized and "wrong" not in serialized
        with pytest.raises(HFGenerationError):
            await hf.generate(MODEL, "second", options=OPTIONS)
        assert len(calls) == 1
    finally:
        await hf.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("status", [200, 401, 402, 429, 500])
async def test_observer_leaves_other_statuses_to_original_handling(stub_httpx, status):
    calls = stub_httpx(lambda request: httpx.Response(status, json=envelope('{"relevant_markers":[]}') if status == 200 else {"error": TOKEN}))
    hf = StructuralHF(settings())
    try:
        if status == 200:
            assert (await hf.generate(MODEL, "synthetic", options=OPTIONS)).response == '{"relevant_markers":[]}'
        else:
            with pytest.raises(HFGenerationError) as caught:
                await hf.generate(MODEL, "synthetic", options=OPTIONS)
            assert caught.value.status_code == status
        assert len(calls) == 1 and hf.observer.diagnostics is None
    finally:
        await hf.aclose()


@pytest.mark.anyio
async def test_oversized_stream_closes_without_reading_the_remainder_or_exposing_partial_data(stub_httpx):
    stream = CountedStream([b'x' * 4096] * 10)
    calls = stub_httpx(lambda request: httpx.Response(400, stream=stream))
    hf = StructuralHF(settings())
    try:
        with pytest.raises(HFGenerationError) as caught:
            await hf.generate(MODEL, "synthetic", options=OPTIONS)
        assert stream.closed and stream.reads == 3 and len(calls) == 1
        assert caught.value.error_code is None and hf.observer.diagnostics["body_complete"] is False
        assert all(value is None for key, value in hf.observer.diagnostics.items() if key != "body_complete")
    finally:
        await hf.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("cancel", [False, True])
async def test_interrupted_error_reads_close_upstream_and_never_retry(stub_httpx, cancel):
    blocked = asyncio.Event()
    stream = CountedStream([b'{"error":'], blocked=blocked)
    calls = stub_httpx(lambda request: httpx.Response(400, stream=stream))
    hf = StructuralHF(settings(hf_timeout_seconds=1))
    try:
        task = asyncio.create_task(hf.generate(MODEL, "synthetic", options=OPTIONS))
        await asyncio.wait_for(blocked.wait(), 1)
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else HFTimeoutError):
            await task
        assert stream.closed and len(calls) == hf.attempts == 1
        assert hf.observer.diagnostics is None
    finally:
        await hf.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("success", [False, True])
async def test_one_structural_diagnostic_can_never_qualify_or_start_paper_jobs(stub_httpx, tmp_path, success):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope('{"relevant_markers":["[1.1]"]}',
                    usage={"prompt_tokens": 100, "completion_tokens": 20})) if success else httpx.Response(400, content=body('{"relevant_markers":[]}')))
    result = await diagnose_structure(settings(api_rate_limit_path=str(tmp_path / "quota")), memory=lambda: 4096)
    assert len(calls) == result["outbound_attempts"] == 1
    assert not result["qualification_accepted"] and result["kind"] == "error_structure_diagnostic_only"
    assert [check["id"] for check in result["qualification"]["checks"]] == ["relevance"]
    assert result["qualification"]["large_schema_preflight_rejected"]
    if success:
        assert result["error_structure"] is None
    else:
        assert result["error_structure"]["expected_match"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("memory", [500, float('nan'), float('inf')])
async def test_unavailable_or_insufficient_memory_stops_before_any_outbound_attempt(stub_httpx, tmp_path, memory):
    calls = stub_httpx(lambda request: httpx.Response(400, json={}))
    result = await diagnose_structure(settings(api_rate_limit_path=str(tmp_path / "quota")), memory=lambda: memory)
    assert not calls and result["outbound_attempts"] == 0 and result["error_structure"] is None
    assert not result["qualification_accepted"]
