"""Measure grammar validity and local request cost at synthetic catalog sizes."""

import argparse
import asyncio
import hashlib
import json
import re
import time
from pathlib import Path

import httpx
from src.services.rag.service import GENERATION_OPTIONS, _selection_pattern


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adversarial", action="store_true")
    args = parser.parse_args()
    rows = []
    out = Path("test_output/selector_reliability/pattern-probe-adversarial.json" if args.adversarial else "test_output/selector_reliability/pattern-probe.json")
    jobs = [(4, value) for value in ("E1 E1", "E99", "E2 E1", "E1 E2 E3 E4")] if args.adversarial else [(n, "E1 E2 E3") for n in (4, 9, 27, 90)]
    async with httpx.AsyncClient(timeout=240) as client:
        for count, requested in jobs:
            pattern = _selection_pattern(count)
            payload = dict(model="llama3.2:1b", stream=False, options=GENERATION_OPTIONS,
                           prompt='Return only the JSON object ' + json.dumps({"answer": requested}) + '. Copy it exactly.',
                           format=dict(type="object", additionalProperties=False, required=["answer"],
                                       properties=dict(answer=dict(type="string", pattern=pattern))))
            start = time.perf_counter()
            response = await client.post("http://localhost:11434/api/generate", json=payload)
            response.raise_for_status()
            result = response.json()
            value = json.loads(result["response"])["answer"]
            valid = isinstance(value, str) and re.fullmatch(pattern, value) is not None
            rows.append(dict(ids=count, requested=requested, valid=valid, pattern_bytes=len(pattern.encode()), seconds=time.perf_counter()-start,
                             payload_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), result=result))
            out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
            print(count, len(pattern), rows[-1]["seconds"], result["response"], flush=True)
            if not valid:
                raise ValueError("Runtime did not enforce the selector grammar")


if __name__ == "__main__":
    asyncio.run(main())
