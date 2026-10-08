import json

import httpx
import pytest
from pydantic import ValidationError
from src.exceptions import OllamaConnectionError, OllamaException, OllamaTimeoutError
from src.services.ollama import OllamaClient, normalize_model_name


def _refuse_connection(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _time_out(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("read timed out", request=request)


def _server_error(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500)


class TrackingStream(httpx.AsyncByteStream):
    def __init__(self):
        self.closed = False

    async def __aiter__(self):
        yield b'{"model":"llama3.2:1b","response":"partial","done":false}\n'

    async def aclose(self):
        self.closed = True


def test_normalize_model_name_adds_latest_only_when_tag_is_missing():
    assert normalize_model_name("llama3.2") == "llama3.2:latest"
    assert normalize_model_name("llama3.2:1b") == "llama3.2:1b"


@pytest.mark.anyio
async def test_readiness_requires_default_model_and_degrades_for_other_missing_models(stub_httpx, settings):
    requests = stub_httpx(lambda request: httpx.Response(200, json={"models": [{"name": "llama3.2:1b"}]}))
    client = OllamaClient(settings)

    result = await client.readiness()
    await client.aclose()

    assert result.status == "degraded"
    assert result.missing_required == []
    assert result.missing_optional == ["nomic-embed-text:latest"]
    assert requests[0].url.path == "/api/tags"


@pytest.mark.anyio
async def test_readiness_is_unhealthy_when_default_generation_model_is_missing(stub_httpx, settings):
    stub_httpx(lambda request: httpx.Response(200, json={"models": [{"model": "nomic-embed-text:latest"}]}))
    client = OllamaClient(settings)

    result = await client.readiness()
    await client.aclose()

    assert result.status == "unhealthy"
    assert result.missing_required == ["llama3.2:1b"]


@pytest.mark.parametrize(
    ("handler", "expected_error"),
    [
        pytest.param(_refuse_connection, OllamaConnectionError, id="connection-refused"),
        pytest.param(_time_out, OllamaTimeoutError, id="read-timeout"),
        pytest.param(_server_error, OllamaException, id="server-error-status"),
    ],
)
@pytest.mark.anyio
async def test_list_models_maps_transport_failures_to_domain_errors(stub_httpx, settings, handler, expected_error):
    stub_httpx(handler)
    client = OllamaClient(settings)

    with pytest.raises(expected_error) as excinfo:
        await client.list_models()
    await client.aclose()

    assert type(excinfo.value) is expected_error


@pytest.mark.anyio
async def test_generate_posts_structured_request_and_validates_response(stub_httpx, settings):
    requests = stub_httpx(
        lambda request: httpx.Response(
            200,
            json={"model": "llama3.2:1b", "response": '{"answer":"hello [1.1]"}', "done": True},
        )
    )
    client = OllamaClient(settings)

    result = await client.generate(
        "llama3.2:1b",
        "Question and evidence",
        system="Grounded assistant",
        response_format={"type": "object"},
        options={"temperature": 0, "num_predict": 512, "num_ctx": 8192},
    )
    await client.aclose()

    assert result.response == '{"answer":"hello [1.1]"}'
    assert json.loads(requests[0].content) == {
        "model": "llama3.2:1b",
        "prompt": "Question and evidence",
        "system": "Grounded assistant",
        "stream": False,
        "format": {"type": "object"},
        "options": {"temperature": 0, "num_predict": 512, "num_ctx": 8192},
    }


@pytest.mark.anyio
async def test_generate_rejects_malformed_ollama_payload(stub_httpx, settings):
    stub_httpx(lambda request: httpx.Response(200, json={"done": True}))
    client = OllamaClient(settings)

    with pytest.raises(OllamaException):
        await client.generate("llama3.2:1b", "prompt")
    await client.aclose()


@pytest.mark.anyio
async def test_generate_rejects_nonterminal_normal_response(stub_httpx, settings):
    stub_httpx(
        lambda request: httpx.Response(
            200,
            json={"model": "llama3.2:1b", "response": "partial", "done": False},
        )
    )
    client = OllamaClient(settings)

    with pytest.raises(OllamaException, match="terminal"):
        await client.generate("llama3.2:1b", "prompt")
    await client.aclose()


@pytest.mark.anyio
async def test_generate_maps_timeout_to_domain_error(stub_httpx, settings):
    stub_httpx(_time_out)
    client = OllamaClient(settings)

    with pytest.raises(OllamaTimeoutError):
        await client.generate("llama3.2:1b", "prompt")
    await client.aclose()


@pytest.mark.anyio
async def test_generate_stream_parses_valid_ndjson_and_requires_terminal_chunk(stub_httpx, settings):
    body = b'\n'.join(
        [
            b'{"model":"llama3.2:1b","response":"hello ","done":false}',
            b'{"model":"llama3.2:1b","response":"[1.1]","done":true,"eval_count":4}',
        ]
    )
    requests = stub_httpx(lambda request: httpx.Response(200, content=body))
    client = OllamaClient(settings)

    chunks = [chunk async for chunk in client.generate_stream("llama3.2:1b", "prompt", response_format={"type": "object"})]
    await client.aclose()

    assert [chunk.response for chunk in chunks] == ["hello ", "[1.1]"]
    assert chunks[-1].done is True
    assert json.loads(requests[0].content)["stream"] is True
    assert json.loads(requests[0].content)["format"] == {"type": "object"}


@pytest.mark.anyio
async def test_generate_stream_rejects_malformed_ndjson(stub_httpx, settings):
    stub_httpx(lambda request: httpx.Response(200, content=b'{"response":"ok","done":false}\nnot-json'))
    client = OllamaClient(settings)

    with pytest.raises(OllamaException):
        _ = [chunk async for chunk in client.generate_stream("llama3.2:1b", "prompt")]
    await client.aclose()


@pytest.mark.anyio
async def test_generate_stream_rejects_missing_terminal_chunk(stub_httpx, settings):
    stub_httpx(
        lambda request: httpx.Response(
            200,
            content=b'{"model":"llama3.2:1b","response":"partial","done":false}\n',
        )
    )
    client = OllamaClient(settings)

    with pytest.raises(OllamaException, match="terminal"):
        _ = [chunk async for chunk in client.generate_stream("llama3.2:1b", "prompt")]
    await client.aclose()


@pytest.mark.anyio
async def test_closing_stream_early_releases_response(stub_httpx, settings):
    stream = TrackingStream()
    stub_httpx(lambda request: httpx.Response(200, stream=stream))
    client = OllamaClient(settings)
    generation = client.generate_stream("llama3.2:1b", "prompt")

    await anext(generation)
    await generation.aclose()
    await client.aclose()

    assert stream.closed is True


@pytest.mark.anyio
async def test_generate_uses_configured_timeout(stub_httpx, settings):
    stub_httpx(
        lambda request: httpx.Response(
            200,
            json={"model": "llama3.2:1b", "response": "ok", "done": True},
        )
    )
    client = OllamaClient(settings)

    assert client.generation_timeout.read == settings.ollama_timeout
    assert client.control_timeout.read < client.generation_timeout.read
    await client.aclose()


def test_generate_response_schema_rejects_wrong_types():
    from src.schemas.ollama import OllamaGenerateResponse

    with pytest.raises(ValidationError):
        OllamaGenerateResponse.model_validate({"response": [], "done": "yes"})
