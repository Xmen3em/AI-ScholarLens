import json

import httpx
import pytest
from pydantic import SecretStr
from src.services.study.content import EvidenceBlock
from src.services.study.service import StudyService
from src.services.study.store import StudyStore
from src.services.study.tutor import Lesson, render_lesson, review_lesson
from src.services.study.visuals import _map_nodes
from src.services.telegram_bot import OffsetStore, PrivateTelegramBot

from tests.unit.test_study_service import Content, Intake, Model, finished
from tests.unit.test_telegram_bot import KEY, settings


def example_lesson():
    return Lesson.model_validate({"title": "شرح الورقة", "sections": [
        {"heading": "الفكرة", "kind": "paper", "text": "الطريقة بتسترجع مصادر وبعدين بتولّد الإجابة.",
         "evidence": [{"block_id": "p1b0", "quote": "The model retrieves documents."},
                      {"block_id": "p1b0", "quote": "It then generates an answer."}]},
        {"heading": "تشبيه", "kind": "analogy", "text": "تخيّل مكتبة بتساعدك تختار مصدر لكل فقرة.", "evidence": []}]})


def test_display_collapses_block_references_without_dropping_original_quotes():
    lesson = example_lesson()
    blocks = [EvidenceBlock(id="p1b0", page=1, section="Method", text="The model retrieves documents. It then generates an answer.")]
    text = render_lesson(lesson, blocks, "https://arxiv.org/abs/2005.11401v4", title="RAG", coverage="full_text")
    assert text.count("p1b0 / ص 1") == 1
    assert len(lesson.sections[0].evidence) == 2


def test_sampling_is_not_reported_as_failed_pdf_extraction():
    text = render_lesson(Lesson(title="شرح", sections=example_lesson().sections[1:]), [],
                         "https://arxiv.org/abs/2005.11401v4", title="RAG", coverage="sampled_text")
    assert "مقاطع مختارة" in text
    assert "الاستخراج جزئي" not in text


def test_reading_map_includes_a_bounded_explanation_and_unique_references():
    lesson = example_lesson()
    nodes = _map_nodes(lesson)
    assert len(nodes) == 1
    assert nodes[0]["body"] == lesson.sections[0].text
    assert nodes[0]["refs"] == "p1b0"
    long = lesson.model_copy(deep=True)
    long.sections[0].text = "معلومة علمية بسيطة ومهمة. " * 40
    assert len(_map_nodes(long)[0]["body"]) <= 122


@pytest.mark.anyio
async def test_partial_extraction_and_sampling_are_both_reported(tmp_path):
    class PartialContent(Content):
        async def acquire(self, source):
            document = await super().acquire(source)
            blocks = [document.blocks[0].model_copy(update={"id": f"p1b{i}"}) for i in range(30)]
            return document.model_copy(update={"blocks": blocks, "coverage": "partial_text", "page_count": 2,
                                               "missing_pages": [2]})
    service = StudyService(StudyStore(tmp_path / "study.sqlite3", "owner"), Intake(), PartialContent(), Model())
    admitted = service.submit("paper", "/paper 1706.03762")
    job = await finished(service, admitted["job_id"])
    assert job["status"] == "ready"
    assert "الاستخراج جزئي" in job["result"]["text"]
    assert "مقاطع مختارة" in job["result"]["text"]
    await service.aclose()


@pytest.mark.anyio
async def test_reviewer_receives_table_context_and_can_reject_a_misleading_analogy():
    original = example_lesson()
    blocks = [EvidenceBlock(id="p1b0", page=1, section="Method",
                            text="The model retrieves documents. It then generates an answer. Different documents per TOKEN, not paragraph.")]

    class Reviewer:
        async def complete(self, job, purpose, messages, **kwargs):
            payload = json.loads(messages[-1]["content"])
            assert payload["source_context"][0]["text"] == blocks[0].text
            assert kwargs["schema"]["properties"]["unsupported_sections"]["items"]["enum"] == [0, 1]
            return {"output": {"unsupported_sections": [1], "issues": ["analogy_mismatch"]}}

    revised = await review_lesson(Reviewer(), "job", original, blocks=blocks)
    assert revised.sections[0] == original.sections[0]
    assert revised.sections[1].kind == "uncertainty"
    assert "فقرة" not in revised.sections[1].text


