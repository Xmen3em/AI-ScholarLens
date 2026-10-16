"""A finite LangGraph teaching workflow, backed by durable application state."""

import asyncio
import base64
import json
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from src.operations import emit_event
from src.services.study.content import ContentError, PaperContent
from src.services.study.intake import StudyInputError, StudyPaper, normalize_input
from src.services.study.store import StoreConflict, StudyStore
from src.services.study.tutor import PROMPT_REVISION, SYSTEM, Lesson, TutorError, render_lesson, validate_lesson
from src.services.study.visuals import study_map

HELP = ("أهلًا! ابعت رابط arXiv أو رقم الورقة، أو /paper وبعدها اسمها. هنعمل شرح بالمصري وبعدين نناقشها مع بعض.\n\n"
        "/study — الورقة الحالية وآخر شرح\n/notes — ملاحظات فيها الاقتباسات الأصلية\n"
        "/level beginner أو /level researcher — مستوى الشرح\n/forget — امسح سياقك وتفضيلاتك\n"
        "بعد الشرح ابعت سؤالك، أو جرّب: بسّطها، مثال، اشرح الطريقة، اختبر فهمي.\n"
        "الشرح بيتولد بالذكاء الاصطناعي؛ راجع المصدر، خصوصًا المعادلات والجداول.")


class StudyState(TypedDict, total=False):
    job_id: str
    text: str
    paper: StudyPaper
    content: PaperContent
    followup: bool
    result: dict


def select_evidence(content: PaperContent, question: str, *, limit: int = 24):
    blocks = content.blocks
    if len(blocks) <= limit:
        return blocks
    terms = set(re.findall(r"[a-z]{3,}", question.lower()))
    hints = {"نتيجة": "experiment results evaluation", "نتائج": "experiment results evaluation",
             "الطريقة": "method architecture model attention", "حدود": "limitations conclusion",
             "dataset": "dataset data evaluation", "اختبر": "method contribution"}
    for term, english in hints.items():
        if term in question:
            terms.update(english.split())
    # Include opening and closing context plus a spread across the document.
    chosen = set(range(min(4, len(blocks)))) | set(range(max(0, len(blocks) - 3), len(blocks)))
    for i in range(8):
        chosen.add(round(i * (len(blocks) - 1) / 7))
    ranked = sorted(range(len(blocks)), key=lambda i: sum(t in blocks[i].text.lower() for t in terms), reverse=True)
    for index in ranked:
        if len(chosen) >= limit:
            break
        chosen.add(index)
    return [blocks[i] for i in sorted(chosen)[:limit]]


