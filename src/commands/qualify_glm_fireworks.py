"""Qualify GLM-5.3 on Fireworks; default only prints the paid-call plan."""

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from src.commands.build_benchmark import DATA, PRIVATE_QUESTIONS, ROOT, verify_frozen
from src.commands.evaluate_study import PROVIDER_PREFIX, BenchJob, SpendLedger, qualify, worst_call_usd
from src.services.study.models import GLM_FIREWORKS_PROFILE

PAPER = "2410.13258v4"
PROFILE = GLM_FIREWORKS_PROFILE
OUTPUT_ROOT = Path("data/eval/glm-fireworks-qualification")
LEDGER = DATA / "spend.json"
CALL_CEILING = 4
LEDGER_CEILING_USD = 40.0
ROUTER = {
    "checked_on": "2026-11-25",
    "url": "https://router.huggingface.co/v1/models",
    "model": "zai-org/GLM-5.3",
    "provider": "fireworks-ai",
    "status": "live",
    "supports_structured_output": True,
    "price_in_usd_per_m": 0.70,
    "price_out_usd_per_m": 2.20,
}


def plan() -> dict:
    return {
        "execute": False,
        "paper": PAPER,
        "profile": PROFILE.name,
        "route": PROFILE.route,
        "input_estimate": PROFILE.input_estimate,
        "request_options": PROFILE.request_options,
        "call_ceiling": CALL_CEILING,
        "worst_input_tokens_per_call": 21_000,
        "max_output_tokens_per_call": 3_000,
        "worst_case_usd_per_call": worst_call_usd(PROFILE),
        "worst_case_usd": CALL_CEILING * worst_call_usd(PROFILE),
        "ledger": str(LEDGER),
        "ledger_spent_usd": SpendLedger(LEDGER).spent(),
        "ledger_ceiling_usd": LEDGER_CEILING_USD,
        "output_root": str(OUTPUT_ROOT),
        "router": ROUTER,
    }


def _error_rows(*, rows: list[dict], errors: list[dict]) -> list[dict]:
    pending = list(errors)
    numbered = []
    call_number = 0
    for row in rows:
        for call in row["calls"]:
            call_number += 1
            failure = row.get("failure_code") or ""
            if not failure.startswith(PROVIDER_PREFIX) or call["state"] != "failed":
                continue
            status = failure.removeprefix(PROVIDER_PREFIX)
            error = pending.pop(0) if pending else {}
            numbered.append({"call": call_number, "http_status": int(status) if status.isdigit() else None, **error})
    return numbered


def _job_report(*, paper: str, job_root: Path, rows: list[dict], errors: list[dict]) -> dict:
    calls = [call for row in rows for call in row["calls"]]
    last = rows[-1] if rows else {}
    review = last.get("review") or {}
    provider_errors = _error_rows(rows=rows, errors=errors)
    return {
        "paper": paper,
        "job_root": str(job_root),
        "status": last.get("status"),
        "failure_code": last.get("failure_code"),
        "diagnostic": last.get("diagnostic"),
        "format": {
            "parseable_calls": sum(call["state"] == "succeeded" for call in calls),
            "total_calls": len(calls),
        },
        "kept_claims": review.get("kept"),
        "review": review,
        "latency_seconds": last.get("seconds"),
        "cost_usd": sum(call["cost_usd"] for call in calls),
        "calls": calls,
        "provider_errors": provider_errors,
    }


def _qualification_rows(root: Path) -> list[dict]:
    rows: list[dict] = []
    for stage in ("qualify", "qualify-plain", "qualify-thinking-off"):
        path = root / f"{stage}-{PROFILE.name}" / "jobs.jsonl"
        if path.exists():
            rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return rows


@asynccontextmanager
async def services(store, profile, audit, observer, *, errors: list[dict]):
    import httpx
    from src.commands.evaluate_study import ManifestIntake
    from src.commands.study_research import ResearchSettings
    from src.services.study.content import PaperContentService
    from src.services.study.service import StudyService
    from src.services.study.tutor import StudyModel

    settings = ResearchSettings()
    model = StudyModel(settings.hf_token, store, audit=audit, profile=profile, error_observer=errors.append)
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=30,
                                 headers={"User-Agent": "ScholarLens-benchmark/0.1"}) as public:
        service = StudyService(store, ManifestIntake(DATA / "content"), PaperContentService(DATA / "sources", public),
                               model, observer=observer)
        try:
            yield service
        finally:
            await service.aclose()
            await model.aclose()


async def execute(service_factory=services) -> int:
    # This command never reads the benchmark questions and never writes its frozen files or stores.
    verify_frozen(ROOT, PRIVATE_QUESTIONS)
    papers = json.loads((ROOT / "papers.v1.json").read_text(encoding="utf-8"))["papers"]
    entry = next((row for row in papers if row["id"] == PAPER and row["split"] == "dev"), None)
    if entry is None:
        raise SystemExit("refused: the qualification paper is not the frozen dev paper")
    ledger = SpendLedger(LEDGER, ceiling_usd=LEDGER_CEILING_USD)
    if not ledger.allows(CALL_CEILING * worst_call_usd(PROFILE)):
        raise SystemExit("refused: the shared ledger cannot fund the entire four-call worst case")
    errors: list[dict] = []

    @asynccontextmanager
    async def observed_services(store, profile, audit, observer):
        async with service_factory(store, profile, audit, observer, errors=errors) as service:
            yield service

    result = await qualify(PROFILE, BenchJob(PAPER, "L", PAPER), root=OUTPUT_ROOT,
                           service_factory=observed_services, ledger=ledger,
                           expected_sha={PAPER: entry["sha256"]})
    report = {
        "qualification": result,
        "profile": PROFILE.name,
        "route": PROFILE.route,
        "router": ROUTER,
        "job": _job_report(paper=PAPER, job_root=OUTPUT_ROOT, rows=_qualification_rows(OUTPUT_ROOT), errors=errors),
        "ledger_spent_usd": ledger.spent(),
        "ledger_ceiling_usd": ledger.ceiling_usd,
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "qualification-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="make the separately owner-approved paid calls")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(plan(), indent=2))
        return 0
    return asyncio.run(execute())


if __name__ == "__main__":
    raise SystemExit(main())
