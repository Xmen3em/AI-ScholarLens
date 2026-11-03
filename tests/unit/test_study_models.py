import json
from dataclasses import replace

import httpx
import pytest
from pydantic import SecretStr
from src.services.hf.tokenizer import VOCABULARY_PATH, count_input_tokens
from src.services.study.models import DEFAULT_PROFILE, GPT_OSS_PROFILE, ModelProfile, call_cost_usd, estimate_input, load_profiles
from src.services.study.store import StudyStore
from src.services.study.tutor import MODEL, StudyModel, TutorError

# Captured from the code before profiles existed (commit 44612f8); the gpt-oss profile must keep sending exactly this.
EXPECTED_BODY = ('{"model":"openai/gpt-oss-120b:cerebras","messages":[{"role":"system","content":"علّم"},'
                 '{"role":"user","content":"q1"}],"temperature":0,"max_tokens":3000,"reasoning_effort":"low",'
                 '"stream":false,"response_format":{"type":"json_schema","json_schema":{"name":"study_output",'
                 '"strict":true,"schema":{"type":"object","properties":{"a":{"type":"string"}}}}}}')
QWEN = ModelProfile("qwen-27b", "Qwen/Qwen3.8-27B:deepinfra", "utf8_bytes_div_3", {"reasoning_effort": "low"},
                    0.20, 2.50, "2026-11-03")


async def sent_request(tmp_path, **options) -> bytes:
    store = StudyStore(tmp_path / "state.sqlite3", "owner")
    job = store.create_job("test", {}, max_calls=1)
    sent = []

    def respond(request):
        sent.append(request.content)
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = StudyModel(SecretStr("private-test"), store, client=client, memory=lambda: 2000,
                           counter=lambda _: 100, **options)
        with pytest.raises(TutorError):
            await model.complete(job["id"], "lesson", [{"role": "system", "content": "علّم"}, {"role": "user", "content": "q1"}],
                                 schema={"type": "object", "properties": {"a": {"type": "string"}}})
    return sent[0]


@pytest.mark.asyncio
async def test_gpt_oss_profile_request_is_byte_identical(tmp_path):
    assert (await sent_request(tmp_path, profile=GPT_OSS_PROFILE)).decode() == EXPECTED_BODY


@pytest.mark.asyncio
async def test_production_sends_the_benchmarked_glm_request(tmp_path):
    # The owner chose GLM-5.3 after the paper benchmark's development runs (3 Nov 2026).
    assert MODEL == DEFAULT_PROFILE.route == "zai-org/GLM-5.3:deepinfra"
    body = json.loads(await sent_request(tmp_path))
    assert body["model"] == "zai-org/GLM-5.3:deepinfra" and body["reasoning_effort"] == "low"
    assert body["response_format"]["json_schema"]["strict"] is True


@pytest.mark.asyncio
async def test_payload_key_order_keeps_options_before_stream(tmp_path):
    body = json.loads(await sent_request(tmp_path, profile=replace(DEFAULT_PROFILE, request_options={})))
    assert list(body) == ["model", "messages", "temperature", "max_tokens", "stream", "response_format"]


@pytest.mark.asyncio
async def test_profile_route_is_recorded_on_attempts(tmp_path):
    store = StudyStore(tmp_path / "state.sqlite3", "owner")
    job = store.create_job("test", {}, max_calls=1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        model = StudyModel(SecretStr("private-test"), store, client=client, memory=lambda: 2000, profile=QWEN)
        with pytest.raises(TutorError):
            await model.complete(job["id"], "lesson", [{"role": "user", "content": "q1"}], schema={"type": "object"})
    assert store.attempts(job["id"])[0]["model"] == "Qwen/Qwen3.8-27B:deepinfra"


def test_profiles_choose_their_input_estimate():
    unused = object()
    assert StudyModel(SecretStr("x"), unused, client=unused, profile=GPT_OSS_PROFILE).counter is count_input_tokens  # type: ignore[arg-type]
    # GLM-5.3, the production default, has no local tokenizer and uses the byte estimate.
    assert StudyModel(SecretStr("x"), unused, client=unused).counter("abcdef") == 2  # type: ignore[arg-type]
    assert StudyModel(SecretStr("x"), unused, client=unused, profile=QWEN).counter("abcdef") == 2  # type: ignore[arg-type]


@pytest.mark.skipif(not VOCABULARY_PATH.exists(), reason="local GPT-OSS vocabulary not present")
def test_byte_estimate_refuses_what_the_tokenizer_refuses():
    arabic = "النموذج بيسترجع المستندات ويولّد الإجابة. " * 600
    english = "The retriever returns the top documents for the generator. " * 1500
    for text in (arabic, english):
        assert estimate_input(QWEN, text) >= count_input_tokens(text)


def test_cost_without_usage_charges_the_maximum():
    assert call_cost_usd(QWEN, None, estimate=10_000) == pytest.approx(10_000 * 0.20 / 1e6 + 3000 * 2.50 / 1e6)
    assert call_cost_usd(QWEN, {"prompt_tokens": 1000, "completion_tokens": 100}, estimate=10_000) == pytest.approx(
        1000 * 0.20 / 1e6 + 100 * 2.50 / 1e6)


def test_profiles_load_from_a_frozen_file(tmp_path):
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"judge": "qwen-27b", "profiles": {"qwen-27b": {
        "route": QWEN.route, "input_estimate": QWEN.input_estimate, "request_options": QWEN.request_options,
        "price_in_usd_per_m": 0.20, "price_out_usd_per_m": 2.50, "priced_on": "2026-11-03"}}}), encoding="utf-8")
    assert load_profiles(path) == {"qwen-27b": QWEN}
    path.write_text(json.dumps({"judge": "x", "profiles": {"x": {"route": "a:b", "input_estimate": "guess",
        "request_options": {}, "price_in_usd_per_m": 1, "price_out_usd_per_m": 1, "priced_on": "2026-11-03"}}}),
        encoding="utf-8")
    with pytest.raises(ValueError):
        load_profiles(path)
