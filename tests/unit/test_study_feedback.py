import json

import httpx
import pytest
from pydantic import SecretStr
from src.services.study.content import EvidenceBlock, PaperContent
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
    assert text.count("↩︎ المصدر: ص 1") == 1
    assert "p1b0" not in text  # students see pages, not internal block IDs
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


class _Worker:
    """A stand-in research process: fixed stdout, exit code and kill tracking."""

    def __init__(self, body=b"", returncode=0, *, hang=False):
        self.returncode = None
        self._exit, self._hang, self.killed = returncode, hang, False
        worker = self

        class Output:
            pending = body

            async def read(self, _):
                if worker._hang:
                    import asyncio

                    await asyncio.sleep(30)
                chunk, self.pending = self.pending, b""
                return chunk

        self.stdout = Output()

    async def wait(self):
        if self.returncode is None:
            self.returncode = self._exit
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


async def _deep_failure(monkeypatch, tmp_path, process=None, *, spawn_error=None):
    import asyncio

    from src.services.study.tutor import TutorError

    async def spawn(*args, **kwargs):
        if spawn_error:
            raise spawn_error
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    service = StudyService(StudyStore(tmp_path / "study.sqlite3", "owner"), None, None, None,
                           research_python=tmp_path / "optional-python.exe")
    try:
        with pytest.raises(TutorError) as captured:
            await service._deep("a" * 32)
    finally:
        await service.aclose()
    return captured.value


@pytest.mark.anyio
@pytest.mark.parametrize(("body", "exit_code", "expected"), [
    # Worker crashed before printing (e.g. optional SDK import failure).
    (b"", 2, {"error": "research_worker_failed", "diagnostic": "research_worker_failed", "stage": "worker_exit"}),
    (b"Traceback: private provider text", 1,
     {"error": "research_worker_failed", "diagnostic": "research_worker_failed", "stage": "worker_exit"}),
    (b"not json", 0, {"error": "research_output_invalid", "diagnostic": "JSONDecodeError", "stage": "worker_output"}),
    (b"[]", 0, {"error": "research_output_invalid", "diagnostic": "shape", "stage": "worker_output"}),
    # A worker category keeps its own stage; an unlisted error is not trusted.
    (b'{"error":"study_context_limit","diagnostic":"study_context_limit","stage":"agent"}', 2,
     {"error": "study_context_limit", "diagnostic": "study_context_limit", "stage": "agent"}),
    (b'{"error":"research_unavailable_or_invalid","diagnostic":"JSONDecodeError","stage":"agent"}', 2,
     {"error": "research_unavailable_or_invalid", "diagnostic": "JSONDecodeError", "stage": "agent"}),
    (b'{"error":"raw provider message","stage":"agent"}', 2,
     {"error": "research_worker_failed", "diagnostic": "research_worker_failed", "stage": "worker_exit"}),
])
async def test_deep_process_boundary_reports_a_finite_stage(monkeypatch, tmp_path, body, exit_code, expected):
    from src.services.study.failures import failure_payload

    error = await _deep_failure(monkeypatch, tmp_path, _Worker(body, exit_code))
    assert failure_payload(error, default="study_generation_unavailable") == expected


@pytest.mark.anyio
async def test_unknown_worker_stage_stays_unknown_instead_of_guessed(monkeypatch, tmp_path):
    from src.services.study.failures import failure_payload

    body = b'{"error":"study_context_limit","diagnostic":"made-up","stage":"private-phase"}'
    error = await _deep_failure(monkeypatch, tmp_path, _Worker(body, 2))
    assert failure_payload(error, default="study_generation_unavailable") == {"error": "study_context_limit",
                                                                             "diagnostic": "study_context_limit"}


@pytest.mark.anyio
async def test_deep_worker_timeout_is_named_and_the_process_is_killed(monkeypatch, tmp_path):
    from src.services.study import service as service_module
    from src.services.study.failures import failure_payload

    monkeypatch.setattr(service_module, "DEEP_WORKER_TIMEOUT_SECONDS", 0.05)
    process = _Worker(hang=True)
    error = await _deep_failure(monkeypatch, tmp_path, process)
    assert failure_payload(error) == {"error": "research_worker_timeout", "diagnostic": "TimeoutError", "stage": "worker_timeout"}
    assert process.killed


