"""Compare frozen baseline and current selectors on separate synthetic examples."""

import argparse
import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path

from evaluation.quality_fixes.development_runner import StaticSearch
from src.config import Settings
from src.schemas.api.rag import AskRequest
from src.services.ollama.client import OllamaClient
from src.services.rag import service as current
from src.services.rag.context import INSUFFICIENT_EVIDENCE_ANSWER

OUT = Path("test_output/selector_reliability")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT / "development.final.json")
    parser.add_argument("--current-only", action="store_true")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("selector_baseline", OUT / "service_baseline.py")
    baseline = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = baseline
    spec.loader.exec_module(baseline)
    baseline.SYSTEM_PROMPT_PATH = current.SYSTEM_PROMPT_PATH
    # The baseline module must retain its old internal array contract.
    class ArrayAnswer:
        @staticmethod
        def model_json_schema():
            return json.loads((OUT / "payload-ave-1-batch0.json").read_text())["format"]

        @staticmethod
        def model_validate_json(raw):
            from pydantic import BaseModel, ConfigDict, Field
            class LegacyAnswer(BaseModel):
                model_config = ConfigDict(extra="forbid", strict=True)
                answer: list[str] = Field(max_length=3)
            return LegacyAnswer.model_validate_json(raw)
    baseline.GeneratedAnswer = ArrayAnswer
    settings = Settings(ollama_host="http://localhost:11434")
    client = OllamaClient(settings)
    cases = json.loads(Path("evaluation/selector_reliability/development.json").read_text())["cases"]
    rows = []
    try:
        for label, module in (("before", baseline), ("string", current)):
            if args.current_only and label == "before":
                continue
            for case in cases:
                rag = module.RAGService(StaticSearch(case), client, settings)
                request = AskRequest(query=case["query"], use_hybrid=False)
                prepared = await rag.prepare(request)
                for endpoint in ("ask", "stream"):
                    start = time.perf_counter()
                    row = dict(variant=label, id=case["id"], endpoint=endpoint, facts=len(case["required_sentences"]))
                    try:
                        answer = (await rag.ask(request)).answer if endpoint == "ask" else "".join([c.response async for c in rag.generate_stream(prepared)])
                        row.update(ok=True, answer=answer, abstained=answer == INSUFFICIENT_EVIDENCE_ANSWER, covered_facts=sum(s in answer for s in case["required_sentences"]))
                    except Exception as exc:
                        row.update(ok=False, error=type(exc).__name__, covered_facts=0)
                    row["seconds"] = time.perf_counter()-start
                    rows.append(row)
                    args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
                    print(label, case["id"], endpoint, row["ok"], flush=True)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
