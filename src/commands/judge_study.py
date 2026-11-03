"""RAGAS judging for the paper benchmark. Run from .venv-eval; default performs no work.

`ragas` is imported only inside build_metrics, so the bot and the main test suite never load it.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from src.commands.build_benchmark import DATA, PRIVATE_PAPER, ROOT, base_id, write_json
from src.services.study.models import ModelProfile, call_cost_usd

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


WORST_JUDGE_INPUT = 21_000
JUDGE_MAX_TOKENS = 3000


def worst_judge_usd(profile: ModelProfile) -> float:
    return call_cost_usd(profile, None, estimate=WORST_JUDGE_INPUT, max_tokens=JUDGE_MAX_TOKENS)


class JudgeMeter:
    """httpx hooks: every judge call counts against the same $40 ledger as the runner, and against a
    call ceiling that survives restarts. A call the ledger cannot afford at its worst case is never sent."""

    def __init__(self, profile: ModelProfile, ledger, *, ceiling: int, state: Path):
        self.profile, self.ledger, self.ceiling, self.state = profile, ledger, ceiling, state

    def calls(self) -> int:
        return json.loads(self.state.read_text(encoding="utf-8"))["calls"] if self.state.exists() else 0

    async def on_request(self, request) -> None:
        if self.calls() >= self.ceiling:
            raise RuntimeError("judge_call_ceiling")
        if not self.ledger.allows(worst_judge_usd(self.profile)):
            raise RuntimeError("judge_price_ceiling")
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self.state.write_text(json.dumps({"calls": self.calls() + 1}), encoding="utf-8")

    async def on_response(self, response) -> None:
        await response.aread()
        try:
            usage = response.json().get("usage")
            usage = usage if type(usage) is dict and {"prompt_tokens", "completion_tokens"} <= set(usage) else None
        except ValueError:
            usage = None
        # No usage means the worst case is charged, never zero.
        self.ledger.charge(call_cost_usd(self.profile, usage, estimate=WORST_JUDGE_INPUT, max_tokens=JUDGE_MAX_TOKENS))

    def hooks(self) -> dict:
        return {"request": [self.on_request], "response": [self.on_response]}


def judge_client(token: str, meter: JudgeMeter):
    import httpx
    from openai import AsyncOpenAI

    # No client retries: each retry would be a paid call the protocol does not allow.
    return AsyncOpenAI(api_key=token, base_url="https://router.huggingface.co/v1", max_retries=0,
                       http_client=httpx.AsyncClient(event_hooks=meter.hooks(), timeout=120))  # type: ignore[arg-type]


async def judge_into(rows: list[dict], metrics: dict[str, Metric], output: Path) -> None:
    """Append each judged row as it finishes; rows already judged are skipped, so a rerun never pays twice."""
    done = set()
    if output.exists():
        done = {(row["model"], row["paper"], row["job"]) for row in map(json.loads, output.read_text(encoding="utf-8").splitlines()) if row}
    for row in rows:
        if (row["model"], row["paper"], row["job"]) in done:
            continue
        scored = (await score_rows([row], metrics))[0]
        with output.open("a", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(scored, ensure_ascii=False) + chr(10))


def check_calibration(rows: list[dict]) -> None:
    # Calibration is committed and published; the unpublished paper's text must never enter it.
    for row in rows:
        if base_id(row.get("paper", "")) == PRIVATE_PAPER:
            raise ValueError("private_paper")
        if not row.get("paper"):
            raise ValueError("paper_required")


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
        rows.append({"id": case["id"], "paper": cases["source"]["paper_id"], "claim_ar": claim, "quote_en": quote,
                     "owner_faithful": None})
    return rows


def build_metrics(profile, token: str, meter: JudgeMeter) -> dict[str, Metric]:  # pragma: no cover - needs .venv-eval
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextRecall, FactualCorrectness, Faithfulness

    llm = llm_factory(profile.route, client=judge_client(token, meter), temperature=0, max_tokens=JUDGE_MAX_TOKENS)
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
    from src.commands.evaluate_study import SpendLedger
    from src.commands.study_research import ResearchSettings
    from src.services.study.models import load_profiles

    profiles = load_profiles(ROOT / "models.v1.json")
    judge = profiles[json.loads((ROOT / "models.v1.json").read_text(encoding="utf-8"))["judge"]]
    meter = JudgeMeter(judge, SpendLedger(DATA / "spend.json"), ceiling=CEILINGS[args.command],
                       state=DATA / f"judge-calls-{args.command}.json")
    metrics = build_metrics(judge, ResearchSettings().hf_token.get_secret_value(), meter)
    if args.command == "calibrate":
        rows = json.loads(CALIBRATION.read_text(encoding="utf-8"))["rows"]
        check_calibration(rows)
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
    asyncio.run(judge_into(rows, metrics, DATA / "judged.jsonl"))
    print("judged", len(rows), "answers;", meter.calls(), "judge calls so far; spent $%.2f" % meter.ledger.spent())
    return 0


if __name__ == "__main__":
    sys.exit(main())
