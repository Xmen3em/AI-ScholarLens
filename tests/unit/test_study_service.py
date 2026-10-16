import asyncio

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
        return {"output": lesson()}


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
    assert len(model.calls) == 1
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
            bad["sections"][0]["evidence"][0]["quote"] = "Fabricated source quotation"
            return {"output": bad}

    service = StudyService(StudyStore(tmp_path / "state.sqlite3", "owner"), Intake(), Content(), BadModel())
    result = service.submit("tg:1", "/paper 1706.03762")
    job = await finished(service, result["job_id"])
    assert job["status"] == "failed"
    assert "Fabricated" not in job["result"]["text"]
    assert service.store.context() is None
    await service.aclose()
