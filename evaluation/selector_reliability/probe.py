"""Read-only exact-payload replay and preservation capture for selector diagnosis."""

import argparse
import asyncio
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import httpx
from src.commands.evaluate_retrieval import snapshot
from src.schemas.api.rag import AskRequest, Citation
from src.services.rag.context import RAGContext
from src.services.rag.service import GENERATION_OPTIONS, SYSTEM_PROMPT_PATH, PreparedRAG, RAGService

OUT = Path("test_output/selector_reliability")


def capture():
    OUT.mkdir(parents=True, exist_ok=True)
    paths = [p for root in ("src", "tests", "evaluation") for p in Path(root).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths += [Path(p) for p in ("README.md", "TESTING.md", ".env.example", ".env.test", "SESSION_HANDOFF.md")]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with httpx.Client(timeout=30) as client:
        state, papers, chunks = snapshot(client, "http://localhost:8000/api/v1", "http://localhost:9200")
        models = client.get("http://localhost:11434/api/tags").json()
        version = client.get("http://localhost:11434/api/version").json()
    (OUT / "initial.json").write_text(json.dumps(dict(hashes=hashes, state=state, models=models, version=version), indent=2))
    (OUT / "corpus.json").write_text(json.dumps(dict(papers=papers, chunks=chunks)))
    print(state, version)


async def replay(batch, variant):
    records = [json.loads(s) for s in Path("test_output/quality_fixes/regression/records.jsonl").read_text(encoding="utf-8").splitlines()]
    cases = json.loads(Path("evaluation/quality_fixes/regression.json").read_text(encoding="utf-8"))["cases"]
    module = sys.modules[RAGService.__module__]
    if variant == "legacy":
        spec = importlib.util.spec_from_file_location("replay_baseline", OUT / "service_baseline.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    rows = []
    async with httpx.AsyncClient(timeout=240) as client:
        for case_id in ("ave-1",):
            matched = [r for r in records if r["case_id"] == case_id and r["requested_mode"] == "hybrid" and r["endpoint"] in ("ask", "stream") and r["ok"]]
            if not matched:
                continue
            case = next(c for c in cases if c["id"] == case_id)
            prepared = []
            for record in matched:
                response = record["response"]
                prepared.append(PreparedRAG(AskRequest(query=case["query"]), RAGContext(sources=response["sources"], citations=[Citation.model_validate(c) for c in response["citations"]], prompt_context=""), "hybrid", response["model"]))
            schema = (json.loads((OUT / "payload-ave-1-batch0.json").read_text())["format"] if variant == "legacy" else RAGService._selection_schema(prepared[0]))
            payloads = [dict(model=p.model, prompt=module.RAGService._prompt(p, structured=True), system=SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip(), format=schema, options={**GENERATION_OPTIONS, **({"num_batch": batch} if batch else {})}, stream=False) for p in prepared]
            payload = payloads[0]
            (OUT / f"payload-utf8-{variant}-{case_id}-batch{batch}.json").write_text(json.dumps(payload, indent=2))
            for i in range(6):
                # Alternate a distinct short prompt with identical repetitions.
                if i in (0, 3):
                    await client.post("http://localhost:11434/api/generate", json=dict(model=prepared[0].model, prompt="Return the word READY.", stream=False, options=payload["options"]))
                start = time.perf_counter()
                response = await client.post("http://localhost:11434/api/generate", json=payload)
                response.raise_for_status()
                row = dict(case=case_id, iteration=i, batch=batch, endpoint_payloads_equal=all(p == payload for p in payloads), payload_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), seconds=time.perf_counter()-start, result=response.json())
                rows.append(row)
                (OUT / f"replay-utf8-{variant}-batch{batch}.json").write_text(json.dumps(rows, indent=2))
                print(case_id, batch, i, row["result"]["response"], round(row["seconds"], 2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--batch", type=int, default=0)
    parser.add_argument("--variant", choices=("legacy", "map", "string"), default="legacy")
    args = parser.parse_args()
    if args.capture:
        capture()
    else:
        asyncio.run(replay(args.batch, args.variant))
