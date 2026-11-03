"""RAGAS judging for the paper benchmark. Run from .venv-eval; default performs no work.

`ragas` is imported only inside build_metrics, so the bot and the main test suite never load it.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from src.commands.build_benchmark import DATA, ROOT, write_json

SCIENCE_CASES = Path("evaluation/paper_learning/science-cases.v1.json")
CALIBRATION = ROOT / "calibration.v1.json"
GATE_AGREEMENT, GATE_KAPPA = 0.85, 0.6
CEILINGS = {"calibrate": 80, "judge": 864}
Metric = Callable[[dict], Awaitable[float]]


async def score_rows(rows: list[dict], metrics: dict[str, Metric]) -> list[dict]:
    scored = []
    for row in rows:
        result = {**row, "faithfulness": await metrics["faithfulness"](row)}
        if row["reference"]:
            result["factual_correctness"] = await metrics["factual_correctness"](row)
            result["context_recall"] = await metrics["context_recall"](row)
        scored.append(result)
    return scored


def agreement(owner: list[bool], judge: list[bool]) -> dict:
    if len(owner) != len(judge) or not owner:
        raise ValueError("labels_mismatch")
    n = len(owner)
    observed = sum(a == b for a, b in zip(owner, judge, strict=True)) / n
    yes_owner, yes_judge = sum(owner) / n, sum(judge) / n
    expected = yes_owner * yes_judge + (1 - yes_owner) * (1 - yes_judge)
    kappa = 1.0 if expected == 1 else (observed - expected) / (1 - expected)
    return {"agreement": observed, "kappa": kappa, "n": n}


def calibrated(result: dict) -> bool:
    return result["agreement"] >= GATE_AGREEMENT and result["kappa"] >= GATE_KAPPA


class CallCounter:
    """httpx request hook: the judge stops at its ceiling instead of spending past it."""

    def __init__(self, ceiling: int):
        self.ceiling, self.count = ceiling, 0

    async def __call__(self, request) -> None:
        self.count += 1
        if self.count > self.ceiling:
            raise RuntimeError("judge_call_ceiling")


def calibration_rows() -> list[dict]:
    from src.services.study.content import EvidenceBlock
    from src.services.study.evidence import evidence_catalog

    cases = json.loads(SCIENCE_CASES.read_text(encoding="utf-8"))
    truth = json.loads(Path(cases["truth_source"]["fixture"]).read_text(encoding="utf-8"))
    evidence = {item["id"]: item for item in truth["evidence"]}
    blocks = []
    for locator in cases["locators"]:
        text = (" … ".join(evidence[i]["quote"] for i in locator["evidence_ids"])
                if locator["construction"] == "reviewed_excerpts" else locator["text"])
        blocks.append(EvidenceBlock(id=locator["block_id"], page=locator["page"], section=locator["section"], text=text))
    quotes = {item["id"]: item["quote"] for item in evidence_catalog(blocks)}
    everything = " ".join(block.text for block in blocks)
    rows = []
    for case in cases["cases"]:
        claims = case["section"]["claims"]
        claim = claims[0]["text"] if claims else case["section"]["text"]
        # A claim without a citation (or an analogy) is judged against all reviewed excerpts.
        quote = quotes.get(claims[0]["evidence_id"], everything) if claims else everything
        rows.append({"id": case["id"], "claim_ar": claim, "quote_en": quote, "owner_faithful": None})
    return rows


def build_metrics(profile, token: str, counter: CallCounter) -> dict[str, Metric]:  # pragma: no cover - needs .venv-eval
    import httpx
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextRecall, FactualCorrectness, Faithfulness

    client = AsyncOpenAI(api_key=token, base_url="https://router.huggingface.co/v1",
                         http_client=httpx.AsyncClient(event_hooks={"request": [counter]}, timeout=120))  # type: ignore[arg-type]
    llm = llm_factory(profile.route, client=client, temperature=0, max_tokens=3000)
    faithfulness, factual, recall = Faithfulness(llm=llm), FactualCorrectness(llm=llm, mode="recall"), ContextRecall(llm=llm)

    async def faithful(row: dict) -> float:
        result = await faithfulness.ascore(user_input=row["question"], response=row["answer"],
                                           retrieved_contexts=row["contexts"])
        return float(result.value)

    async def correct(row: dict) -> float:
        return float((await factual.ascore(response=row["answer"], reference=row["reference"])).value)

    async def recalled(row: dict) -> float:
        result = await recall.ascore(user_input=row["question"], retrieved_contexts=row["contexts"],
                                     reference=row["reference"])
        return float(result.value)

    return {"faithfulness": faithful, "factual_correctness": correct, "context_recall": recalled}


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wiring, needs .venv-eval to execute
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["calibration-sheet", "calibrate", "judge"])
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "calibration-sheet":
        if CALIBRATION.exists():
            raise SystemExit("calibration.v1.json exists; the owner's labels are never overwritten")
        write_json(CALIBRATION, {"version": "paper-benchmark-calibration-v1", "rows": calibration_rows()})
        print("wrote", CALIBRATION, "- the owner adds 24 development claims and labels all 40")
        return 0
    if not args.execute:
        print(f"{args.command}: up to {CEILINGS[args.command]} judge calls. Re-run with --execute.")
        return 0
    from src.commands.study_research import ResearchSettings
    from src.services.study.models import load_profiles

    profiles = load_profiles(ROOT / "models.v1.json")
    judge = profiles[json.loads((ROOT / "models.v1.json").read_text(encoding="utf-8"))["judge"]]
    counter = CallCounter(CEILINGS[args.command])
    metrics = build_metrics(judge, ResearchSettings().hf_token.get_secret_value(), counter)
    if args.command == "calibrate":
        rows = json.loads(CALIBRATION.read_text(encoding="utf-8"))["rows"]
        if len(rows) != 40 or any(row["owner_faithful"] is None for row in rows):
            raise SystemExit("calibration needs 40 rows, all labelled by the owner")
        verdicts = asyncio.run(score_rows([{"question": "", "answer": row["claim_ar"], "contexts": [row["quote_en"]],
                                            "reference": None} for row in rows], metrics))
        result = agreement([row["owner_faithful"] for row in rows], [item["faithfulness"] >= 0.5 for item in verdicts])
        result["calibrated"] = calibrated(result)
        write_json(DATA / "calibration-result.json", result)
        print(json.dumps(result))
        return 0
    rows = [json.loads(line) for line in (DATA / "ragas-input.jsonl").read_text(encoding="utf-8").splitlines() if line]
    scored = asyncio.run(score_rows(rows, metrics))
    with (DATA / "judged.jsonl").open("w", encoding="utf-8", newline="") as handle:
        for row in scored:
            handle.write(json.dumps(row, ensure_ascii=False) + chr(10))
    print("judged", len(scored), "answers in", counter.count, "calls")
    return 0


if __name__ == "__main__":
    sys.exit(main())
