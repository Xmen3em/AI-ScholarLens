"""Optional isolated Deep Agents worker. No inference without an admitted job."""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ResearchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    hf_token: SecretStr
    telegram_owner_id: int = Field(gt=0, lt=2**52)

    def __init__(self, **values):
        super().__init__(**values)


async def run_job(job_id: str) -> dict:
    from src.services.study.deep import HFStudyChat, create_study_research
    from src.services.study.store import StudyStore
    from src.services.study.tools import StudyTools
    from src.services.study.tutor import SYSTEM, LessonDraft, StudyModel, validate_lesson

    settings = ResearchSettings()
    store = StudyStore(Path("data/study/sessions.sqlite3"), str(settings.telegram_owner_id))
    job = store.get_job(job_id)
    if not job or job["status"] != "running" or not job["payload"].get("text", "").startswith("/deep "):
        raise ValueError("admitted_research_job_required")
    tools = StudyTools(store, max_calls=8)
    transport = StudyModel(settings.hf_token, store)
    try:
        model = HFStudyChat(transport=transport, job_id=job_id)
        system = SYSTEM + "\nYou have read-only paper tools. Use them to verify the answer. No external web research is available. "
        system += "Return your final answer as JSON matching this schema: " + json.dumps(LessonDraft.model_json_schema())
        agent = create_study_research(model, tools, system)
        context = store.context()
        payload = {"question": job["payload"]["text"][6:], "depth": store.preferences()["depth"],
                   "paper": tools.document.paper.arxiv_id, "recent_dialogue_not_evidence": context["turns"][-2:] if context else []}
        async with asyncio.timeout(95):
            result = await agent.ainvoke({"messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]},
                                         config={"recursion_limit": 16, "callbacks": []})
        raw = json.loads(result["messages"][-1].content)
        validate_lesson(raw, tools.document.blocks)
        return raw
    finally:
        await transport.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    os.environ["LANGSMITH_TRACING"] = os.environ["LANGCHAIN_TRACING_V2"] = "false"
    logging.disable(logging.CRITICAL)
    try:
        result = asyncio.run(run_job(args.job))
        print(json.dumps({"output": result}, ensure_ascii=True), flush=True)
    except Exception:
        print(json.dumps({"error": "research_unavailable_or_invalid"}), flush=True)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