@pytest.mark.anyio
async def test_review_can_see_the_competing_table_row_beyond_the_chosen_quote():
    original = example_lesson()
    original.sections[1] = original.sections[0].model_copy(update={"heading": "النتائج", "kind": "paper",
        "text": "RAG-Token حقق أفضل نتيجة على TQA-Wiki: 66.1.",
        "evidence": [original.sections[0].evidence[0].model_copy(update={"block_id": "p6b0",
                     "quote": "RAG-Token 44.1 55.2/66.1 45.5 50.0"})]})
    table = "Table 1: TQA standard/TQA-Wiki. RAG-Token 44.1 55.2/66.1 45.5 50.0 RAG-Seq. 44.5 56.8/68.0 45.2 52.2"
    blocks = [EvidenceBlock(id="p6b0", page=6, section="Results", text=table)]

    class Reviewer:
        async def complete(self, job, purpose, messages, **kwargs):
            payload = json.loads(messages[-1]["content"])
            assert payload["source_context"][0]["text"] == table
            assert "68.0" not in payload["lesson"]["sections"][1]["evidence"][0]["quote"]
            return {"output": {"unsupported_sections": [1], "issues": ["overgeneralized_comparison"]}}

    result = await review_lesson(Reviewer(), "job", original, blocks=blocks)
    assert result.sections[1].kind == "uncertainty"
    assert "66.1" not in result.sections[1].text


