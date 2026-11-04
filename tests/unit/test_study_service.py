import asyncio
import json

import pytest
from src.services.study.content import EvidenceBlock, PaperContent
from src.services.study.intake import StudyPaper
from src.services.study.service import StudyService
from src.services.study.store import StudyStore

from tests.unit.test_study_tutor import lesson


def paper(identity="1706.03762v1"):
    return StudyPaper(arxiv_id=identity, title="Attention Is All You Need", authors=["Author"],
                      abstract="The model uses attention.", categories=["cs.CL"], published="2017-06-12T00:00:00Z")


class Intake:
    async def resolve(self, text):
        return [paper()] if text.startswith("1706") else [paper(), paper("1706.03762v2")]


class Content:
    async def acquire(self, source):
        return PaperContent(paper=source, source_sha256="a" * 64, parser_revision="test", page_count=1,
                            blocks=[EvidenceBlock(id="p1b1", page=1, section="Method", text="The model uses attention.")],
                            missing_pages=[], coverage="full_text")


class Model:
    def __init__(self):
        self.calls = []

    async def complete(self, job, purpose, messages, **kwargs):
        self.calls.append(messages)
        if purpose == "grounding_review":
            return {"output": honest_verdicts(messages)}
        return {"output": lesson()}


def honest_spans(quote):
    # Exact pieces of the quote, each at most 200 characters, cut at spaces.
    spans, words = [], quote.split()
    while words and len(spans) < 3:
        piece = ""
        while words and len(piece) + len(words[0]) + 1 <= 200:
            piece = (piece + " " + words.pop(0)).strip()
        spans.append(piece or words.pop(0)[:200])
    return spans


def honest_verdicts(messages):
    items = json.loads(messages[-1]["content"])["items"]
    return {"verdicts": [{"id": item["id"], "supported": True, "issue": "none",
                          "support_spans": honest_spans(item["quote"]) if "quote" in item else []} for item in items]}


async def finished(service, identity):
    for _ in range(100):
        job = service.store.get_job(identity)
        if job["status"] != "running":
            return job
        await asyncio.sleep(0.01)
    pytest.fail("study did not finish")


@pytest.mark.asyncio
async def test_intake_lesson_followup_and_forget_are_end_to_end(tmp_path):
    store = StudyStore(tmp_path / "study.sqlite3", "owner")
    model = Model()
    service = StudyService(store, Intake(), Content(), model)
    first = service.submit("tg:1", "/paper 1706.03762")
    job = await finished(service, first["job_id"])
    assert job["status"] == "ready"
    assert "ص 1" in job["result"]["text"]
    assert store.context()["paper_id"] == "1706.03762v1"
    again = service.submit("tg:1", "/paper 1706.03762")
    assert again["job_id"] == first["job_id"]
    assert len(model.calls) == 2
    followup = service.submit("tg:2", "اشرح الطريقة بمثال")
    assert (await finished(service, followup["job_id"]))["status"] == "ready"
    assert len(store.context()["turns"]) == 1
    assert service.submit("tg:3", "/forget")["reply"]
    assert store.context() is None
    await service.aclose()


@pytest.mark.asyncio
async def test_title_candidates_never_auto_activate_a_paper(tmp_path):
    service = StudyService(StudyStore(tmp_path / "state.sqlite3", "owner"), Intake(), Content(), Model())
    response = service.submit("tg:1", "/paper Attention Is All You Need")
    job = await finished(service, response["job_id"])
    assert "/choose 1" in job["result"]["text"]
    assert service.store.context() is None
    selected = service.submit("tg:2", "/choose 2")
    assert (await finished(service, selected["job_id"]))["status"] == "ready"
    assert service.store.context()["paper_id"] == "1706.03762v2"
    await service.aclose()


@pytest.mark.asyncio
async def test_failed_validation_cannot_activate_or_leak_an_unverified_lesson(tmp_path):
    class BadModel(Model):
        async def complete(self, *args, **kwargs):
            bad = lesson()
            bad["sections"][0]["evidence_ids"] = ["Fabricated source quotation"]
            return {"output": bad}

    service = StudyService(StudyStore(tmp_path / "state.sqlite3", "owner"), Intake(), Content(), BadModel())
    result = service.submit("tg:1", "/paper 1706.03762")
    job = await finished(service, result["job_id"])
    assert job["status"] == "failed"
    assert "Fabricated" not in job["result"]["text"]
    assert service.store.context() is None
    await service.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("question", ["Which dataset is used in this research paper?", "/ask RAG", "Who developed this model?"])
