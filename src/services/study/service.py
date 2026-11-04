"""A finite LangGraph teaching workflow, backed by durable application state."""

import asyncio
import base64
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from src.operations import emit_event
from src.services.study.content import ContentError, PaperContent
from src.services.study.evidence import evidence_catalog
from src.services.study.failures import SAFE_DIAGNOSTICS, SAFE_FAILURES, SAFE_STAGES, failure_payload, staged
from src.services.study.intake import StudyInputError, StudyPaper, normalize_input
from src.services.study.pool import JOB_DEADLINE
from src.services.study.store import StoreConflict, StudyStore
from src.services.study.tutor import (
    PROMPT_REVISION,
    SYSTEM,
    Lesson,
    TutorError,
    accept_draft,
    check_claims,
    draft_report,
    lesson_schema,
    page_label,
    render_lesson,
    screen_claims,
    validate_draft,
)
from src.services.study.visuals import study_map

HELP = ("أهلًا! ابعت رابط arXiv أو رقم الورقة، أو /paper وبعدها اسمها. هنعمل شرح بالمصري وبعدين نناقشها مع بعض.\n\n"
        "/study — الورقة الحالية وآخر شرح\n/notes — ملاحظات فيها الاقتباسات الأصلية\n"
        "/level beginner أو /level researcher — مستوى الشرح\n/forget — امسح سياقك وتفضيلاتك\n"
        "/deep سؤالك — بحث أعمق داخل الورقة بأدوات قراءة محدودة (اختياري)\n"
        "بعد الشرح ابعت سؤالك، أو جرّب: بسّطها، مثال، اشرح الطريقة، اختبر فهمي.\n"
        "الشرح بيتولد بالذكاء الاصطناعي؛ راجع المصدر، خصوصًا المعادلات والجداول.")
BUSY = "في طلب شغّال حاليًا. استنى النتيجة؛ مش هبدأ طلب تاني بالتوازي أو أكرر الاستدعاء تلقائيًا."
# The worker stops its own agent loop at 95 s; this parent ceiling also covers process start/teardown.
DEEP_WORKER_TIMEOUT_SECONDS = 105


class StudyState(TypedDict, total=False):
    job_id: str
    text: str
    paper: StudyPaper
    content: PaperContent
    followup: bool
    result: dict


def select_evidence(content: PaperContent, question: str, *, limit: int = 24, opening: int = 4):
    blocks = content.blocks
    if len(blocks) <= limit:
        return blocks
    terms = set(re.findall(r"[a-z]{3,}", question.lower()))
    hints = {"نتيجة": "experiment results evaluation", "نتائج": "experiment results evaluation",
             "الطريقة": "method architecture model attention", "حدود": "limitations conclusion",
             "dataset": "dataset data evaluation", "اختبر": "method contribution",
             "تمهيدي": "method model approach training experiments results limitations"}
    for term, english in hints.items():
        if term in question:
            terms.update(english.split())
    # Include opening and closing context plus a spread across the document. A first
    # lesson keeps a longer opening: the problem and method usually come first.
    chosen = set(range(min(opening, len(blocks)))) | set(range(max(0, len(blocks) - 3), len(blocks)))
    for i in range(8):
        chosen.add(round(i * (len(blocks) - 1) / 7))
    ranked = sorted(range(len(blocks)), key=lambda i: sum(t in blocks[i].text.lower() for t in terms), reverse=True)
    for index in ranked:
        if len(chosen) >= limit:
            break
        chosen.add(index)
    return [blocks[i] for i in sorted(chosen)[:limit]]


def _acknowledgement(command: str, text: str, has_paper: bool) -> str:
    # Say what is actually happening; a title search is not yet a lesson.
    if command == "/deep":
        return "🔎 ببحث جوّه الورقة بأدوات القراءة… ده ممكن ياخد دقيقة. هبعت النتيجة هنا."
    if command == "/quiz":
        return "📝 بجهّز سؤال من الورقة…"
    lesson = "📖 بجهّز الشرح التمهيدي من الورقة… هبعت النتيجة هنا."
    if command == "/choose":
        return lesson
    try:
        kind = normalize_input(text.partition(" ")[2] if command == "/paper" else text)[0]
    except StudyInputError:
        kind = None
    if kind == "id":
        return lesson
    if command == "/paper" or not has_paper:
        return "🔎 بدوّر على الورقة في arXiv…"
    return "💬 بجهّز الإجابة من الورقة…"


