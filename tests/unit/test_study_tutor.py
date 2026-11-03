import json

import httpx
import pytest
from pydantic import SecretStr
from src.services.study.content import EvidenceBlock
from src.services.study.store import StudyStore
from src.services.study.tutor import StudyModel, TutorError, accept_draft, check_claims, validate_draft, validate_lesson


def lesson():
    return {"title": "شرح الورقة", "sections": [
        {"heading": "الفكرة", "kind": "paper", "text": "", "evidence_ids": [], "claims": [
            {"text": "الطريقة بتستخدم attention عشان تفهم العلاقات بين الكلمات.", "evidence_id": "p1b1s0"}]},
        {"heading": "فكّر فيها", "kind": "question", "text": "إيه الفرق بين الطريقة دي والتكرار؟", "evidence_ids": [], "claims": []}]}


def test_paper_sections_require_real_exact_evidence_and_preserve_numbers():
    blocks = [EvidenceBlock(id="p1b1", page=1, section="Method", text="The model uses attention. Accuracy is 92.5 percent.")]
    assert validate_lesson(lesson(), blocks).title == "شرح الورقة"
    for support in ("p9b9s0", "invented"):
        bad = lesson()
        bad["sections"][0]["claims"][0]["evidence_id"] = support
        with pytest.raises(TutorError):
            validate_lesson(bad, blocks)
    bad = lesson()
    bad["sections"][0]["claims"][0]["text"] += " والنتيجة 99.9 بالمية."
    with pytest.raises(TutorError):
        validate_lesson(bad, blocks)


def test_paper_claim_cannot_drop_its_citation():
    bad = lesson()
    bad["sections"][0]["claims"][0]["evidence_id"] = ""
    with pytest.raises(TutorError):
        validate_lesson(bad, [])


def test_a_percentage_can_use_the_units_from_the_table_header():
    raw = lesson()
    raw["sections"][0]["claims"][0]["text"] = "النتيجة على مجموعة الاختبار كانت 92.5% في مقياس الدقة."
    blocks = [EvidenceBlock(id="p1b1", page=1, section="Results", text="Test accuracy (%) 92.5")]
    assert validate_lesson(raw, blocks).sections[0].evidence


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
async def test_the_claim_check_gets_room_for_copied_spans(tmp_path):
    store = StudyStore(tmp_path / "state.sqlite3", "owner")
    job = store.create_job("test", {}, max_calls=1)
    sent = []

    def respond(request):
        sent.append(json.loads(request.content))
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    model = StudyModel(SecretStr("private-test"), store, client=client, memory=lambda: 2000, counter=lambda _: 100)
    with pytest.raises((TutorError, RuntimeError)):
        await model.complete(job["id"], "grounding_review", [{"role": "user", "content": "test"}], schema={"type": "object"})
    # Verdicts now carry up to three 200-character spans each; 1,000 tokens truncated real lessons.
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
async def test_transport_failures_keep_a_safe_diagnostic(tmp_path):
    from src.services.study.failures import failure_payload

    cases = {"length": "incomplete_output", "usage": "invalid_usage", "json": "JSONDecodeError", "schema": "ValidationError"}
    for index, (change, diagnostic) in enumerate(cases.items()):
        store = StudyStore(tmp_path / f"diag-{index}.sqlite3", "owner")
        job = store.create_job("test", {})
        raw = {"choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "{}"}}],
               "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
        if change == "length":
            # A thinking model can spend its whole budget on reasoning and stop mid-answer.
            raw["choices"][0]["finish_reason"] = "length"
        elif change == "usage":
            raw.pop("usage")
        elif change == "json":
            raw["choices"][0]["message"]["content"] = "{not json"
        schema = {"type": "object", "required": ["a"]} if change == "schema" else {"type": "object"}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=raw))) as client:
            model = StudyModel(SecretStr("private-test"), store, client=client, memory=lambda: 2000, counter=lambda _: 100)
            with pytest.raises(TutorError) as caught:
                await model.complete(job["id"], "lesson", [{"role": "user", "content": "test"}], schema=schema)
        assert str(caught.value) == "study_response_invalid_or_unavailable"
        assert failure_payload(caught.value)["diagnostic"] == diagnostic, change


@pytest.mark.asyncio
async def test_low_ram_blocks_before_attempt_reservation(tmp_path):
    store = StudyStore(tmp_path / "state.sqlite3", "owner")
    job = store.create_job("test", {})
    model = StudyModel(SecretStr("private-test"), store, memory=lambda: 500, counter=lambda _: 100)
    with pytest.raises(TutorError):
        await model.complete(job["id"], "lesson", [{"role": "user", "content": "test"}], schema={"type": "object"})
    assert store.attempts(job["id"]) == []
    await model.aclose()


@pytest.mark.anyio
async def test_claim_check_removes_a_bad_comparison_without_rewriting_it():
    blocks = [EvidenceBlock(id="p1b1", page=1, section="Method", text="The model retrieves documents."),
              EvidenceBlock(id="p2b1", page=2, section="Results", text="Some metrics improve; other metrics decline.")]
    raw = {"title": "شرح", "sections": [
        {"heading": "الفكرة", "kind": "paper", "text": "", "evidence_ids": [], "claims": [
            {"text": "الطريقة بتسترجع مصادر وتستخدمها في التوليد.", "evidence_id": "p1b1s0"}]},
        {"heading": "المقارنة", "kind": "paper", "text": "", "evidence_ids": [], "claims": [
            {"text": "الطريقة أحسن من كل النماذج في كل المقاييس.", "evidence_id": "p2b1s0"}]}]}

    class Checker:
        async def complete(self, *args, **kwargs):
            return {"output": {"verdicts": [
                {"id": "c0", "supported": True, "support_spans": ["The model retrieves documents."], "issue": "none"},
                {"id": "c1", "supported": False, "support_spans": [], "issue": "overgeneralized_comparison"}]}}

    lesson, withheld = accept_draft(await check_claims(Checker(), "job", validate_draft(raw, blocks), blocks=blocks))
    assert [s.heading for s in lesson.sections] == ["الفكرة"] and withheld == {"المقارنة": 1}
    assert "كل النماذج" not in " ".join(s.text for s in lesson.sections)


def test_server_copies_the_original_quote_instead_of_asking_a_model_to_reproduce_it():
    blocks = [EvidenceBlock(id="p1b1", page=1, section="Method", text="The model uses attention. Original text, with punctuation!")]
    result = validate_lesson(lesson(), blocks)
    assert result.sections[0].evidence[0].quote == blocks[0].text
