import hashlib
import json

import httpx
import pytest
from src.commands import prepare_glm_tokenizer
from src.services.study import glm_tokenizer
from src.services.study.models import DEFAULT_PROFILE, estimate_input
from tokenizers import Tokenizer, models, pre_tokenizers


def install_tokenizer(tmp_path, monkeypatch):
    # A tiny word-level tokenizer: every whitespace-separated word is one token.
    built = Tokenizer(models.WordLevel({"[UNK]": 0, "hello": 1}, unk_token="[UNK]"))
    built.pre_tokenizer = pre_tokenizers.Whitespace()
    path = tmp_path / "glm-tokenizer.json"
    path.write_text(built.to_str(), encoding="utf-8")
    monkeypatch.setattr(glm_tokenizer, "GLM_TOKENIZER_PATH", path)
    monkeypatch.setattr(glm_tokenizer, "GLM_TOKENIZER_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    glm_tokenizer.clear_cache()
    return path


def test_production_counts_with_glms_own_tokenizer(tmp_path, monkeypatch):
    install_tokenizer(tmp_path, monkeypatch)
    assert DEFAULT_PROFILE.input_estimate == "glm_tokenizer"
    assert estimate_input(DEFAULT_PROFILE, "hello hello مرحبا") == 3


@pytest.mark.parametrize("mutation", ["missing", "changed", "oversize", "version"])
def test_a_missing_or_unverified_tokenizer_falls_back_to_the_byte_estimate(tmp_path, monkeypatch, mutation):
    path = install_tokenizer(tmp_path, monkeypatch)
    if mutation == "missing":
        path.unlink()
    elif mutation == "changed":
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "oversize":
        monkeypatch.setattr(glm_tokenizer, "MAX_GLM_TOKENIZER_BYTES", 10)
    else:
        monkeypatch.setattr(glm_tokenizer, "version", lambda name: "changed")
    glm_tokenizer.clear_cache()
    # Six UTF-8 bytes, three per token: the byte estimate only ever over-counts.
    assert estimate_input(DEFAULT_PROFILE, "hello!") == 2


def test_prepare_downloads_once_and_checks_the_published_hash(tmp_path, monkeypatch):
    body = b'{"stand-in": "tokenizer"}'
    target = tmp_path / "data/pc-app/tokenizer/glm-tokenizer.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(glm_tokenizer, "GLM_TOKENIZER_PATH", target.relative_to(tmp_path))
    monkeypatch.setattr(glm_tokenizer, "GLM_TOKENIZER_SHA256", hashlib.sha256(body).hexdigest())
    monkeypatch.setattr(glm_tokenizer, "verify_glm_tokenizer", lambda: body)
    seen = []

    def serve(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(serve)
    assert prepare_glm_tokenizer.prepare()["status"] == "tokenizer_preparation_required" and not seen
    result = prepare_glm_tokenizer.prepare(download=True, transport=transport)
    assert result["status"] == "tokenizer_prepared" and seen == [glm_tokenizer.GLM_TOKENIZER_URL]
    assert target.read_bytes() == body
    assert prepare_glm_tokenizer.prepare(download=True, transport=transport)["status"] == "tokenizer_verified"
    assert len(seen) == 1


def test_prepare_refuses_a_download_with_the_wrong_hash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(glm_tokenizer, "GLM_TOKENIZER_PATH", tmp_path.joinpath("data/pc-app/tokenizer/glm.json")
                        .relative_to(tmp_path))
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"tampered"))
    with pytest.raises(ValueError, match="differs"):
        prepare_glm_tokenizer.prepare(download=True, transport=transport)
    assert not (tmp_path / "data/pc-app/tokenizer/glm.json").exists()


def test_the_pinned_source_is_one_commit_of_the_glm_repository():
    assert glm_tokenizer.GLM_TOKENIZER_URL == ("https://huggingface.co/zai-org/GLM-5.3/resolve/"
                                               "ba32f8c19c8738e2c57c71798c601d477a7bf844/tokenizer.json")
    assert glm_tokenizer.GLM_TOKENIZER_SHA256 == "19e773648cb4e65de8660ea6365e10acca112d42a854923df93db4a6f333a82d"


@pytest.mark.skipif(not glm_tokenizer.GLM_TOKENIZER_PATH.exists(), reason="local GLM tokenizer not prepared")
def test_the_real_tokenizer_counts_a_request_below_its_byte_estimate():
    glm_tokenizer.clear_cache()
    request = json.dumps({"messages": [{"role": "user", "content": "اشرح الطريقة خطوة بخطوة. Explain the retriever."}]},
                         ensure_ascii=False) * 200
    counted = glm_tokenizer.count_glm_tokens(request)
    assert counted is not None and 0 < counted < -(-len(request.encode()) // 3)