class StudyService:
    def __init__(self, store: StudyStore, intake, content, model, *, research_python: Path | None = None, ocr=None,
                 observer: Callable[[str, Lesson, list[dict]], None] | None = None):
        self.store, self.intake, self.content, self.model = store, intake, content, model
        # Evaluation hook: sees each accepted lesson and the catalog the writer was given. Production passes none.
        self.observer = observer
        self.research_python, self.ocr = research_python, ocr
        self.tasks: set[asyncio.Task] = set()
        # Finite stage names per running job, shown to the student as progress; never paper or model text.
        self.progress: dict[str, str] = {}
        graph = StateGraph(StudyState)
        graph.add_node("resolve", self._resolve)
        graph.add_node("extract", self._extract)
        graph.add_node("teach", self._teach)
        graph.add_edge(START, "resolve")
        graph.add_conditional_edges("resolve", lambda state: "done" if state.get("result") else "extract",
                                    {"done": END, "extract": "extract"})
        graph.add_edge("extract", "teach")
        graph.add_edge("teach", END)
        self.graph = graph.compile()

    async def aclose(self):
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

    def submit(self, intent: str, text: str) -> dict:
        if not text.strip() or len(text) > 512:
            return {"reply": HELP}
        text = text.strip()
        capability_question = " ".join(re.sub(r"[^\w\s]", "", text.casefold()).split())
        if capability_question in {"what you can make now", "what can you do", "what can you do now",
                                   "what can you help me with", "تقدر تعمل إيه", "تقدر تعمل ايه", "بتعمل ايه"}:
            return {"reply": HELP}
        if not text.startswith("/"):
            choice = self._pending_choice(text)
            if choice:
                text = f"/choose {choice}"
        command, _, argument = text.partition(" ")
        command = command.lower()
        if command == "/choose" and not argument.strip():
            if self.store.selection():
                return {"reply": "اكتب /choose ورقم الورقة من القائمة، مثلًا: /choose 1"}
            return {"reply": "مفيش قائمة نتايج حالية. ابعت /paper واسم الورقة بالإنجليزي الأول."}
        if command == "/deep":
            example = "/deep اشرح طريقة التدريب خطوة بخطوة من الدليل"
            if not argument.strip():
                return {"reply": "اكتب سؤالًا بعد /deep عن الورقة الحالية، مثل:\n" + example +
                        "\nلو لسه ما اخترتش ورقة، افتحها الأول بأمر /paper والرابط."}
            try:
                kind, _ = normalize_input(argument)
            except StudyInputError:
                kind = None
            if kind == "id" or argument.startswith(("http://", "https://")):
                return {"reply": "بعد /deep اكتب سؤالك، مش رابط الورقة. لفتح الورقة استخدم:\n/paper " + argument +
                        "\nوبعد ما الشرح يجهز ابعت مثلًا:\n" + example}
        if command in {"/paper", "/choose", "/ask", "/deep"} and not argument.strip():
            return {"reply": HELP}
        if command in {"/start", "/help"}:
            return {"reply": HELP}
        if command == "/level":
            try:
                self.store.set_preferences(depth=argument)
            except StoreConflict:
                return {"reply": "اختار /level beginner أو /level researcher"}
            return {"reply": "تمام، مستوى الشرح اتغيّر إلى " + argument}
        if command in {"/study", "/notes"}:
            context = self.store.context()
            if not context:
                return {"reply": "لسه مفيش ورقة مختارة. ابعت /paper وبعدها اسم الورقة أو رابطها."}
            paper = self.store.paper(context["paper_id"])
            if command == "/notes" and paper and paper["lesson"]:
                return {"reply": self.notes(PaperContent.model_validate(paper["content"]), Lesson.model_validate(paper["lesson"]))}
            return {"reply": "الورقة الحالية: " + context["metadata"]["title"] + "\nhttps://arxiv.org/abs/" + context["paper_id"] +
                    "\nاسألني عن الفكرة أو الطريقة أو النتائج. /notes لعرض الشرح والاقتباسات."}
        if command == "/forget":
            if any(not task.done() for task in self.tasks):
                return {"reply": "في طلب شغّال دلوقتي. استنى يخلص وبعدين ابعت /forget عشان يتمسح السياق كله."}
            self.store.forget()
            return {"reply": "مسحت الورقة الحالية وسياق الحوار والتفضيلات. ملفات المصادر العامة وسجل عدد الاستدعاءات بيفضلوا محفوظين."}
        if command.startswith("/") and command not in {"/paper", "/choose", "/ask", "/quiz", "/deep"}:
            return {"reply": HELP}
        if command == "/deep" and (not self.research_python or not self.store.context()):
            return {"reply": "الشرح العادي متاح. وضع /deep محتاج ورقة مختارة وبيئة research الاختيارية المثبتة."}
        if command == "/quiz":
            text = "اختبر فهمي بسؤال واحد من الورقة؛ ما تقولش الإجابة لسه."
        elif command == "/ask":
            text = argument
        context = self.store.context()
        if not context and command not in {"/paper", "/choose"}:
            # Preserve the existing general-concept assistant for explicit questions.
            if command == "/ask" or re.match(r"(?i)^(what|why|how|which|who|where|when|explain|define|understand|ما هو|ايه|إيه|اشرح|يعني|هل|مين|فين|متى)\b", text):
                if any(not task.done() for task in self.tasks):
                    return {"reply": BUSY}
                return {"fallback": True}
            if command != "/ask" and not re.search(r"[A-Za-z0-9]", text):
                return {"reply": "لسه مفيش ورقة مفتوحة. ابعت رقم arXiv (زي 2005.11401) أو /paper واسم الورقة بالإنجليزي، وبعدها اسألني."}
        try:
            job = self.store.create_job(intent, {"text": text}, max_calls=4)
        except StoreConflict:
            return {"reply": "في طلب شغّال بالفعل أو معرّف الطلب متعارض. استنى النتيجة؛ مش هكرر أي استدعاء تلقائيًا."}
        if job["status"] == "running" and not any(task.get_name() == job["id"] for task in self.tasks):
            task = asyncio.create_task(self._run(job["id"], text), name=job["id"])
            self.tasks.add(task)
            self.progress[job["id"]] = "started"
            task.add_done_callback(self.tasks.discard)
            task.add_done_callback(lambda done: self.progress.pop(done.get_name(), None))
        return {"job_id": job["id"], "reply": _acknowledgement(command, text, bool(context))}

    def request_kind(self, text: str) -> Literal["paper", "question", "other"]:
        """What a message will cost before it runs: a new paper, a follow-up, or no model call (mirrors _resolve)."""
        text = text.strip()
        if not text.startswith("/") and self._pending_choice(text):
            return "paper"
        command, _, argument = text.partition(" ")
        command = command.lower()
        if command == "/ask":
            # submit runs /ask's argument, which may itself be an arXiv ID.
            text, command, argument = argument.strip(), "", ""
        if command == "/choose":
            return "paper"
        if command.startswith("/") and command not in {"/paper", "/quiz", "/deep"}:
            return "other"
        is_paper = command == "/paper"
        try:
            identity = normalize_input(argument if is_paper else text)[0] == "id"
        except StudyInputError:
            identity = False
        if identity:
            return "paper"
        return "question" if self.store.context() and not is_paper else "other"

    def _pending_choice(self, text: str) -> int | None:
        options = self.store.selection()
        if not options:
            return None
        match = re.fullmatch(r"\s*(\d{1,2})\s*[.)\-:]?\s*(.*?)\s*", text, re.DOTALL)
        if match:
            number, rest = int(match.group(1)), match.group(2).casefold()
            if 1 <= number <= len(options) and (not rest or rest in options[number - 1]["title"].casefold()):
                return number
            return None
        titles = [option["title"].casefold() for option in options]
        return titles.index(text.casefold()) + 1 if text.casefold() in titles else None

    async def _run(self, job_id, text):
        try:
            async with asyncio.timeout(160) as deadline:
                # Time spent waiting for a model slot does not count toward the 160 s (multi-user beta).
                JOB_DEADLINE.set(deadline)
                state = await self.graph.ainvoke({"job_id": job_id, "text": text}, config={"recursion_limit": 8})
            result = state["result"]
            if "followup" in state:
                # The multi-user beta counts a delivered answer by what it was.
                result = {**result, "kind": "question" if state["followup"] else "paper"}
            self.store.finish_job(job_id, result)
            emit_event("study_job_completed", outcome="ready")
        except asyncio.CancelledError:
            # Startup recovery marks any reserved attempt unknown; no automatic resume.
            raise
        except Exception as exc:
            code = exc.code if isinstance(exc, (ContentError, StudyInputError)) else "study_generation_unavailable"
            failure = failure_payload(exc, default=code)
            code = failure["error"]
            messages = {
                "lesson_validation_failed": "ماقدرتش أتحقق من الإجابة من نص الورقة، فمش هعرضها عشان ماتكونش مضللة. جرّب سؤال أضيق عن خطوة أو جدول أو صفحة محددة.",
                "study_memory_unavailable": "الذاكرة المتاحة قليلة حاليًا. الطلب ما اتكررش تلقائيًا.",
                "study_context_limit": "سياق الطلب أكبر من الحد الحالي. جرّب سؤالًا عن خطوة محددة؛ مش هكرر الطلب تلقائيًا.",
                "study_tool_budget_exhausted": "وصلت لحدّ قراءة المصادر المسموح للطلب ده. مش هعرض تحليلًا ناقصًا أو أعيد الطلب تلقائيًا.",
                "study_provider_http_429": "مزوّد النموذج وصل لحدّ الطلبات حاليًا. الطلب مش هيتكرر تلقائيًا.",
                "pdf_unavailable": "ملف الـPDF مش متاح من arXiv دلوقتي؛ جرّب طلب جديد لاحقًا.",
                "pdf_size_limit": "حجم الملف أكبر من حد النسخة الحالية: 20 MiB. اختار ورقة أصغر حاليًا.",
                "pdf_processing_failed": "ماقدرتش أقرأ ملف الـPDF. الحد الحالي 45 صفحة و20 MiB؛ الملفات الأطول أو غير المقروءة مش مدعومة في النسخة دي.",
                "source_cache_full": "مساحة كاش المصادر وصلت للحد الحالي. محتاجين نراجع الملفات المحلية قبل إضافة ورقة جديدة.",
                "needs_ocr": "الورقة محتاجة OCR. مسار OCR المستضاف لسه اختياري ومش مفعّل؛ مش هشرح ملف مش مقروء.",
                "research_worker_timeout": "وضع /deep خد وقت أطول من الحد المسموح، فوقفته. الطلب مش هيتكرر تلقائيًا.",
                "research_worker_unavailable": "ماقدرتش أشغّل بيئة /deep الاختيارية على الجهاز. الشرح العادي لسه متاح.",
                "research_final_json_invalid": "وضع /deep رجّع إجابة نهائية مش بالشكل المطلوب، فمش هعرضها. مفيش إعادة تلقائية.",
            }
            reply = messages.get(code, "ماقدرتش أكمل الطلب أو أتحقق من الشرح. ابعت طلب جديد لو تحب تحاول تاني؛ مفيش إعادة تلقائية.")
            result = {"failure_code": code, "diagnostic": failure.get("diagnostic", code)}
            review = getattr(exc, "review", None)
            if type(review) is dict:
                result["review"] = review
            if "stage" in failure:
                # Deep failures carry a finite stage; show the owner the same safe labels the job stores.
                result["stage"] = failure["stage"]
                reply += f"\n\nتشخيص /deep:\nstage={failure['stage']} code={code} diagnostic={result['diagnostic']}"
            self.store.finish_job(job_id, {"text": reply, **result}, status="failed")
            emit_event("study_job_completed", outcome="failed", error_class=type(exc).__name__)

    async def _resolve(self, state: StudyState) -> dict:
        text = state["text"]
        command, _, argument = text.partition(" ")
        if command.lower() == "/choose":
            options = self.store.selection()
            if not argument.isdecimal() or not 1 <= int(argument) <= len(options):
                raise StudyInputError("invalid_selection")
            self.store.selection([])
            return {"paper": StudyPaper.model_validate(options[int(argument) - 1]), "followup": False}
        context = self.store.context()
        is_paper = command.lower() == "/paper"
        value = argument if is_paper else text
        identity = False
        try:
            kind, _ = normalize_input(value)
            identity = kind == "id"
        except StudyInputError:
            if is_paper or text.startswith(("http:", "https:")):
                raise
        if context and not is_paper and not identity:
            saved = self.store.paper(context["paper_id"])
            if saved:
                document = PaperContent.model_validate(saved["content"])
                return {"paper": document.paper, "content": document, "followup": True}
        papers = await self.intake.resolve(value)
        if not papers:
            return {"result": {"text": "ملقيتش ورقة AI/ML مناسبة بالعنوان ده. جرّب رقم arXiv أو العنوان بالإنجليزي."}}
        if not identity:
            self.store.selection([p.model_dump() for p in papers])
            lines = [f"{i}. {p.title}\n{p.source_url}" for i, p in enumerate(papers, 1)]
            return {"result": {"text": "اختار الورقة المقصودة بإرسال /choose 1 (أو رقم النتيجة):\n\n" + "\n\n".join(lines)}}
        return {"paper": papers[0], "followup": False}

    async def _extract(self, state: StudyState) -> dict:
        self.progress[state["job_id"]] = "reading"
        document = state.get("content") or await self.content.acquire(state["paper"])
        if self.ocr is not None and document.missing_pages:
            document = await self.ocr.enrich(document, self.content.source_path(document.paper), state["job_id"])
        if not document.blocks:
            raise ContentError("needs_ocr")
        return {"content": document}

    async def _teach(self, state: StudyState) -> dict:
        document = state["content"]
        question = state["text"] if state.get("followup") else "ابدأ درس تمهيدي متكامل عن الورقة."
        selected = select_evidence(document, question, opening=4 if state.get("followup") else 12)
        context = self.store.context()
        recent = context["turns"] if context and context["paper_id"] == document.paper.arxiv_id and state.get("followup") else []
        payload = {"prompt_revision": PROMPT_REVISION, "task": "followup" if state.get("followup") else "first_lesson",
                   "paper": {"id": document.paper.arxiv_id, "title": document.paper.title},
                   "coverage": document.coverage, "depth": self.store.preferences()["depth"],
                   "question": question, "recent_dialogue_not_evidence": [
                       {"question": turn["question"][:600], "answer": turn["answer"][:1800]} for turn in recent[-4:]],
                   "source_evidence": evidence_catalog(selected)}
        if question.startswith("/deep "):
            self.progress[state["job_id"]] = "researching"
            result = await self._deep(state["job_id"])
            selected = document.blocks
        else:
            system = SYSTEM
            if state.get("followup"):
                system += ("\nCURRENT TASK: answer ONLY this follow-up question in at most THREE focused sections. "
                           "Do not repeat the introductory lesson. Do not add experiments/results unless the user asks for them. "
                           "For a simple explanation use a short supported explanation, an explicitly labeled example, and optionally one question.")
            self.progress[state["job_id"]] = "writing_answer" if state.get("followup") else "writing_lesson"
            result = await self.model.complete(state["job_id"], "followup" if state.get("followup") else "lesson",
                [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                schema=lesson_schema(selected, followup=bool(state.get("followup"))))
        review: dict = {}
        stage = "result_validation"
        try:
            draft = screen_claims(validate_draft(result["output"], selected), question=question)
            stage = "review"
            self.progress[state["job_id"]] = "checking"
            draft = await check_claims(self.model, state["job_id"], draft, blocks=document.blocks, report=review)
            review.update(draft_report(draft))
            lesson, withheld = accept_draft(draft)
        except Exception as exc:
            # A worker that succeeded can still fail here, in the parent; keep that distinguishable.
            if question.startswith("/deep "):
                staged(exc, stage)
            if review:
                exc.review = review  # type: ignore[attr-defined]
            raise
        if self.observer is not None:
            self.observer(state["job_id"], lesson, evidence_catalog(selected))
        text = render_lesson(lesson, selected, document.paper.source_url, title=document.paper.title,
                             coverage=document.coverage, sampled=not state.get("followup") and len(selected) != len(document.blocks),
                             followup=bool(state.get("followup")), withheld=withheld)
        self.store.save_paper(document.paper.arxiv_id, document.model_dump(), None if state.get("followup") else lesson.model_dump())
        if not state.get("followup"):
            self.store.activate(document.paper.arxiv_id, {"title": document.paper.title})
        else:
            self.store.append_turn(document.paper.arxiv_id, question, text)
        response: dict = {"text": text}
        if review:
            response["review"] = review
        if not state.get("followup"):
            picture = await asyncio.to_thread(study_map, lesson)
            if picture and len(picture) <= 180000:
                response["image"] = base64.b64encode(picture).decode()
        return {"result": response}

    async def _deep(self, job_id: str) -> dict:
        if self.research_python is None:
            raise TutorError("research_environment_required")
        env = {name: value for name, value in os.environ.items() if name.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
        env.update(PYTHONUTF8="1", LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false")
        try:
            process = await asyncio.create_subprocess_exec(str(self.research_python), "-m", "src.commands.study_research", "--job", job_id,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=env,
                creationflags=0x08000000 if os.name == "nt" else 0)
        except OSError:
            raise staged(TutorError("research_worker_unavailable", diagnostic="OSError"), "worker_start") from None
        try:
            try:
                async with asyncio.timeout(DEEP_WORKER_TIMEOUT_SECONDS):
                    assert process.stdout is not None
                    body = bytearray()
                    while chunk := await process.stdout.read(4096):
                        body.extend(chunk)
                        if len(body) > 65536:
                            raise staged(TutorError("research_output_limit"), "worker_output")
                    await process.wait()
            except TimeoutError:
                raise staged(TutorError("research_worker_timeout", diagnostic="TimeoutError"), "worker_timeout") from None
            try:
                raw = json.loads(body)
            except ValueError:
                raw = None
            if type(raw) is dict and type(raw.get("error")) is str and raw["error"] in SAFE_FAILURES:
                diagnostic = raw.get("diagnostic")
                if type(diagnostic) is not str or diagnostic not in SAFE_DIAGNOSTICS:
                    diagnostic = None
                stage = raw.get("stage")
                # A worker error without a known stage stays unknown; never guess a phase.
                error = TutorError(raw["error"], diagnostic=diagnostic)
                if type(stage) is str and stage in SAFE_STAGES:
                    staged(error, stage)
                raise error
            if process.returncode:
                raise staged(TutorError("research_worker_failed"), "worker_exit")
            if type(raw) is not dict or "output" not in raw:
                raise staged(TutorError("research_output_invalid", diagnostic="JSONDecodeError" if raw is None else "shape"),
                              "worker_output")
            return raw
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    @staticmethod
    def notes(document: PaperContent, lesson: Lesson) -> str:
        text = render_lesson(lesson, document.blocks, document.paper.source_url, title=document.paper.title, coverage=document.coverage)
        lookup = {block.id: block for block in document.blocks}
        # The page label line is Arabic; each English quotation stays on its own LTR line.
        quotes = [f"📄 {page_label(lookup.get(s.block_id))}:\n{s.quote}" for section in lesson.sections for s in section.evidence]
        return text + "\n\n📌 الاقتباسات الأصلية للتحقق:\n\n" + "\n\n".join(dict.fromkeys(quotes))
