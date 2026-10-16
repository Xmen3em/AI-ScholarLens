"""Explicit, durable 12-attempt development smoke. Default performs no work."""

import argparse
import asyncio
import json
import os
from pathlib import Path


async def execute(case: str, revision: str = "v1") -> dict:
    import httpx
    from src.commands.study_research import ResearchSettings
    from src.services.study.content import PaperContentService, render_page
    from src.services.study.intake import ArxivIntake
    from src.services.study.store import StudyStore
    from src.services.study.tools import StudyTools
    from src.services.study.tutor import SYSTEM, LessonDraft, StudyModel, host_memory_mib, validate_lesson

    if host_memory_mib() < 1024:
        return {"status": "insufficient_memory", "outbound_calls": 0}
    root = Path("data/study")
    store = StudyStore(root / "smoke.sqlite3", "development-smoke-20261017")
    store.set_total_ceiling(12)
    settings = ResearchSettings()
    def audit(result):
        (root / f"smoke-{case}-{revision}-{result['purpose']}-raw.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    model = StudyModel(settings.hf_token, store, audit=audit)
    try:
        if case in {"lesson", "followup", "unsupported"}:
            from src.services.study.service import StudyService

            texts = {"lesson": "/paper 2005.11401v4", "followup": "اشرح الفرق بين retriever و generator بمثال بسيط",
                     "unsupported": "الورقة بتقول إيه عن درجة حرارة الجو في القاهرة؟"}
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=30,
                headers={"User-Agent": "ScholarLens-private-development/0.1"}) as public:
                service = StudyService(store, ArxivIntake(public), PaperContentService(root / "smoke-sources", public), model)
                try:
                    result = service.submit("smoke:" + case + "-" + revision, texts[case])
                    if not result.get("job_id"):
                        return result
                    if service.tasks:
                        await asyncio.gather(*service.tasks)
                    job = store.get_job(result["job_id"])
                    assert job is not None
                    return {"status": job["status"], "job_id": job["id"], "attempts": store.attempts(job["id"]), "result": job["result"]}
                finally:
                    await service.aclose()
        job = store.create_job("smoke:" + case + "-" + revision, {"case": case}, max_calls=4 if case == "deep" else 1)
        if job["status"] != "running":
            return {"status": job["status"], "result": job["result"], "attempts": store.attempts(job["id"])}
        try:
            source = StudyTools(store)
            if case == "ocr":
                from src.services.study.ocr import RemoteOCR

                async with httpx.AsyncClient(trust_env=False) as public:
                    path = PaperContentService(root / "smoke-sources", public).source_path(source.document.paper)
                image = await asyncio.to_thread(render_page, path, 1)
                ocr = RemoteOCR(settings.hf_token, store)
                try:
                    result = {"text": await ocr.extract_page(job["id"], image)}
                finally:
                    await ocr.aclose()
            else:
                from src.services.study.deep import HFStudyChat, create_study_research

                os.environ["LANGSMITH_TRACING"] = os.environ["LANGCHAIN_TRACING_V2"] = "false"
                agent = create_study_research(HFStudyChat(transport=model, job_id=job["id"]), source,
                    SYSTEM + "\nUse the read tools to verify the method. Return final JSON matching: " + json.dumps(LessonDraft.model_json_schema()))
                async with asyncio.timeout(120):
                    output = await agent.ainvoke({"messages": [{"role": "user", "content": "Use search_evidence ONCE with English query 'retriever generator method' and limit 3, then explain RAG in Egyptian Arabic in 1-3 sections citing the returned evidence IDs. Return final JSON immediately after that one tool result."}]},
                        config={"recursion_limit": 16, "callbacks": []})
                lesson = validate_lesson(json.loads(output["messages"][-1].content), source.document.blocks)
                result = {"lesson": lesson.model_dump(), "tool_calls": source.calls}
            store.finish_job(job["id"], result)
            return {"status": "ready", "result": result, "attempts": store.attempts(job["id"])}
        except Exception as exc:
            store.finish_job(job["id"], {"error_class": type(exc).__name__, "category": str(exc) if type(exc).__name__ == "TutorError" else "unavailable"}, status="failed")
            return {"status": "failed", "error_class": type(exc).__name__, "attempts": store.attempts(job["id"])}
    finally:
        await model.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--case", choices=["lesson", "followup", "unsupported", "deep", "ocr"], default="lesson")
    parser.add_argument("--revision", choices=["v1", "v2", "v3", "v4", "v5"], default="v1", help="Explicit new development case; does not reset the shared 12-attempt ceiling")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"status": "offline", "maximum_attempts": 12, "outbound_calls": 0}))
        return
    result = asyncio.run(execute(args.case, args.revision))
    path = Path(f"data/study/smoke-{args.case}-{args.revision}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result.get("status"), "attempts_for_case": len(result.get("attempts", [])), "report": str(path)}))


if __name__ == "__main__":
    main()