@pytest.mark.anyio
async def test_missing_research_interpreter_is_a_start_failure(monkeypatch, tmp_path):
    from src.services.study.failures import failure_payload

    error = await _deep_failure(monkeypatch, tmp_path, spawn_error=FileNotFoundError("C:/private/path/python.exe"))
    assert failure_payload(error) == {"error": "research_worker_unavailable", "diagnostic": "OSError", "stage": "worker_start"}


@pytest.mark.anyio
async def test_deep_output_limit_is_a_worker_output_failure(monkeypatch, tmp_path):
    from src.services.study.failures import failure_payload

    process = _Worker(b"x" * 70000)
    error = await _deep_failure(monkeypatch, tmp_path, process)
    assert failure_payload(error)["error"] == "research_output_limit"
    assert failure_payload(error)["stage"] == "worker_output"
    assert process.killed


@pytest.mark.anyio
async def test_failed_job_keeps_the_stage_and_shows_safe_labels_to_the_owner(tmp_path):
    from src.services.study.failures import staged
    from src.services.study.tutor import TutorError

    class StagedModel(Model):
        async def complete(self, *args, **kwargs):
            raise staged(TutorError("study_context_limit"), "agent")

    service = StudyService(StudyStore(tmp_path / "study.sqlite3", "owner"), Intake(), Content(), StagedModel())
    admitted = service.submit("context", "/paper 1706.03762")
    job = await finished(service, admitted["job_id"])
    assert job["status"] == "failed"
    assert (job["result"]["failure_code"], job["result"]["diagnostic"], job["result"]["stage"]) == (
        "study_context_limit", "study_context_limit", "agent")
    assert "stage=agent code=study_context_limit diagnostic=study_context_limit" in job["result"]["text"]
    await service.aclose()


def test_the_first_stage_wins_and_stages_are_never_free_text():
    from src.services.study.failures import failure_payload, staged

    error = staged(staged(ValueError("secret"), "agent"), "validation")
    assert failure_payload(error) == {"error": "research_unavailable_or_invalid", "diagnostic": "ValueError", "stage": "agent"}
    free = ValueError("x")
    free.stage = "C:/Users/private"
    assert "stage" not in failure_payload(free)


@pytest.mark.anyio
async def test_research_worker_prints_its_stage(monkeypatch, capsys):
    import asyncio
    import sys

    from src.commands import study_research
    from src.services.study.failures import staged
    from src.services.study.tutor import TutorError

    async def failed(_):
        raise staged(TutorError("research_final_json_invalid"), "final_json")

    monkeypatch.setattr(study_research, "run_job", failed)
    monkeypatch.setattr(study_research.logging, "disable", lambda _: None)
    monkeypatch.setattr(sys, "argv", ["study_research", "--job", "a" * 32])
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    with pytest.raises(SystemExit):
        await asyncio.to_thread(study_research.main)
    assert json.loads(capsys.readouterr().out) == {"error": "research_final_json_invalid",
                                                   "diagnostic": "research_final_json_invalid", "stage": "final_json"}


def test_arabic_lines_that_open_with_english_stay_right_to_left():
    from src.services.study.tutor import RLM, render_lesson

    lesson = Lesson.model_validate({"title": "RAG-Token وRAG-Sequence", "sections": [
        {"heading": "Sequence وToken", "kind": "paper", "text": "RAG-Token بيختار وثيقة لكل token.\n" + "في RAG-Sequence الوثيقة ثابتة.",
         "evidence": [{"block_id": "p3b0", "quote": "each target token"}]}]})
    blocks = [EvidenceBlock(id="p3b0", page=3, section="Models", text="each target token")]
    text = render_lesson(lesson, blocks, "https://arxiv.org/abs/2005.11401v4", title="RAG", coverage="full_text", followup=True)
    lines = text.split("\n")
    assert RLM + "💬 RAG-Token وRAG-Sequence" in lines
    assert RLM + "Sequence وToken — 📄 من الورقة" in lines
    assert RLM + "RAG-Token بيختار وثيقة لكل token." in lines
    # Arabic-first lines, the URL line and pure English text get no mark.
    assert "في RAG-Sequence الوثيقة ثابتة." in lines
    assert "🔗 المصدر والنسخة: https://arxiv.org/abs/2005.11401v4" in lines
    assert text.count(RLM) == 3 and "📖" not in text