@pytest.mark.anyio
async def test_telegram_parts_preserve_paragraphs_question_and_source(stub_httpx, tmp_path):
    calls = stub_httpx(lambda _: httpx.Response(200, json={"ok": True, "result": {"message_id": 1}}))
    paragraphs = ["شرح " + "😀" * 1400, "تشبيه " + "مثال بالمصري " * 120,
                  "سؤال للفهم: إيه دور المسترجع؟", "المصدر: https://arxiv.org/abs/2005.11401v4"]
    text = "\n\n".join(paragraphs)
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True) as bot:
        await bot._study_text(text)
    messages = [json.loads(request.content)["text"] for request in calls]
    assert len(messages) > 1
    assert messages[0].startswith("[1/")
    payloads = [message.split("\n", 1)[1] for message in messages]
    assert "".join(payloads) == text
    assert all(len(message.encode("utf-16-le")) // 2 <= 4096 for message in messages)
    assert any(paragraphs[1] in part for part in payloads)
    assert paragraphs[-1] in payloads[-1]


@pytest.mark.anyio
async def test_deep_url_is_explained_without_admitting_a_model_job(tmp_path):
    service = StudyService(StudyStore(tmp_path / "study.sqlite3", "owner"), Intake(), Content(), Model(),
                           research_python=tmp_path / "optional-python.exe")
    first = service.submit("paper", "/paper 1706.03762")
    assert (await finished(service, first["job_id"]))["status"] == "ready"
    reply = service.submit("url", "/deep https://arxiv.org/abs/2005.11401v4")
    assert "job_id" not in reply
    assert "/paper" in reply["reply"] and "/deep" in reply["reply"]
    assert not service.tasks
    await service.aclose()


def test_empty_deep_gives_a_question_example_without_work(tmp_path):
    service = StudyService(StudyStore(tmp_path / "study.sqlite3", "owner"), None, None, None)
    reply = service.submit("empty", "/deep")
    assert "/deep اشرح" in reply["reply"]
    assert "job_id" not in reply and not service.tasks


@pytest.mark.anyio
@pytest.mark.parametrize("question", ["what you can make now", "What can you do?", "تقدر تعمل إيه؟"])
async def test_capability_questions_return_local_help_without_admitting_a_job(tmp_path, question):
    service = StudyService(StudyStore(tmp_path / "study.sqlite3", "owner"), None, None, None)
    document = await Content().acquire((await Intake().resolve("1706.03762"))[0])
    service.store.save_paper(document.paper.arxiv_id, document.model_dump())
    service.store.activate(document.paper.arxiv_id, {"title": document.paper.title})
    result = service.submit("capabilities", question)
    assert "job_id" not in result
    assert "/paper" in result["reply"] and "/deep" in result["reply"]
    assert not service.tasks
    await service.aclose()


@pytest.mark.anyio
async def test_research_worker_reports_a_safe_validation_category(monkeypatch, capsys):
    import sys

    from src.commands import study_research
    from src.services.study.tutor import TutorError

    async def failed(_):
        raise TutorError("lesson_validation_failed", diagnostic="unsupported_quote")

    monkeypatch.setattr(study_research, "run_job", failed)
    monkeypatch.setattr(sys, "argv", ["study_research", "--job", "a" * 32])
    monkeypatch.setattr(study_research.logging, "disable", lambda _: None)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    # main owns its event loop, so call it outside this test's loop.
    import asyncio

    with pytest.raises(SystemExit):
        await asyncio.to_thread(study_research.main)
    assert json.loads(capsys.readouterr().out) == {"error": "lesson_validation_failed", "diagnostic": "unsupported_quote"}


@pytest.mark.anyio
@pytest.mark.parametrize("code", ["study_context_limit", "research_tool_execution_denied"])
async def test_worker_preserves_allowlisted_error_codes_without_raw_exception_text(monkeypatch, capsys, code):
    import asyncio
    import sys

    from src.commands import study_research
    from src.services.study.tutor import TutorError

    async def failed(_):
        if code.startswith("study_"):
            raise TutorError(code)
        raise ValueError(code)

    monkeypatch.setattr(study_research, "run_job", failed)
    monkeypatch.setattr(study_research.logging, "disable", lambda _: None)
    monkeypatch.setattr(sys, "argv", ["study_research", "--job", "a" * 32])
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    with pytest.raises(SystemExit):
        await asyncio.to_thread(study_research.main)
    assert json.loads(capsys.readouterr().out)["error"] == code


@pytest.mark.anyio
async def test_job_retains_a_context_failure_category_instead_of_null(tmp_path):
    from src.services.study.tutor import TutorError

    class LimitedModel(Model):
        async def complete(self, *args, **kwargs):
            raise TutorError("study_context_limit")

    service = StudyService(StudyStore(tmp_path / "study.sqlite3", "owner"), Intake(), Content(), LimitedModel())
    admitted = service.submit("context", "/paper 1706.03762")
    job = await finished(service, admitted["job_id"])
    assert job["result"]["failure_code"] == "study_context_limit"
    assert job["result"]["diagnostic"] == "study_context_limit"
    assert "سياق" in job["result"]["text"]
    await service.aclose()


def test_failure_metadata_never_copies_unknown_exception_text():
    from src.services.study.failures import failure_payload

    result = failure_payload(ValueError("private-provider-output-and-token-must-not-escape"))
    assert result == {"error": "research_unavailable_or_invalid", "diagnostic": "ValueError"}


@pytest.mark.anyio
async def test_worker_error_crosses_the_process_boundary_as_a_safe_category(monkeypatch, tmp_path):
    import asyncio

    from src.services.study.tutor import TutorError

    class Output:
        body = b'{"error":"unknown_evidence_block","diagnostic":"unknown_evidence_block"}'

        async def read(self, _):
            body, self.body = self.body, b""
            return body

    class Process:
        stdout, returncode = Output(), 2

        async def wait(self):
            return 2

    async def spawn(*args, **kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    service = StudyService(StudyStore(tmp_path / "study.sqlite3", "owner"), None, None, None,
                           research_python=tmp_path / "optional-python.exe")
    with pytest.raises(TutorError, match="unknown_evidence_block") as captured:
        await service._deep("a" * 32)
    assert captured.value.diagnostic == "unknown_evidence_block"
    await service.aclose()
