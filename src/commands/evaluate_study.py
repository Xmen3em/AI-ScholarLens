"""Run one paper-benchmark stage for one model. Default performs no work and opens no client."""

import argparse
import asyncio
import json
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Literal

import httpx
from src.commands.build_benchmark import DATA, PRIVATE_QUESTIONS, ROOT, load_questions, verify_frozen
from src.resources import free_memory_mib as host_memory_mib
from src.services.study.models import ModelProfile, call_cost_usd, load_profiles
from src.services.study.store import StoreConflict, StudyStore

STAGE_CEILINGS = {"qualify": 4, "dev": 96, "dev-rerun": 96, "holdout": 144}
WORST_INPUT_TOKENS = 20_000
CALLS_PER_JOB = 2
MIN_MEMORY_MIB = 1024
OWNER = "paper-benchmark"
# Rejections of a request field, which qualification retries once without options.
OPTION_REJECTED = {"study_provider_http_400", "study_provider_http_422"}
FORMAT_FAILURES = {"study_response_invalid_or_unavailable", "review_validation_failed"}
PROVIDER_PREFIX = "study_provider_http_"


@dataclass(frozen=True)
class BenchJob:
    paper: str
    kind: Literal["L", "Q1", "Q2", "Q3"]
    text: str


def plan_jobs(papers: dict, questions: dict, split: str) -> list[BenchJob]:
    jobs = []
    for paper in papers["papers"]:
        if paper["split"] != split:
            continue
        entry = questions["papers"][paper["id"]]
        jobs.append(BenchJob(paper["id"], "L", paper["id"]))
        jobs += [BenchJob(paper["id"], "Q1", entry["Q1"]["text"]), BenchJob(paper["id"], "Q2", entry["Q2"]["text"]),
                 BenchJob(paper["id"], "Q3", entry["Q3"]["text"])]
    return jobs


class ManifestIntake:
    """Resolve benchmark papers from their frozen parsed content; runs never call the arXiv API."""

    def __init__(self, root: Path):
        self.root = root

    async def resolve(self, value: str) -> list:
        from src.services.study.content import PaperContent
        from src.services.study.intake import StudyInputError

        path = self.root / (value.strip() + ".json")
        if not path.exists():
            raise StudyInputError("invalid_paper_input")
        return [PaperContent.model_validate_json(path.read_text(encoding="utf-8")).paper]


def worst_call_usd(profile: ModelProfile) -> float:
    return call_cost_usd(profile, None, estimate=WORST_INPUT_TOKENS)


class SpendLedger:
    """Dollars charged across every stage; refuses a job whose worst case would pass the ceiling."""

    def __init__(self, path: Path, ceiling_usd: float = 40.0):
        self.path, self.ceiling_usd = path, ceiling_usd

    def spent(self) -> float:
        if not self.path.exists():
            return 0.0
        return float(json.loads(self.path.read_text(encoding="utf-8"))["spent_usd"])

    def charge(self, usd: float) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"spent_usd": self.spent() + usd}), encoding="utf-8")

    def allows(self, next_max_usd: float) -> bool:
        return self.spent() + next_max_usd <= self.ceiling_usd


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + chr(10))


def _row(job: BenchJob, status: str, **fields) -> dict:
    base: dict = {"paper": job.paper, "job": job.kind, "status": status, "failure_code": None, "diagnostic": None,
            "stage": None, "review": None, "seconds": None, "calls": [], "lesson": None, "contexts": [],
            "question": job.text}
    return {**base, **fields}


