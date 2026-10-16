"""Hosted review bindings, unchanged semantic scoring and pre-holdout locks."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from src.commands.agent_collection import build_jobs
from src.commands.evaluate_agent import load_labels, write_json
from src.commands.evaluate_hf_agent import source_hashes, validate_selection
from src.commands.evaluate_retrieval import digest
from src.commands.hf_allowance import validate_pilot_scope
from src.commands.hf_evaluation import HF_MANIFEST_SHA256, hosted_work, load_protocol, qualification_cases
from src.commands.hf_paper_allowance import validate_task_accounting
from src.commands.hf_paper_profile import PAPER_PROFILES, get_profile
from src.commands.hf_qualification import load_revision
from src.commands.score_agent import make_review_template, score_records


def scoring_profile(name=None) -> tuple[dict, str]:
    return (load_protocol(), HF_MANIFEST_SHA256) if name in {None, "hosted-agent-v1"} else get_profile(name)


def hosted_review_template(records: list, cases: list, model: str, *, fixture_manifest_sha256=None, profile_name=None) -> dict:
    _, manifest_sha = scoring_profile(profile_name)
    binding = {"fixture_manifest_sha256": fixture_manifest_sha256} if fixture_manifest_sha256 else {}
    return {**make_review_template(records, cases), "hosted_manifest_sha256": manifest_sha,
            **binding, "model": model, "records_sha256": digest(records)}


def hosted_gates(records, original, qualification, completion, profile, model, *, split, planned_count):
    gates = [gate for gate in original["gate_failures"] if split != "development" or gate != "holdout_matrix_incomplete"]
    expected_count = profile["holdout_jobs"] if split == "holdout" else profile["development_jobs"]
    if not original["collection_complete"] or planned_count != expected_count or len(records) != expected_count:
        gates.append("hosted_matrix_incomplete")
    expected_preservation = {"corpus_unchanged", "models_unchanged", "source_unchanged", "frozen_labels_unchanged"}
    preserved = completion.get("preservation") or {}
    if completion.get("status") != "collected" or set(preserved) != expected_preservation or any(value is not True for value in preserved.values()):
        gates.append("hosted_preservation_incomplete")
    checks = qualification.get("checks") or []
    if (qualification.get("qualified") is not True or qualification.get("large_schema_preflight_rejected") is not True
            or len(checks) != profile["qualification_calls"] or any(check.get("ok") is not True for check in checks)
            or any(len(check.get("calls", [])) != 1 or check["calls"][0].get("outbound_attempts") != 1 for check in checks)):
        gates.append("hosted_qualification_failed")
    outbound = 0
    for item in [*checks, *records]:
        calls = item.get("calls", item.get("hf_calls", []))
        work = hosted_work(calls, profile, model)
        if work != item.get("work", item.get("hosted")):
            raise ValueError("Saved hosted work differs from ledger")
        if "measured" in item and len(calls) != item["measured"].get("generation_calls", 0):
            raise ValueError("Saved hosted generation count differs")
        outbound += work["outbound_attempts"]
        if not work["usage_complete"]:
            gates.append("hosted_usage_incomplete")
        if work["schema_violations"]:
            gates.append("hosted_schema_violation")
        if "minimum_free_mib" in item and (item["minimum_free_mib"] is None or item["minimum_free_mib"] < profile["live_margin_mib"]):
            gates.append("hosted_qualification_resource_failed")
    budget = profile["qualification_calls"] + sum(6 if record.get("path") == "agent" else 2 for record in records)
    if outbound > min(budget, profile["maximum_outbound_attempts"]):
        gates.append("hosted_outbound_budget_breach")
    if completion.get("outbound_attempts") != outbound:
        gates.append("hosted_attempt_accounting_incomplete")
    for name, cell in original["cells"].items():
        maximum = profile["agent_p95_ms"] if name.startswith("agent:") else profile["baseline_p95_ms"]
        if cell["latency"]["p95_ms"] > maximum:
            gates.append("hosted_latency_target_failed")
    return sorted(set(gates))


def score_run(run: Path, source: Path, reviews: dict, *, profile_name=None) -> dict:
    read = lambda name: json.loads((run / name).read_text(encoding="utf-8"))
    profile, manifest_sha = scoring_profile(profile_name)
    metadata = read("metadata.json")
    cerebras = profile["version"] in PAPER_PROFILES
    if metadata.get("hosted_manifest_sha256") != manifest_sha or metadata.get("inference_started") is not True:
        raise ValueError("Run lacks hosted inference evidence")
    model, split = metadata["configuration"]["model"], metadata["split"]
    if model not in profile["model_pairs"]:
        raise ValueError("Unregistered scored pair")
    _, labels, papers, chunks = load_labels(Path("evaluation/week7_agent"), source)
    records = [json.loads(line) for line in (run / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if (reviews.get("hosted_manifest_sha256") != manifest_sha or reviews.get("model") != model
            or reviews.get("records_sha256") != digest(records)):
        raise ValueError("Hosted review binding differs")
    planned = [job["key"] for job in metadata["jobs"]]
    if [record["key"] for record in records] != planned[:len(records)]:
        raise ValueError("Hosted collection order differs")
    cases = labels[split]["cases"]
    original = score_records(records, cases, reviews, papers, chunks, planned_keys=planned, split=split, expected_model=model)
    qualification, completion = read("qualification.json"), read("completion.json")
    fixture_sha = metadata.get("fixture_manifest_sha256")
    revision = load_revision() if fixture_sha else None
    if (qualification.get("fixture_manifest_sha256") != fixture_sha or reviews.get("fixture_manifest_sha256") != fixture_sha
            or revision and revision["manifest_sha256"] != fixture_sha or cerebras and revision is None):
        raise ValueError("Qualification/review revision binding differs")
    gates = hosted_gates(records, original, qualification, completion, profile, model, split=split, planned_count=len(planned))
    funding_binding = None
    if cerebras:
        budget = 261 if split == "development" else 773
        if (metadata.get("configuration", {}).get("policy") != profile["version"]
                or any(type(metadata.get(key)) is not int or metadata[key] != budget
                       for key in ("planned_outbound_budget", "approved_outbound_budget", "outbound_budget"))
                or metadata.get("source_snapshot_sha256") != hashlib.sha256((source / "state.json").read_bytes()).hexdigest()):
            gates.append("cerebras_scope_changed")
        try:
            funding_binding = validate_task_accounting(metadata, run, completion)
        except (ValueError, OSError, sqlite3.Error):
            gates.append("cerebras_allowance_incomplete")
        if split == "holdout":
            try:
                selection = metadata.get("selection_lock", {})
                if metadata.get("selection_sha256") != digest(selection):
                    raise ValueError("Selection binding differs")
                validate_selection(selection, model, source, profile_name=profile["version"])
            except (ValueError, OSError, KeyError, sqlite3.Error):
                gates.append("cerebras_development_lock_incomplete")
    elif revision:
        try:
            validate_pilot_scope(metadata)
        except ValueError:
            gates.append("hosted_pilot_scope_changed")
        allowance = metadata.get("allowance", {})
        budget = metadata.get("outbound_budget")
        if (type(budget) is not int or not 1 <= budget <= 11 or allowance.get("reserved_for_run") != budget
                or completion.get("outbound_attempts", 12) > budget):
            gates.append("hosted_pilot_allowance_incomplete")
    for check, expected in zip(qualification.get("checks", []), revision["cases"] if revision else qualification_cases()):
        limit = profile["selector_output_limit"] if expected["id"].startswith("selector") else profile["controller_output_limit"]
        if (check.get("id") != expected["id"] or check.get("schema_sha256") != digest(expected["schema"])
                or any(call.get("schema_sha256") != digest(expected["schema"]) or call.get("output_limit") != limit
                       for call in check.get("calls", []))):
            gates.append("hosted_qualification_identity_changed")
        if revision and (check.get("fixture_sha256") != digest(expected)
                         or check.get("ok") is True and check.get("diagnostics", {}).get("expected_match") is not True):
            gates.append("hosted_qualification_identity_changed")
        if cerebras and expected["id"] == "relevance":
            diagnostic = {"expected_match": True, "supplied_marker_membership": True, "duplicate_markers": False, "marker_count": 1}
            if digest(check.get("diagnostics")) != digest(diagnostic):
                gates.append("hosted_qualification_identity_changed")
    if source_hashes() != metadata["source_sha256"]:
        gates.append("hosted_source_changed_since_collection")
    expected_jobs = build_jobs(cases)
    if planned != [job["key"] for job in expected_jobs]:
        gates.append("hosted_matrix_incomplete")
    case_cost = sum(record["hosted"]["known_usage_cost_usd"] for record in records)
    qualification_cost = sum(check["work"]["known_usage_cost_usd"] for check in qualification.get("checks", []))
    return {**original, "hosted_manifest_sha256": manifest_sha, "model": model,
            **({"funding_binding": funding_binding} if cerebras else {}),
            "fixture_manifest_sha256": fixture_sha,
            "gate_failures": sorted(set(gates)), "development_accepted": split == "development" and not gates,
            "holdout_accepted": split == "holdout" and not gates,
            "case_known_usage_cost_usd": case_cost, "qualification_known_usage_cost_usd": qualification_cost,
            "known_usage_cost_usd": case_cost + qualification_cost,
            "unknown_usage_attempts": sum(record["hosted"]["unknown_usage_attempts"] for record in records)
                + sum(check["work"]["unknown_usage_attempts"] for check in qualification.get("checks", []))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("template", "score", "lock", "accept"))
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=("hosted-agent-v1", *PAPER_PROFILES))
    args = parser.parse_args()
    run, output = args.run.resolve(), args.output.resolve()
    roots = [(Path.cwd() / name).resolve() for name in ("test_output", "tests/test_output")]
    if (not any(run.is_relative_to(root) and run != root for root in roots) or output.exists()
            or not any(output.is_relative_to(root) and output != root for root in roots)):
        parser.error("Run/output must be local ignored evidence; output must be fresh")
    metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    _, manifest_sha = scoring_profile(args.profile)
    if metadata.get("hosted_manifest_sha256") != manifest_sha:
        raise ValueError("Unreviewed hosted run")
    if args.operation == "template":
        _, labels, _, _ = load_labels(Path("evaluation/week7_agent"), args.snapshot)
        records = [json.loads(line) for line in (run / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        result = hosted_review_template(records, labels[metadata["split"]]["cases"], metadata["configuration"]["model"],
            fixture_manifest_sha256=metadata.get("fixture_manifest_sha256"), profile_name=args.profile)
    elif args.operation == "accept":
        if args.profile not in PAPER_PROFILES or args.reviews is None or args.reviews.resolve() != (run / "reviews.json").resolve():
            parser.error("App acceptance requires the explicit Cerebras profile and reviews.json inside its holdout run")
        from src.commands.hf_paper_acceptance import create_acceptance_lock

        result = create_acceptance_lock(run, args.snapshot)
    else:
        if args.reviews is None:
            parser.error("Completed semantic reviews are required")
        reviews = json.loads(args.reviews.read_text(encoding="utf-8"))
        extra = {"profile_name": args.profile} if args.profile else {}
        result = score_run(run, args.snapshot, reviews, **extra)
        if args.operation == "lock":
            if not result["development_accepted"]:
                raise ValueError("Development evidence is not accepted")
            report = run / "selection-report.json"
            if report.exists() or (run / "reviews.json").resolve() != args.reviews.resolve():
                raise ValueError("Lock requires fresh report and reviews.json inside its run")
            write_json(report, result)
            result = {"hosted_manifest_sha256": manifest_sha, "model": result["model"],
                      "development_accepted": True, "development_jobs": 64, "development_run": str(run),
                      "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                      "evidence_sha256": {name: hashlib.sha256((run / name).read_bytes()).hexdigest() for name in
                        ("metadata.json", "completion.json", "qualification.json", "records.jsonl", "reviews.json")}}
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, result)
    print(json.dumps({"operation": args.operation, "written": str(output), "accepted": result.get("holdout_accepted", result.get("development_accepted", False))}))


if __name__ == "__main__":
    main()
