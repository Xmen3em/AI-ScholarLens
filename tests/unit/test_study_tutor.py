import json

import httpx
import pytest
from pydantic import SecretStr
from src.services.study.content import EvidenceBlock
from src.services.study.store import StudyStore
from src.services.study.tutor import StudyModel, TutorError, validate_lesson


def lesson():
    return {"title": "شرح الورقة", "sections": [
        {"heading": "الفكرة", "kind": "paper", "text": "الطريقة بتستخدم attention عشان تفهم العلاقات بين الكلمات.",
         "evidence": [{"block_id": "p1b1", "quote": "The model uses attention."}]},
        {"heading": "فكّر فيها", "kind": "question", "text": "إيه الفرق بين الطريقة دي والتكرار؟", "evidence": []}]}


def test_paper_sections_require_real_exact_evidence_and_preserve_numbers():
    blocks = [EvidenceBlock(id="p1b1", page=1, section="Method", text="The model uses attention. Accuracy is 92.5 percent.")]
    assert validate_lesson(lesson(), blocks).title == "شرح الورقة"
    for support in ({"block_id": "p9b9", "quote": "The model uses attention."},
                    {"block_id": "p1b1", "quote": "Invented quotation."}):
        bad = lesson()
        bad["sections"][0]["evidence"] = [support]
        with pytest.raises(TutorError):
            validate_lesson(bad, blocks)
    bad = lesson()
    bad["sections"][0]["text"] += " والنتيجة 99.9 بالمية."
    with pytest.raises(TutorError):
        validate_lesson(bad, blocks)


def test_paper_claim_cannot_drop_its_citation():
    bad = lesson()
    bad["sections"][0]["evidence"] = []
    with pytest.raises(TutorError):
        validate_lesson(bad, [])


@pytest.mark.asyncio
async def test_new_transport_reserves_before_network_and_never_retries(tmp_path):
    store = StudyStore(tmp_path / "state.sqlite3", "owner")
    job = store.create_job("test", {}, max_calls=1)
    sent = []

    def respond(request):
        assert store.attempts(job["id"])[0]["state"] == "reserved"
        sent.append(json.loads(request.content))
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    model = StudyModel(SecretStr("private-test"), store, client=client, memory=lambda: 2000, counter=lambda _: 100)
    for _ in range(2):
        with pytest.raises((TutorError, RuntimeError)):
            await model.complete(job["id"], "lesson", [{"role": "user", "content": "test"}], schema={"type": "object"})
    assert len(sent) == 1
    assert store.attempts(job["id"])[0]["state"] == "failed"
    assert sent[0]["max_tokens"] == 3000
    await client.aclose()


@pytest.mark.asyncio
async def test_transport_rejects_truncation_missing_usage_and_tool_calls(tmp_path):
    for index, change in enumerate(("length", "usage", "tools")):
        store = StudyStore(tmp_path / f"state-{index}.sqlite3", "owner")
        job = store.create_job("test", {})
        raw = {"choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "{}"}}],
               "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
        if change == "length":
            raw["choices"][0]["finish_reason"] = "length"
        elif change == "usage":
            raw.pop("usage")
        else:
            raw["choices"][0]["message"]["tool_calls"] = [{"id": "x"}]
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=raw))) as client:
            model = StudyModel(SecretStr("private-test"), store, client=client, memory=lambda: 2000, counter=lambda _: 100)
            with pytest.raises(TutorError):
                await model.complete(job["id"], "lesson", [{"role": "user", "content": "test"}], schema={"type": "object"})


@pytest.mark.asyncio
async def test_low_ram_blocks_before_attempt_reservation(tmp_path):
    store = StudyStore(tmp_path / "state.sqlite3", "owner")
    job = store.create_job("test", {})
    model = StudyModel(SecretStr("private-test"), store, memory=lambda: 500, counter=lambda _: 100)
    with pytest.raises(TutorError):
        await model.complete(job["id"], "lesson", [{"role": "user", "content": "test"}], schema={"type": "object"})
    assert store.attempts(job["id"]) == []
    await model.aclose()
