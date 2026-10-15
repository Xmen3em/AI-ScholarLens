import base64
import hashlib
import json

import pytest
from src.services.hf import tokenizer
from src.services.hf.client import HFClient, HFGenerationError

from tests.unit.test_hf_client import settings


def install_vocabulary(tmp_path, monkeypatch):
    ranks = {bytes([i]): i for i in range(256)} | {b"hello": 256, b" hello": 257}
    data = b"".join(base64.b64encode(token) + b" " + str(rank).encode() + b"\n" for token, rank in ranks.items())
    path = tmp_path / "synthetic-vocabulary.tiktoken"
    path.write_bytes(data)
    monkeypatch.setattr(tokenizer, "VOCABULARY_PATH", path)
    monkeypatch.setattr(tokenizer, "VOCABULARY_SHA256", hashlib.sha256(data).hexdigest())
    return path


def test_local_verified_bpe_counts_text_without_network_and_preserves_unicode(tmp_path, monkeypatch):
    install_vocabulary(tmp_path, monkeypatch)
    assert tokenizer.count_input_tokens("hello hello") == 2
    assert tokenizer.count_input_tokens("مرحبا") > 0
    assert tokenizer.count_input_tokens("<|start|>user") > 1


def test_unreviewed_tokenizer_version_cannot_admit_a_request(tmp_path, monkeypatch):
    install_vocabulary(tmp_path, monkeypatch)
    monkeypatch.setattr(tokenizer, "version", lambda name: "changed")
    with pytest.raises(ValueError): tokenizer.count_input_tokens("hello")


@pytest.mark.parametrize("mutation", ["missing", "changed", "oversize"])
def test_tokenizer_never_downloads_or_repairs_missing_or_corrupt_data(tmp_path, monkeypatch, mutation):
    path = install_vocabulary(tmp_path, monkeypatch)
    tokenizer.count_input_tokens("hello")
    if mutation == "missing": path.unlink()
    elif mutation == "changed": path.write_bytes(path.read_bytes() + b" ")
    else: path.write_bytes(b"x" * (tokenizer.MAX_VOCABULARY_BYTES + 1))
    before = path.read_bytes() if path.exists() else None
    with pytest.raises((ValueError, OSError)): tokenizer.count_input_tokens("hello")
    assert (path.read_bytes() if path.exists() else None) == before


def test_explicit_context_admission_keeps_full_text_and_old_client_byte_gate(tmp_path, monkeypatch):
    install_vocabulary(tmp_path, monkeypatch)
    config = settings(hf_models=["openai/gpt-oss-120b:cerebras"], hf_default_model="openai/gpt-oss-120b:cerebras")
    prompt = "hello " * 2000
    original = object.__new__(HFClient); original.settings = config
    selected = object.__new__(type("Selected", (tokenizer.CerebrasInputAdmission, HFClient), {})); selected.settings = config
    with pytest.raises(HFGenerationError): original._payload(config.hf_models[0], prompt, None, None, None)
    payload = selected._payload(config.hf_models[0], prompt, None, None, None)
    assert payload["messages"][0]["content"] == prompt
    assert tokenizer.count_input_tokens(json.dumps(payload, ensure_ascii=False, allow_nan=False)) < 8192 - 512 - 512


def test_true_token_overflow_and_large_grammar_still_reject_locally(tmp_path, monkeypatch):
    from src.schemas.api.rag import GeneratedAnswer
    from src.services.rag.service import _selection_pattern

    install_vocabulary(tmp_path, monkeypatch)
    hf = object.__new__(type("Selected", (tokenizer.CerebrasInputAdmission, HFClient), {}))
    hf.settings = settings(hf_models=["openai/gpt-oss-120b:cerebras"], hf_default_model="openai/gpt-oss-120b:cerebras")
    with pytest.raises(HFGenerationError): hf._payload(hf.settings.hf_models[0], "x" * 9000, None, None, None)
    schema = GeneratedAnswer.model_json_schema()
    schema["properties"]["answer"] = {"type": "string", "pattern": _selection_pattern(30)}
    with pytest.raises(HFGenerationError): hf._payload(hf.settings.hf_models[0], "hello", None, schema, None)
