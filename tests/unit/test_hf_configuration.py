import pytest
from pydantic import ValidationError
from src.config import Settings
from src.schemas.generation import GenerationResult

MODEL = "openai/gpt-oss-120b:groq"
TOKEN = "hf_" + "syntheticcredential" * 2
KEY = "isolated-api-key-" * 3


def config(**values):
    return Settings(_env_file=None, **values)


def test_hosted_defaults_preserve_local_generation_and_embeddings():
    settings = config()
    assert settings.hf_inference_enabled is False and settings.hf_token is None
    assert settings.hf_models == [MODEL] and settings.hf_default_model == MODEL
    assert settings.ollama_models == ["llama3.2:1b"]
    assert settings.ollama_default_model == "llama3.2:1b"
    assert settings.ollama_embedding_model == "nomic-embed-text"
    assert settings.agent_enabled is False


@pytest.mark.parametrize("values", [
    {}, {"hf_token": TOKEN}, {"api_key": KEY},
    {"hf_token": "hf_bad\nAuthorization: injected", "api_key": KEY},
    {"hf_token": TOKEN, "api_key": KEY, "answer_cache_enabled": True},
])
def test_hosted_activation_requires_credentials_key_and_uncached_profile(values):
    with pytest.raises(ValidationError) as error:
        config(hf_inference_enabled=True, **values)
    assert TOKEN not in str(error.value) and KEY not in str(error.value)


@pytest.mark.parametrize("models,default", [
    (["openai/gpt-oss-120b:cerebras"], "openai/gpt-oss-120b:cerebras"),
    (["openai/gpt-oss-120b:fastest"], "openai/gpt-oss-120b:fastest"),
    (["https://other.example/model"], "https://other.example/model"),
    ([MODEL, MODEL], MODEL), ([], MODEL), ([MODEL], "unregistered"),
    (["moonshotai/Kimi-K3:deepinfra"], "moonshotai/Kimi-K3:deepinfra"),
])
def test_hosted_registry_rejects_unreviewed_or_ambiguous_configuration(models, default):
    with pytest.raises(ValidationError):
        config(hf_models=models, hf_default_model=default)


def test_hosted_allowlist_and_token_are_independent_of_ollama(monkeypatch):
    monkeypatch.setenv("HF_MODELS", MODEL + ",openai/gpt-oss-120b:fireworks-ai")
    settings = config(hf_inference_enabled=True, hf_token=TOKEN, api_key=KEY)
    assert len(settings.hf_models) == 2
    assert settings.ollama_models == ["llama3.2:1b"]
    assert TOKEN not in repr(settings)


def test_provider_neutral_result_projects_only_real_usage_to_existing_callers():
    result = GenerationResult(model=MODEL, content='{"answer":"E1"}', elapsed_ms=12.5,
                              input_tokens=100, output_tokens=8, reasoning_tokens=3)
    legacy = result.as_legacy_response()
    assert legacy.response == result.content and legacy.model == MODEL and legacy.done
    assert legacy.prompt_eval_count == 100 and legacy.eval_count == 8
    assert legacy.total_duration is None and legacy.load_duration is None
    assert legacy.eval_duration is None and legacy.prompt_eval_duration is None
    assert GenerationResult(model=MODEL, content="NONE", elapsed_ms=1).output_tokens is None


@pytest.mark.parametrize("values", [{"input_tokens": -1}, {"output_tokens": True},
                                   {"elapsed_ms": -1}, {"content": ""}, {"reasoning_tokens": "1"}])
def test_generation_result_rejects_invalid_external_fields(values):
    with pytest.raises(ValidationError):
        GenerationResult(**({"model": MODEL, "content": "NONE", "elapsed_ms": 1.0} | values))
