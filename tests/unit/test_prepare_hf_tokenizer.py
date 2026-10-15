import hashlib

import httpx
import pytest
from src.commands.prepare_hf_tokenizer import prepare
from src.services.hf import tokenizer


def location(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "data/pc-app/tokenizer/o200k_base.tiktoken"
    monkeypatch.setattr(tokenizer, "VOCABULARY_PATH", path)
    return path


def test_default_is_offline_without_http_or_directory_creation(tmp_path, monkeypatch):
    location(tmp_path, monkeypatch)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: pytest.fail("Offline check created HTTP"))
    assert prepare() == {"status": "tokenizer_preparation_required", "outbound_http_requests": 0, "inference_attempts": 0}
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("failure", [None, "hash", "size", "redirect"])
def test_explicit_download_verifies_before_creating_any_file_and_never_overwrites(tmp_path, monkeypatch, failure):
    path = location(tmp_path, monkeypatch)
    data = b"synthetic-public-token-table"
    monkeypatch.setattr(tokenizer, "VOCABULARY_SHA256", hashlib.sha256(data).hexdigest())
    real = httpx.Client
    requests = []
    def respond(request):
        requests.append(request)
        if failure == "redirect": return httpx.Response(302, headers={"Location": "https://untrusted.invalid"})
        return httpx.Response(200, content=b"changed" if failure == "hash" else data)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real(transport=httpx.MockTransport(respond), **kwargs))
    if failure == "size": monkeypatch.setattr(tokenizer, "MAX_VOCABULARY_BYTES", 1)
    if failure:
        with pytest.raises((ValueError, httpx.HTTPStatusError)): prepare(download=True)
        assert not list(tmp_path.iterdir())
    else:
        assert prepare(download=True)["status"] == "tokenizer_prepared" and path.read_bytes() == data
        assert prepare(download=True)["outbound_http_requests"] == 0
    assert len(requests) == 1 and str(requests[0].url) == tokenizer.VOCABULARY_URL
    assert "Authorization" not in requests[0].headers