def test_review_rejections_become_one_closing_note():
    from src.services.study.tutor import WITHHELD, render_lesson

    lesson = Lesson.model_validate({"title": "شرح", "sections": [
        {"heading": "الفكرة", "kind": "paper", "text": "الطريقة بتسترجع مصادر.", "evidence": [{"block_id": "p1b0", "quote": "The model retrieves documents."}]},
        {"heading": "الطريقة", "kind": "uncertainty", "text": WITHHELD, "evidence": []},
        {"heading": "تشبيه", "kind": "uncertainty", "text": WITHHELD, "evidence": []}]})
    blocks = [EvidenceBlock(id="p1b0", page=1, section="Method", text="The model retrieves documents.")]
    text = render_lesson(lesson, blocks, "https://arxiv.org/abs/2005.11401v4", title="RAG", coverage="full_text")
    assert WITHHELD not in text and "حدود المتاح" not in text
    assert "⚠️ شلت 2 جزء ماقدرتش أتأكد منه من نص الورقة: «الطريقة»، «تشبيه»." in text


@pytest.mark.anyio
async def test_review_report_carries_only_counts_and_issue_labels():
    original = example_lesson()

    class Reviewer:
        async def complete(self, job, purpose, messages, **kwargs):
            return {"output": {"unsupported_sections": [1], "issues": ["analogy_mismatch", "analogy_mismatch"]}}

    report = {}
    await review_lesson(Reviewer(), "job", original, blocks=[], report=report)
    assert report == {"reviewed": 2, "rejected": 1, "rejected_sections": [1], "issues": ["analogy_mismatch"]}


@pytest.mark.anyio
async def test_deep_answer_rejected_by_review_names_the_review_stage(tmp_path, monkeypatch):
    blocks_text = Content  # the shared stub source used by the service tests

    class RejectingModel(Model):
        reject = False

        async def complete(self, job, purpose, messages, **kwargs):
            if purpose == "grounding_review" and self.reject:
                return {"output": {"unsupported_sections": [0], "issues": ["missing_support"]}}
            return await super().complete(job, purpose, messages, **kwargs)

    model = RejectingModel()
    service = StudyService(StudyStore(tmp_path / "study.sqlite3", "owner"), Intake(), blocks_text(), model,
                           research_python=tmp_path / "python.exe")
    first = service.submit("paper", "/paper 1706.03762")
    assert (await finished(service, first["job_id"]))["status"] == "ready"
    document = service.store.paper(service.store.context()["paper_id"])["content"]
    snippet = document["blocks"][0]["id"] + "s0"

    async def deep(job_id):
        return {"output": {"title": "شرح أعمق", "sections": [{"heading": "الطريقة", "kind": "paper",
                "text": "النموذج بيستخدم الانتباه في كل طبقة عشان يفهم العلاقات.", "evidence_ids": [snippet]}]}}

    monkeypatch.setattr(service, "_deep", deep)
    model.reject = True
    admitted = service.submit("deep", "/deep اشرح الطريقة")
    job = await finished(service, admitted["job_id"])
    assert job["status"] == "failed"
    assert (job["result"]["failure_code"], job["result"]["diagnostic"], job["result"]["stage"]) == (
        "lesson_validation_failed", "semantic_support", "review")
    assert job["result"]["review"] == {"reviewed": 1, "rejected": 1, "rejected_sections": [0], "issues": ["missing_support"]}
    assert "stage=review" in job["result"]["text"]
    await service.aclose()


