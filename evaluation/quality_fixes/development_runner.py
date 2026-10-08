"""Run synthetic development cases without retrieving or writing corpus data.

Baseline snapshots are the preserved pre-edit service.py.before/excerpts.py.before.
Run from the repository root: python -m evaluation.quality_fixes.development_runner.
"""

import argparse
import asyncio
import importlib.machinery
import importlib.util
import json
import sys
import time
from pathlib import Path

from src.config import Settings
from src.schemas.api.rag import AskRequest
from src.schemas.api.search import ChunkSearchResponse, PaperPassages, PassageHit
from src.services.ollama.client import OllamaClient
from src.services.rag import service as current
from src.services.rag.context import INSUFFICIENT_EVIDENCE_ANSWER

ROOT = Path("evaluation/quality_fixes")
OUTPUT = Path("test_output/quality_fixes")


def baseline_module(name):
    path = OUTPUT / (name + ".py.before")
    loader = importlib.machinery.SourceFileLoader("baseline_" + name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


class StaticSearch:
    def __init__(self, case):
        self.hits = [
            PaperPassages(arxiv_id=p["id"], title=p["id"], categories=["cs.AI"], score=1,
                          passages=[PassageHit(section_title="Abstract", section_index=0,
                                               chunk_index=0, content=p["text"], score=1)])
            for p in case["papers"]
        ]

    def search_chunks(self, query, **kwargs):
        return ChunkSearchResponse(query=query, total=len(self.hits), took_ms=0, hits=self.hits)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=["all", "before", "expanded", "default"], default="all")
    parser.add_argument("--output", type=Path, default=OUTPUT / "development_results.json")
    args = parser.parse_args()
    before = baseline_module("service")
    before.build_excerpts = baseline_module("excerpts").build_excerpts
    before.SYSTEM_PROMPT_PATH = current.SYSTEM_PROMPT_PATH
    settings = Settings(ollama_host="http://localhost:11434")
    client = OllamaClient(settings)
    rows = []
    try:
        for label, module, count in (("before", before, 1), ("expanded", current, 3), ("default", current, 1)):
            if args.variant not in ("all", label):
                continue
            for case in json.loads((ROOT / "development.json").read_text())["cases"]:
                rag = module.RAGService(StaticSearch(case), client,
                                        settings.model_copy(update={"rag_sentence_candidates_per_passage": count}))
                request = AskRequest(query=case["query"], use_hybrid=False)
                prepared = await rag.prepare(request)
                candidates = module.build_excerpts(prepared.context.citations, case["query"],
                                                  **({"candidates_per_passage": count} if label != "before" else {}))
                for endpoint in ("ask", "stream"):
                    row = {"variant": label, "id": case["id"], "endpoint": endpoint,
                           "offered_facts": sum(any(s == e.text for e in candidates.values())
                                                for s in case["required_sentences"]),
                           "facts": len(case["required_sentences"]),
                           "candidates": {k: e.text for k, e in candidates.items()}}
                    started = time.perf_counter()
                    try:
                        answer = (await rag.ask(request)).answer if endpoint == "ask" else "".join(
                            [c.response async for c in rag.generate_stream(prepared)])
                        row.update(answer=answer, ok=True, abstained=answer == INSUFFICIENT_EVIDENCE_ANSWER,
                                   covered_facts=sum(s in answer for s in case["required_sentences"]))
                    except Exception as exc:
                        row.update(ok=False, error=type(exc).__name__, covered_facts=0)
                    row["seconds"] = time.perf_counter() - started
                    rows.append(row)
                    args.output.write_text(json.dumps(rows, indent=2))
                    print(label, case["id"], endpoint, "ok=", row["ok"], flush=True)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