async def run_stage(stage: str, profile: ModelProfile, jobs: list[BenchJob], *, root: Path, service_factory,
                    ledger: SpendLedger, call_ceiling: int, expected_sha: dict[str, str],
                    memory=host_memory_mib, clock=time.monotonic) -> list[dict]:
    if memory() < MIN_MEMORY_MIB:
        raise RuntimeError("insufficient_memory")
    folder = root / f"{stage}-{profile.name}"
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / "jobs.jsonl"
    done = {(row["paper"], row["job"]) for row in _rows(output)}
    store = StudyStore(folder / "state.sqlite3", OWNER)
    store.recover_interrupted()
    usages: list[dict] = []
    seen: dict = {}

    def audit(record: dict) -> None:
        usages.append(record["result"]["usage"])

    def observer(job_id: str, lesson, catalog: list[dict]) -> None:
        seen.update(job_id=job_id, lesson=lesson.model_dump(mode="json"), contexts=[item["quote"] for item in catalog])

    worst = worst_call_usd(profile)
    stopped = False
    lessons: dict[str, str] = {row["paper"]: row["status"] for row in _rows(output) if row["job"] == "L"}
    async with service_factory(store, profile, audit, observer) as service:
        for job in jobs:
            if (job.paper, job.kind) in done:
                continue
            if job.kind != "L" and lessons.get(job.paper) != "ready":
                _append(output, _row(job, "blocked"))
                continue
            if stopped or store.total_attempts() + CALLS_PER_JOB > call_ceiling or not ledger.allows(CALLS_PER_JOB * worst):
                stopped = True
                _append(output, _row(job, "stopped"))
                continue
            usages.clear()
            seen.clear()
            started = clock()
            try:
                submitted = service.submit(f"bench:{stage}:{job.paper}:{job.kind}", job.text)
            except StoreConflict as exc:
                submitted = {"reply": str(exc)}
            if service.tasks:
                await asyncio.gather(*service.tasks, return_exceptions=True)
            seconds = round(clock() - started, 3)
            stored = store.get_job(submitted["job_id"]) if submitted.get("job_id") else None
            if stored is None:
                row = _row(job, "failed", failure_code="not_submitted", seconds=seconds)
            else:
                result = stored["result"] or {}
                status = {"ready": "ready", "failed": "failed"}.get(stored["status"], "unknown")
                calls, pending = [], list(usages)
                for attempt in store.attempts(stored["id"]):
                    usage = pending.pop(0) if attempt["state"] == "succeeded" and pending else None
                    cost = call_cost_usd(profile, usage, estimate=WORST_INPUT_TOKENS)
                    ledger.charge(cost)
                    calls.append({"purpose": attempt["purpose"], "state": attempt["state"], "usage": usage, "cost_usd": cost})
                row = _row(job, status, failure_code=result.get("failure_code"), diagnostic=result.get("diagnostic"),
                           stage=result.get("stage"), review=result.get("review"), seconds=seconds, calls=calls,
                           lesson=seen.get("lesson") if seen.get("job_id") == stored["id"] else None,
                           contexts=seen.get("contexts", []) if seen.get("job_id") == stored["id"] else [])
                if job.kind == "L" and status == "ready":
                    saved = store.paper(job.paper)
                    sha = saved["content"]["source_sha256"] if saved else None
                    if sha != expected_sha.get(job.paper):
                        row.update(status="failed", failure_code="source_changed")
            if job.kind == "L":
                lessons[job.paper] = row["status"]
            _append(output, row)
    return _rows(output)


def _qualified(row: dict) -> bool:
    # The schema was honoured if both calls produced parseable output; a withheld lesson still counts.
    return row["status"] == "ready" or row["failure_code"] == "lesson_validation_failed"


async def qualify(profile: ModelProfile, job: BenchJob, *, root: Path, service_factory, ledger: SpendLedger,
                  expected_sha: dict[str, str], memory=host_memory_mib) -> dict:
    ceiling = STAGE_CEILINGS["qualify"]
    rows = await run_stage("qualify", profile, [job], root=root, service_factory=service_factory, ledger=ledger,
                           call_ceiling=ceiling, expected_sha=expected_sha, memory=memory)
    row, options = rows[0], profile.request_options
    if row["failure_code"] in OPTION_REJECTED and profile.request_options:
        plain = replace(profile, request_options={})
        used = len(row["calls"])
        rows = await run_stage("qualify-plain", plain, [job], root=root, service_factory=service_factory,
                               ledger=ledger, call_ceiling=ceiling - used, expected_sha=expected_sha, memory=memory)
        row, options = rows[0], {}
    result = {"model": profile.name, "passed": _qualified(row), "request_options": options}
    path = root / "qualification.json"
    recorded = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    recorded[profile.name] = result
    path.write_text(json.dumps(recorded, indent=2), encoding="utf-8")
    return result


