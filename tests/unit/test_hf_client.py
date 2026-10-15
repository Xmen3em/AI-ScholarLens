import asyncio
import json
import traceback

import httpx
import pytest
from src.config import Settings
from src.exceptions import UnsupportedModelError
from src.schemas.api.agent import ScopeDecision
from src.services.hf.client import HFClient, HFGenerationError, HFResponseError, HFTimeoutError

from tests.unit.test_hf_configuration import KEY, MODEL, TOKEN

OPTIONS = {"temperature": 0, "num_predict": 256, "num_ctx": 8192}
PRIVATE_QUESTION = "sensitive user question sentinel"


def settings(**values):
    return Settings(_env_file=None, hf_inference_enabled=True, hf_token=TOKEN, api_key=KEY, **values)


def envelope(content='{"in_scope":true}', **updates):
    return {"model": "provider-internal-model-name", "choices": [
        {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}
    ]} | updates


@pytest.mark.anyio
async def test_exact_schema_and_pinned_route_with_real_usage_no_reasoning_leak(stub_httpx):
    payload = envelope(usage={"prompt_tokens": 80, "completion_tokens": 9,
                              "completion_tokens_details": {"reasoning_tokens": 4}})
    payload["choices"][0]["message"]["reasoning_content"] = "private provider reasoning"
    calls = stub_httpx(lambda request: httpx.Response(200, json=payload))
    client = HFClient(settings())
    schema = ScopeDecision.model_json_schema()
    try:
        result = await client.generate_result(MODEL, "question", system="fixed system",
                                              response_format=schema, options=OPTIONS)
        assert result.input_tokens == 80 and result.output_tokens == 9 and result.reasoning_tokens == 4
        assert "private provider reasoning" not in result.model_dump_json()
        assert result.model == MODEL and client.attempts == 1
        request = calls[0]
        assert str(request.url) == "https://router.huggingface.co/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer " + TOKEN
        wire = json.loads(request.content)
        assert wire == {"model": MODEL, "messages": [{"role": "system", "content": "fixed system"},
                                                     {"role": "user", "content": "question"}],
                        "stream": False, "max_tokens": 256, "temperature": 0,
                        "reasoning_effort": "low", "response_format": {"type": "json_schema",
                         "json_schema": {"name": "bounded_generation", "strict": True, "schema": schema}}}
        assert "num_ctx" not in wire and schema == ScopeDecision.model_json_schema()
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("count", [1, 10])
async def test_original_selector_patterns_are_forwarded_without_modification(stub_httpx, count):
    from src.services.rag.service import _selection_pattern

    schema = {"type": "object", "properties": {"answer": {"type": "string", "pattern": _selection_pattern(count)}},
              "required": ["answer"], "additionalProperties": False}
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope('{"answer":"NONE"}')))
    client = HFClient(settings())
    try:
        await client.generate(MODEL, "question", response_format=schema)
        assert json.loads(calls[0].content)["response_format"]["json_schema"]["schema"] == schema
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("error,expected", [(httpx.ConnectError, HFGenerationError), (httpx.ReadTimeout, HFTimeoutError)])
async def test_transport_failures_do_not_leak_messages_or_retry(stub_httpx, error, expected):
    def fail(request):
        raise error(TOKEN, request=request)

    calls = stub_httpx(fail)
    client = HFClient(settings())
    try:
        with pytest.raises(expected) as caught:
            await client.generate(MODEL, "question")
        assert TOKEN not in "".join(traceback.format_exception(caught.value))
        assert len(calls) == client.attempts == 1
    finally:
        await client.aclose()


def test_monitoring_accepts_only_registered_hosted_metadata():
    from src.tracing import EVENTS, safe_fields

    assert "hf_generation_attempt" in EVENTS
    assert safe_fields({"model": TOKEN, "provider": TOKEN, "content": TOKEN, "reasoning_content": TOKEN}) == {}
    assert safe_fields({"model": MODEL, "provider": "groq", "status_code": 402, "outcome": "failed"}) == {
        "model": MODEL, "provider": "groq", "status_code": 402, "outcome": "failed"}


def test_cerebras_metadata_keeps_registered_provider_label_without_arbitrary_content():
    from src.tracing import safe_fields

    assert safe_fields({"model": "openai/gpt-oss-120b:cerebras", "provider": "cerebras", "content": TOKEN}) == {
        "model": "openai/gpt-oss-120b:cerebras", "provider": "cerebras"}
    assert safe_fields({"provider": "unknown-provider", "model": "openai/gpt-oss-20b:cerebras"}) == {}