@pytest.mark.anyio
async def test_a_pasted_result_line_or_bare_number_chooses_from_the_pending_list(tmp_path):
    service = StudyService(StudyStore(tmp_path / "study.sqlite3", "owner"), Intake(), Content(), Model())
    listed = service.submit("search", "/paper attention is all you need")
    assert (await finished(service, listed["job_id"]))["status"] == "ready"
    assert len(service.store.selection()) == 2
    assert service.submit("bare", "/choose")["reply"].startswith("اكتب /choose ورقم الورقة")
    chosen = service.submit("pasted", "1. Attention Is All You Need")
    assert service.store.get_job(chosen["job_id"])["payload"]["text"] == "/choose 1"
    assert chosen["reply"].startswith("📖")
    assert (await finished(service, chosen["job_id"]))["status"] == "ready"
    # The list is consumed, so a later "2" (say, a quiz answer) is not a paper choice.
    assert service.store.selection() == []
    assert service.submit("plain", "/choose")["reply"].startswith("مفيش قائمة نتايج حالية")
    await service.aclose()


@pytest.mark.anyio
async def test_arabic_follow_up_without_an_open_paper_is_not_sent_to_arxiv(tmp_path):
    intake = Intake()
    service = StudyService(StudyStore(tmp_path / "study.sqlite3", "owner"), intake, Content(), Model())
    reply = service.submit("simplify", "بسّطها")
    assert "job_id" not in reply and reply["reply"].startswith("لسه مفيش ورقة مفتوحة")
    await service.aclose()


def test_first_lessons_keep_the_opening_where_the_method_usually_is():
    from src.services.study.service import select_evidence

    blocks = [EvidenceBlock(id=f"p{i // 3 + 1}b{i % 3}", page=i // 3 + 1, section="S", text=f"block {i} text")
              for i in range(51)]
    document = PaperContent(paper=paper_for_selection(), source_sha256="a" * 64, parser_revision="t", page_count=17,
                            blocks=blocks, missing_pages=[], coverage="full_text")
    first = [b.id for b in select_evidence(document, "ابدأ درس تمهيدي", opening=12)]
    assert first[:12] == [b.id for b in blocks[:12]] and len(first) == 24
    followup = [b.id for b in select_evidence(document, "سؤال")]
    assert "p4b0" not in followup[:4]


def paper_for_selection():
    from tests.unit.test_study_service import paper

    return paper()


@pytest.mark.anyio
async def test_degenerate_and_unrequested_superiority_sections_are_withheld_not_shown(tmp_path):
    repeated = "َـ" * 700

    class Screened(Model):
        async def complete(self, job, purpose, messages, **kwargs):
            if purpose == "grounding_review":
                return {"output": {"unsupported_sections": [], "issues": []}}
            return {"output": {"title": "شرح تمهيدي", "sections": [
                {"heading": "الطريقة", "kind": "paper", "text": "النموذج بيستخدم آلية الانتباه عشان يربط الكلمات ببعض.",
                 "evidence_ids": ["p1b1s0"]},
                {"heading": "تكرار", "kind": "paper", "text": "النموذج بيستخدم المسترج" + repeated, "evidence_ids": ["p1b1s0"]},
                {"heading": "النتيجة", "kind": "paper", "text": "النموذج متفوق على كل الطرق التانية في الانتباه.",
                 "evidence_ids": ["p1b1s0"]}]}}

    service = StudyService(StudyStore(tmp_path / "study.sqlite3", "owner"), Intake(), Content(), Screened())
    admitted = service.submit("paper", "/paper 1706.03762")
    job = await finished(service, admitted["job_id"])
    assert job["status"] == "ready"
    assert job["result"]["review"]["screened"] == ["degenerate_text", "unrequested_comparison"]
    text = job["result"]["text"]
    assert "ـ" * 6 not in text and "متفوق" not in text
    assert "⚠️ شلت 2 جزء" in text and "آلية الانتباه" in text
    await service.aclose()