async def test_explicit_questions_keep_the_existing_assistant_when_no_paper_is_selected(tmp_path, question):
    service = StudyService(StudyStore(tmp_path / "state.sqlite3", "owner"), None, None, None)
    assert service.submit("question", question) == {"fallback": True}
    assert not service.tasks


@pytest.mark.asyncio
async def test_observer_sees_the_accepted_lesson_and_the_writer_catalog(tmp_path):
    store = StudyStore(tmp_path / "state.sqlite3", "owner")
    seen = []
    service = StudyService(store, Intake(), Content(), Model(), observer=lambda *args: seen.append(args))
    job = await finished(service, service.submit("tg:1", "/paper 1706.03762")["job_id"])
    assert job["status"] == "ready"
    job_id, accepted, catalog = seen[0]
    assert job_id == job["id"] and accepted.sections[0].kind == "paper"
    assert catalog[0]["id"] == "p1b1s0" and catalog[0]["quote"] == "The model uses attention."
    # The benchmark sees the lesson; the stored result and the local API stay as they were.
    assert "lesson" not in job["result"]
    await service.aclose()


@pytest.mark.asyncio
async def test_a_running_job_reports_each_stage_and_forgets_it_when_finished(tmp_path):
    seen = []

    class Reading(Content):
        async def acquire(self, source):
            seen.append(("acquire", service.progress.get(job_id)))
            return await super().acquire(source)

    class Watching(Model):
        async def complete(self, job, purpose, messages, **kwargs):
            seen.append((purpose, service.progress.get(job)))
            return await super().complete(job, purpose, messages, **kwargs)

    service = StudyService(StudyStore(tmp_path / "state.sqlite3", "owner"), Intake(), Reading(), Watching())
    job_id = service.submit("tg:1", "/paper 1706.03762")["job_id"]
    assert service.progress[job_id] == "started"
    assert (await finished(service, job_id))["status"] == "ready"
    followup = service.submit("tg:2", "اشرح الطريقة بمثال")["job_id"]
    assert (await finished(service, followup))["status"] == "ready"
    await asyncio.sleep(0)
    assert seen == [("acquire", "reading"), ("lesson", "writing_lesson"), ("grounding_review", "checking"),
                    ("followup", "writing_answer"), ("grounding_review", "checking")]
    assert service.progress == {}
    await service.aclose()


@pytest.mark.asyncio
async def test_request_kind_tells_papers_from_questions(tmp_path):
    store = StudyStore(tmp_path / "study.sqlite3", "owner")
    service = StudyService(store, Intake(), Content(), Model())
    assert service.request_kind("1706.03762") == "paper"
    assert service.request_kind("/paper 1706.03762") == "paper"
    assert service.request_kind("/paper attention is all you need") == "other"
    assert service.request_kind("attention is all you need") == "other"
    assert service.request_kind("/help") == "other" and service.request_kind("/usage") == "other"
    await finished(service, service.submit("tg:1", "1706.03762")["job_id"])
    assert service.request_kind("اشرح الطريقة بمثال") == "question"
    assert service.request_kind("/quiz") == "question" and service.request_kind("/ask what is attention") == "question"
    assert service.request_kind("1706.03762v2") == "paper"
    assert service.request_kind("/notes") == "other"


@pytest.mark.asyncio
async def test_ready_results_say_whether_they_were_a_paper_or_a_question(tmp_path):
    store = StudyStore(tmp_path / "study.sqlite3", "owner")
    service = StudyService(store, Intake(), Content(), Model())
    lesson_job = await finished(service, service.submit("tg:1", "1706.03762")["job_id"])
    answer_job = await finished(service, service.submit("tg:2", "اشرح الطريقة بمثال")["job_id"])
    assert lesson_job["result"]["kind"] == "paper" and answer_job["result"]["kind"] == "question"