class StudyService:
    def __init__(self, store: StudyStore, intake, content, model):
        self.store, self.intake, self.content, self.model = store, intake, content, model
        self.tasks: set[asyncio.Task] = set()
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
        command, _, argument = text.partition(" ")
        command = command.lower()
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
        if command.startswith("/") and command not in {"/paper", "/choose", "/ask", "/quiz"}:
            return {"reply": HELP}
        if command == "/quiz":
            text = "اختبر فهمي بسؤال واحد من الورقة؛ ما تقولش الإجابة لسه."
        elif command == "/ask":
            text = argument
        context = self.store.context()
        if not context and command not in {"/paper", "/choose"}:
            # Preserve the existing general-concept assistant for explicit questions.
            if re.match(r"(?i)^(what|why|how|explain|define|understand|ما هو|ايه|إيه|اشرح|يعني)\b", text):
                return {"fallback": True}
        try:
            job = self.store.create_job(intent, {"text": text}, max_calls=4)
        except StoreConflict:
            return {"reply": "في طلب شغّال بالفعل أو معرّف الطلب متعارض. استنى النتيجة؛ مش هكرر أي استدعاء تلقائيًا."}
        if job["status"] == "running" and not any(task.get_name() == job["id"] for task in self.tasks):
            task = asyncio.create_task(self._run(job["id"], text), name=job["id"])
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        return {"job_id": job["id"], "reply": "بجهّز الشرح من الورقة… هبعت النتيجة هنا. تقدر تستخدم /study لمعرفة الورقة الحالية."}

    async def _run(self, job_id, text):
        try:
            async with asyncio.timeout(160):
                state = await self.graph.ainvoke({"job_id": job_id, "text": text}, config={"recursion_limit": 8})
            self.store.finish_job(job_id, state["result"])
            emit_event("study_job_completed", outcome="ready")
        except asyncio.CancelledError:
            # Startup recovery marks any reserved attempt unknown; no automatic resume.
            raise
        except Exception as exc:
            code = exc.code if isinstance(exc, (ContentError, StudyInputError)) else "study_generation_unavailable"
            if isinstance(exc, TutorError) and str(exc) in {"lesson_validation_failed", "study_memory_unavailable"}:
                code = str(exc)
            messages = {
                "lesson_validation_failed": "الشرح ما اجتازش التحقق من المصادر، فمش هعرض إجابة ممكن تكون مضللة.",
                "study_memory_unavailable": "الذاكرة المتاحة قليلة حاليًا. الطلب ما اتكررش تلقائيًا.",
                "pdf_unavailable": "ملف الـPDF مش متاح من arXiv دلوقتي؛ جرّب طلب جديد لاحقًا.",
                "needs_ocr": "الورقة محتاجة OCR. مسار OCR المستضاف لسه اختياري ومش مفعّل؛ مش هشرح ملف مش مقروء.",
            }
            self.store.finish_job(job_id, {"text": messages.get(code, "ماقدرتش أكمل الطلب أو أتحقق من الشرح. ابعت طلب جديد لو تحب تحاول تاني؛ مفيش إعادة تلقائية.")}, status="failed")
            emit_event("study_job_completed", outcome="failed", error_class=type(exc).__name__)

    async def _resolve(self, state: StudyState) -> dict:
        text = state["text"]
        command, _, argument = text.partition(" ")
        if command.lower() == "/choose":
            options = self.store.selection()
            if not argument.isdecimal() or not 1 <= int(argument) <= len(options):
                raise StudyInputError("invalid_selection")
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
        document = state.get("content") or await self.content.acquire(state["paper"])
        if not document.blocks:
            raise ContentError("needs_ocr")
        return {"content": document}

    async def _teach(self, state: StudyState) -> dict:
        document = state["content"]
        question = state["text"] if state.get("followup") else "ابدأ درس تمهيدي متكامل عن الورقة."
        selected = select_evidence(document, question)
        context = self.store.context()
        recent = context["turns"] if context and context["paper_id"] == document.paper.arxiv_id and state.get("followup") else []
        payload = {"prompt_revision": PROMPT_REVISION, "task": "followup" if state.get("followup") else "first_lesson",
                   "paper": {"id": document.paper.arxiv_id, "title": document.paper.title},
                   "coverage": document.coverage, "depth": self.store.preferences()["depth"],
                   "question": question, "recent_dialogue_not_evidence": recent[-4:],
                   "source_blocks": [b.model_dump() for b in selected]}
        result = await self.model.complete(state["job_id"], "followup" if state.get("followup") else "lesson",
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            schema=Lesson.model_json_schema())
        lesson = validate_lesson(result["output"], selected)
        text = render_lesson(lesson, selected, document.paper.source_url, title=document.paper.title, coverage=document.coverage)
        self.store.save_paper(document.paper.arxiv_id, document.model_dump(), None if state.get("followup") else lesson.model_dump())
        if not state.get("followup"):
            self.store.activate(document.paper.arxiv_id, {"title": document.paper.title})
        else:
            self.store.append_turn(document.paper.arxiv_id, question, text)
        response = {"text": text}
        if not state.get("followup"):
            picture = await asyncio.to_thread(study_map, lesson)
            if picture and len(picture) <= 180000:
                response["image"] = base64.b64encode(picture).decode()
        return {"result": response}

    @staticmethod
    def notes(document: PaperContent, lesson: Lesson) -> str:
        text = render_lesson(lesson, document.blocks, document.paper.source_url, title=document.paper.title, coverage=document.coverage)
        quotes = [f"[{s.block_id}] {s.quote}" for section in lesson.sections for s in section.evidence]
        return text + "\n\nالاقتباسات الأصلية للتحقق:\n" + "\n\n".join(dict.fromkeys(quotes))