@pytest.mark.anyio
@pytest.mark.parametrize("status", [301, 307, 400, 401, 402, 403, 429, 500, 503])
async def test_http_failures_are_sanitized_and_never_retry_redirect_or_downgrade(stub_httpx, status):
    calls = stub_httpx(lambda request: httpx.Response(status, headers={"Location": "https://other.example"},
                                                     json={"error": TOKEN + PRIVATE_QUESTION}))
    client = HFClient(settings())
    try:
        with pytest.raises(HFGenerationError) as error:
            await client.generate(MODEL, PRIVATE_QUESTION, response_format=ScopeDecision.model_json_schema(), options=OPTIONS)
        trace = "".join(traceback.format_exception(error.value))
        assert TOKEN not in trace and PRIVATE_QUESTION not in trace
        assert error.value.status_code == status and len(calls) == client.attempts == 1
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("mutate", [
    lambda p: p.update(choices=[]),
    lambda p: p["choices"].append(p["choices"][0]),
    lambda p: p["choices"][0].update(index=True),
    lambda p: p["choices"][0].update(finish_reason="length"),
    lambda p: p["choices"][0].update(finish_reason="tool_calls"),
    lambda p: p["choices"][0]["message"].update(content=None, reasoning_content="hidden"),
    lambda p: p["choices"][0]["message"].update(content={"in_scope": True}),
    lambda p: p["choices"][0]["message"].update(content=" " * 10),
    lambda p: p["choices"][0]["message"].update(content="x" * 8193),
    lambda p: p["choices"][0]["message"].update(role="user"),
    lambda p: p["choices"][0]["message"].update(tool_calls=[{"function": "arbitrary"}]),
    lambda p: p["choices"][0]["message"].update(refusal="refused"),
    lambda p: p.update(usage={"prompt_tokens": True}),
    lambda p: p.update(usage={"completion_tokens": 257}),
    lambda p: p.update(usage={"prompt_tokens": 8192}),
    lambda p: p.update(usage={"completion_tokens": 2, "completion_tokens_details": {"reasoning_tokens": 3}}),
])
async def test_untrusted_envelopes_and_token_overruns_fail_closed(stub_httpx, mutate):
    payload = envelope()
    mutate(payload)
    calls = stub_httpx(lambda request: httpx.Response(200, json=payload))
    client = HFClient(settings())
    try:
        with pytest.raises(HFResponseError):
            await client.generate(MODEL, "question", options=OPTIONS)
        assert len(calls) == client.attempts == 1
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("body", [b"not json", b'{"choices":[],"choices":[]}', b"x" * 65537],
                         ids=["malformed", "duplicate", "oversize"])
async def test_malformed_duplicate_or_oversize_envelopes_are_rejected(stub_httpx, body):
    calls = stub_httpx(lambda request: httpx.Response(200, content=body))
    client = HFClient(settings())
    try:
        with pytest.raises(HFResponseError):
            await client.generate(MODEL, "question", options=OPTIONS)
        assert len(calls) == 1
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("model,prompt,options,fmt", [
    ("unregistered", "question", OPTIONS, None),
    (MODEL, "x" * 20001, OPTIONS, None),
    (MODEL, "é" * 4000, OPTIONS, None),
    (MODEL, "question", OPTIONS | {"num_predict": 1024}, None),
    (MODEL, "question", OPTIONS | {"temperature": 1}, None),
    (MODEL, "question", OPTIONS | {"num_ctx": 32768}, None),
    (MODEL, "question", OPTIONS | {"tools": []}, None),
    (MODEL, "question", OPTIONS, "json"),
])
async def test_invalid_requests_do_not_start_paid_attempts(stub_httpx, model, prompt, options, fmt):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope()))
    client = HFClient(settings())
    try:
        with pytest.raises((HFGenerationError, ValueError, UnsupportedModelError)):
            await client.generate(model, prompt, options=options, response_format=fmt)
        assert not calls and client.attempts == 0
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_missing_usage_stays_unknown_and_plain_retry_uses_pinned_profile(stub_httpx):
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope("E1")))
    client = HFClient(settings())
    try:
        result = await client.generate(MODEL, "question", options=OPTIONS)
        assert result.prompt_eval_count is None and result.eval_count is None and result.total_duration is None
        assert "response_format" not in json.loads(calls[0].content)
        assert result.model == MODEL and result.response == "E1"
    finally:
        await client.aclose()


class BlockedStream(httpx.AsyncByteStream):
    def __init__(self):
        self.started = asyncio.Event()
        self.closed = False

    async def __aiter__(self):
        self.started.set()
        await asyncio.Event().wait()
        yield b"unreachable"

    async def aclose(self):
        self.closed = True


@pytest.mark.anyio
async def test_disconnect_cancels_read_and_releases_single_request_capacity(stub_httpx):
    stream = BlockedStream()
    invocation = 0

    def respond(request):
        nonlocal invocation
        invocation += 1
        return httpx.Response(200, stream=stream) if invocation == 1 else httpx.Response(200, json=envelope())

    calls = stub_httpx(respond)
    client = HFClient(settings())
    task = asyncio.create_task(client.generate(MODEL, "question", options=OPTIONS))
    try:
        await asyncio.wait_for(stream.started.wait(), 1)
        with pytest.raises(HFGenerationError):
            await client.generate(MODEL, "second", options=OPTIONS)
        assert len(calls) == client.attempts == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stream.closed
        await client.generate(MODEL, "third", options=OPTIONS)
        assert len(calls) == client.attempts == 2
    finally:
        task.cancel()
        await client.aclose()


@pytest.mark.anyio
async def test_entire_attempt_deadline_bounds_a_stalled_body(stub_httpx):
    stream = BlockedStream()
    calls = stub_httpx(lambda request: httpx.Response(200, stream=stream))
    client = HFClient(settings(hf_timeout_seconds=1))
    try:
        with pytest.raises(HFTimeoutError):
            await asyncio.wait_for(client.generate(MODEL, "question", options=OPTIONS), 2)
        assert stream.closed and len(calls) == client.attempts == 1
    finally:
        await client.aclose()


def test_disabled_settings_cannot_construct_a_hosted_client():
    with pytest.raises(ValueError):
        HFClient(Settings(_env_file=None))
