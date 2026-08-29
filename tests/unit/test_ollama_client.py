import json

import httpx
import pytest
from src.exceptions import OllamaConnectionError, OllamaException, OllamaTimeoutError
from src.services.ollama import OllamaClient


def _refuse_connection(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _time_out(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("read timed out", request=request)


def _server_error(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500)


@pytest.mark.anyio
async def test_health_check_reports_version_from_ollama(stub_httpx, settings):
    requests = stub_httpx(lambda request: httpx.Response(200, json={"version": "0.11.2"}))

    result = await OllamaClient(settings).health_check()

    assert result == {
        "status": "healthy",
        "message": "Ollama service is running",
        "version": "0.11.2",
    }
    assert requests[0].url.path == "/api/version"


@pytest.mark.anyio
async def test_health_check_reports_unknown_version_when_ollama_omits_it(stub_httpx, settings):
    stub_httpx(lambda request: httpx.Response(200, json={}))

    result = await OllamaClient(settings).health_check()

    assert result["version"] == "unknown"


@pytest.mark.parametrize(
    ("handler", "expected_error"),
    [
        pytest.param(_refuse_connection, OllamaConnectionError, id="connection-refused"),
        pytest.param(_time_out, OllamaTimeoutError, id="read-timeout"),
        pytest.param(_server_error, OllamaException, id="server-error-status"),
    ],
)
@pytest.mark.anyio
async def test_health_check_maps_transport_failures_to_domain_errors(stub_httpx, settings, handler, expected_error):
    stub_httpx(handler)

    with pytest.raises(expected_error) as excinfo:
        await OllamaClient(settings).health_check()

    # Exact type matters: the connection and timeout errors both subclass OllamaException.
    assert type(excinfo.value) is expected_error


@pytest.mark.anyio
async def test_generate_posts_prompt_and_returns_ollama_payload(stub_httpx, settings):
    requests = stub_httpx(lambda request: httpx.Response(200, json={"response": "hello"}))

    result = await OllamaClient(settings).generate("llama3.2:1b", "Say hello")

    assert result == {"response": "hello"}
    assert requests[0].url.path == "/api/generate"
    assert json.loads(requests[0].content) == {
        "model": "llama3.2:1b",
        "prompt": "Say hello",
        "stream": False,
    }


@pytest.mark.anyio
async def test_generate_maps_server_error_to_ollama_exception(stub_httpx, settings):
    stub_httpx(_server_error)

    with pytest.raises(OllamaException) as excinfo:
        await OllamaClient(settings).generate("llama3.2:1b", "Say hello")

    assert type(excinfo.value) is OllamaException
