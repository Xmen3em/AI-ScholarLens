import copy
import json
from pathlib import Path

import httpx
import pytest
from src.commands.hf_qualification import load_revision
from src.commands.hf_reproduction import load_array_prompt, load_prompt_comparison, reproduce

from tests.unit.test_hf_client import envelope, settings


def test_semantic_pairs_keep_original_controls_and_do_not_copy_target_answers():
    profile = load_prompt_comparison()
    original = load_revision()["cases"][1]
    base = load_array_prompt()["arms"]["minimal-array-prompt-256"]["payload"]
    assert len(profile["arms"]) == profile["maximum_outbound_attempts"] == 6
    for arm in profile["arms"].values():
        case = arm["case"]
        instruction, data_text = case["prompt"].split("\nData:\n", 1)
        data = json.loads(data_text)
        expected = ["[1.1]"] if arm["polarity"] == "positive" else []
        assert case["expected"] == {"relevant_markers": expected}
        assert case["schema"] == original["schema"] and case["system"] == original["system"]
        assert "[1.1]" not in instruction and "target" not in data and "expected" not in data
        wire = copy.deepcopy(base)
        wire["messages"][-1]["content"] = case["prompt"]
        assert arm["payload"] == wire
        if expected:
            assert data == json.loads(original["prompt"].split("\nData:\n", 1)[1])
    for variant in ("concise", "json-shape", "per-passage"):
        pair = [arm for arm in profile["arms"].values() if arm["variant"] == variant]
        assert {arm["polarity"] for arm in pair} == {"positive", "negative"}
        assert pair[0]["case"]["prompt"].split("\nData:\n")[0] == pair[1]["case"]["prompt"].split("\nData:\n")[0]


def test_prompt_comparison_freeze_rejects_changed_inputs(tmp_path):
    for path in Path("evaluation/week7_hf/prompt-comparison-v1").iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / "requests.json").write_text("{}")
    with pytest.raises(ValueError):
        load_prompt_comparison(tmp_path)


@pytest.mark.anyio
@pytest.mark.parametrize("arm", ["concise-positive", "concise-negative", "json-shape-negative",
                                 "json-shape-positive", "per-passage-positive", "per-passage-negative"])
async def test_semantic_arm_sends_exact_frozen_request_without_retaining_output(stub_httpx, tmp_path, arm):
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quota.db")})
    case = load_prompt_comparison()["arms"][arm]["case"]
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope(json.dumps(case["expected"]))))
    result = await reproduce(config, arm, memory=lambda: 4096, experiment="prompt-comparison-v1")
    assert len(calls) == 1 and json.loads(calls[0].content) == load_prompt_comparison()["arms"][arm]["payload"]
    assert result["category"] == "passed" and result["qualification_accepted"] is False
    assert "response" not in result and "content" not in result


@pytest.mark.anyio
@pytest.mark.parametrize("polarity", ["positive", "negative"])
async def test_schema_valid_wrong_decision_does_not_pass_semantic_pair(stub_httpx, tmp_path, polarity):
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quota.db")})
    wrong = {"relevant_markers": [] if polarity == "positive" else ["[1.1]"]}
    stub_httpx(lambda request: httpx.Response(200, json=envelope(json.dumps(wrong))))
    result = await reproduce(config, "concise-" + polarity, memory=lambda: 4096, experiment="prompt-comparison-v1")
    assert result["category"] == "expected_mismatch" and result["expected_match"] is False


@pytest.mark.anyio
async def test_arbitrary_generated_markers_and_reasoning_are_never_retained(stub_httpx, tmp_path):
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quota.db")})
    body = envelope('{"relevant_markers":["private-generated-marker"]}')
    body["choices"][0]["message"]["reasoning_content"] = "private-generated-reasoning"
    stub_httpx(lambda request: httpx.Response(200, json=body))
    result = await reproduce(config, "concise-positive", memory=lambda: 4096, experiment="prompt-comparison-v1")
    assert result["category"] == "expected_mismatch"
    assert "private-generated-marker" not in json.dumps(result) and "private-generated-reasoning" not in json.dumps(result)
