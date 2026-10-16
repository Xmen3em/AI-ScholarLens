import asyncio
import json

import httpx
import pytest
from src.commands import hf_paper_client as command
from src.commands.hf_paper_allowance import TaskAllowance
from src.commands.hf_schema_execution import load_cerebras, load_selectors
from src.services.hf.client import HFGenerationError, HFTimeoutError

from tests.unit.test_hf_client import envelope, settings
from tests.unit.test_hf_paper_allowance import setup
from tests.unit.test_hf_tokenizer import install_vocabulary


def client(tmp_path, monkeypatch, *, memory=lambda: 4096):
    install_vocabulary(tmp_path, monkeypatch)
    metadata, approval, path = setup(tmp_path, monkeypatch)
    grant = TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
    source = metadata["source_sha256"]
    monkeypatch.setattr(command, "source_hashes", lambda: source.copy())
    config = settings(hf_models=["openai/gpt-oss-120b:cerebras"], hf_default_model="openai/gpt-oss-120b:cerebras",
                      agent_enabled=True, answer_cache_enabled=False, local_tracing_enabled=False,
                      monitoring_directory=None, rag_sentence_candidates_per_passage=1,
                      api_rate_limit_path=str(tmp_path / "quotas.sqlite3"))
    return command.FundedHF(config, grant=grant, output=tmp_path, source=source, outbound_budget=261, memory=memory), grant


def arguments(case):
    return {"system": case["system"], "response_format": case["schema"],
            "options": {"temperature": 0, "num_predict": 512 if case["id"].startswith("selector") else 256, "num_ctx": 8192}}


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["generate", "generate_result"])
async def test_both_generation_apis_reserve_once_and_cannot_replay_after_restart(tmp_path, monkeypatch, stub_httpx, method):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope(usage={"prompt_tokens": 100, "completion_tokens": 20})))
    hf, grant = client(tmp_path, monkeypatch)
    case = load_cerebras()["cases"][0]
    try:
        await getattr(hf, method)(hf.settings.hf_default_model, case["prompt"], **arguments(case))
        assert hf.attempts == grant.used == len(calls) == 1
        assert not hf.halted
        with pytest.raises(ValueError):
            command.FundedHF(hf.settings, grant=grant, output=tmp_path / "new", source=hf.source,
                             outbound_budget=261, memory=lambda: 4096)
        assert len(calls) == 1
    finally:
        await hf.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["source", "memory", "payload", "capacity"])
async def test_preflight_rejections_do_not_reserve_or_send(tmp_path, monkeypatch, stub_httpx, failure):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope()))
    hf, grant = client(tmp_path, monkeypatch, memory=lambda: 599 if failure == "memory" else 4096)
    case = load_cerebras()["cases"][0]
    if failure == "source": monkeypatch.setattr(command, "source_hashes", lambda: {"changed": "source"})
    if failure == "capacity": hf._busy = True
    try:
        with pytest.raises((ValueError, HFGenerationError)):
            await hf.generate_result(hf.settings.hf_default_model, case["prompt"] + (" changed" if failure == "payload" else ""),
                                     **arguments(case))
        assert hf.attempts == grant.used == len(calls) == 0
    finally:
        hf._busy = False
        await hf.aclose()


@pytest.mark.anyio
async def test_frozen_funded_client_rejects_an_unregistered_candidate_catalog(tmp_path, monkeypatch, stub_httpx):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope()))
    hf, grant = client(tmp_path, monkeypatch)
    try:
        with pytest.raises(ValueError):
            command.FundedHF(hf.settings.model_copy(update={"rag_max_sentence_candidates": 10}),
                             grant=grant, output=tmp_path / "new", source=hf.source,
                             outbound_budget=261, memory=lambda: 4096)
        assert grant.used == len(calls) == 0
    finally:
        await hf.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["400", "timeout", "missing_usage", "schema"])
async def test_wire_or_measurement_failure_consumes_one_and_stops_next_valid_call(tmp_path, monkeypatch, stub_httpx, failure):
    def respond(request):
        if failure == "400": return httpx.Response(400, json={"error": {"code": "json_validate_failed"}})
        if failure == "timeout": raise httpx.ReadTimeout("private provider text", request=request)
        usage = {} if failure == "missing_usage" else {"usage": {"prompt_tokens": 100, "completion_tokens": 20}}
        return httpx.Response(200, json=envelope('{"in_scope":"invalid"}' if failure == "schema" else '{"in_scope":true}', **usage))

    calls = stub_httpx(respond)
    hf, grant = client(tmp_path, monkeypatch)
    cases = load_cerebras()["cases"]
    try:
        if failure in {"400", "timeout"}:
            with pytest.raises((HFGenerationError, HFTimeoutError)):
                await hf.generate(hf.settings.hf_default_model, cases[0]["prompt"], **arguments(cases[0]))
        else:
            await hf.generate(hf.settings.hf_default_model, cases[0]["prompt"], **arguments(cases[0]))
        assert hf.halted
        with pytest.raises(HFGenerationError):
            await hf.generate(hf.settings.hf_default_model, cases[1]["prompt"], **arguments(cases[1]))
        assert hf.attempts == grant.used == len(calls) == 1
    finally:
        await hf.aclose()


@pytest.mark.anyio
async def test_direct_result_cannot_bypass_six_call_request_bound(tmp_path, monkeypatch, stub_httpx):
    cases = load_cerebras()["cases"] + load_selectors()["cases"]
    outputs = [case["expected"] or {"query": "neural retrieval"} for case in cases] + [{"in_scope": True}]
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope(json.dumps(outputs.pop(0)),
                                                      usage={"prompt_tokens": 100, "completion_tokens": 20})))
    hf, grant = client(tmp_path, monkeypatch)
    try:
        for case in cases + [cases[0]]:
            await hf.generate_result(hf.settings.hf_default_model, case["prompt"], **arguments(case))
        with pytest.raises(HFGenerationError):
            await hf.generate_result(hf.settings.hf_default_model, cases[0]["prompt"], **arguments(cases[0]))
        assert hf.attempts == grant.used == len(calls) == 6
    finally:
        await hf.aclose()


@pytest.mark.anyio
async def test_settlement_failure_stops_further_wire_and_keeps_uncertainty_reserved(tmp_path, monkeypatch, stub_httpx):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope(usage={"prompt_tokens": 100, "completion_tokens": 20})))
    hf, grant = client(tmp_path, monkeypatch)
    cases = load_cerebras()["cases"]

    def unavailable(*args):
        raise OSError("private storage detail")

    monkeypatch.setattr(grant, "settle", unavailable)
    try:
        with pytest.raises(OSError):
            await hf.generate_result(hf.settings.hf_default_model, cases[0]["prompt"], **arguments(cases[0]))
        assert grant.used == 1 and hf.halted
        with pytest.raises(HFGenerationError):
            await hf.generate_result(hf.settings.hf_default_model, cases[1]["prompt"], **arguments(cases[1]))
        assert len(calls) == 1
    finally:
        await hf.aclose()


@pytest.mark.anyio
async def test_cancelled_wire_is_consumed_and_not_replayable(tmp_path, monkeypatch, stub_httpx):
    entered = asyncio.Event()

    async def blocked(request):
        entered.set()
        await asyncio.Event().wait()

    calls = stub_httpx(blocked)
    hf, grant = client(tmp_path, monkeypatch)
    case = load_cerebras()["cases"][0]
    task = asyncio.create_task(hf.generate_result(hf.settings.hf_default_model, case["prompt"], **arguments(case)))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert hf.halted and not hf._busy and hf.attempts == grant.used == len(calls) == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await hf.aclose()