@asynccontextmanager
async def production_services(store, profile, audit, observer):
    from src.commands.study_research import ResearchSettings
    from src.services.study.content import PaperContentService
    from src.services.study.service import StudyService
    from src.services.study.tutor import StudyModel

    settings = ResearchSettings()
    model = StudyModel(settings.hf_token, store, audit=audit, profile=profile)
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=30,
                                 headers={"User-Agent": "ScholarLens-benchmark/0.1"}) as public:
        service = StudyService(store, ManifestIntake(DATA / "content"), PaperContentService(DATA / "sources", public), model,
                               observer=observer)
        try:
            yield service
        finally:
            await service.aclose()
            await model.aclose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=sorted(STAGE_CEILINGS), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--close-dev", action="store_true", help="record that development is closed")
    args = parser.parse_args(argv)
    profiles = load_profiles(ROOT / "models.v1.json")
    if args.model not in profiles or args.model == "judge":
        raise SystemExit("unknown model profile: " + args.model)
    profile = profiles[args.model]
    ceiling = STAGE_CEILINGS[args.stage]
    if not args.execute and not args.close_dev:
        print(f"stage {args.stage}, model {profile.route}: call ceiling {ceiling}, worst case "
              f"${ceiling * worst_call_usd(profile):.2f}, price ceiling $40 across stages. Re-run with --execute.")
        return 0
    try:
        digest = verify_frozen(ROOT, PRIVATE_QUESTIONS)
    except ValueError as exc:
        raise SystemExit("refused: " + str(exc)) from None
    if args.close_dev:
        (DATA / "dev-closed.json").write_text(json.dumps({"closed_on": date.today().isoformat(),
                                                          "manifest_sha256": digest}), encoding="utf-8")
        print("development closed")
        return 0
    if args.stage == "holdout":
        if not (DATA / "dev-closed.json").exists():
            raise SystemExit("refused: development is not closed (--close-dev)")
        # Holdout must run on exactly the files development closed with.
        if json.loads((DATA / "dev-closed.json").read_text(encoding="utf-8"))["manifest_sha256"] != digest:
            raise SystemExit("refused: the frozen manifest changed after development closed")
    if args.stage == "qualify" and args.model == "baseline":
        raise SystemExit("refused: the baseline needs no qualification")
    if args.stage != "qualify" and args.model != "baseline":
        path = DATA / "qualification.json"
        recorded = json.loads(path.read_text(encoding="utf-8")).get(args.model) if path.exists() else None
        if not recorded or not recorded["passed"]:
            raise SystemExit("refused: " + args.model + " has not passed qualification")
        profile = replace(profile, request_options=recorded["request_options"])
    papers = json.loads((ROOT / "papers.v1.json").read_text(encoding="utf-8"))
    expected = {row["id"]: row["sha256"] for row in papers["papers"]}
    ledger = SpendLedger(DATA / "spend.json")
    split = "holdout" if args.stage == "holdout" else "dev"
    jobs = plan_jobs(papers, load_questions(), split)
    if args.stage == "qualify":
        print(asyncio.run(qualify(profile, jobs[0], root=DATA, service_factory=production_services, ledger=ledger,
                                  expected_sha=expected)))
        return 0
    rows = asyncio.run(run_stage(args.stage, profile, jobs, root=DATA, service_factory=production_services,
                                 ledger=ledger, call_ceiling=ceiling, expected_sha=expected))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print(json.dumps({"rows": len(rows), "statuses": counts, "spent_usd": round(ledger.spent(), 4)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
