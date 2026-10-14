"""Plan prospective synthetic fixture controls offline; this command cannot execute inference."""

import argparse
import hashlib
import json
from pathlib import Path

from src.commands.evaluate_agent import write_json
from src.commands.evaluate_hf_agent import source_hashes
from src.commands.evaluate_retrieval import digest
from src.commands.hf_qualification import load_revision
from src.commands.hf_reproduction import PROMPT_COMPARISON_SHA256, load_prompt_comparison
from src.commands.hf_success_diagnostics import SUCCESS_DIAGNOSTICS_SHA256, load_success_contract

CLARITY_SHA256 = "8cdf31dc0c6e2947ff9e6de2e021a3a7c15b1957d1ec9e1e85a5b2bf2f7c57d1"


def load_clarity(root=Path("evaluation/week7_hf/fixture-clarity-v1")) -> dict:
    manifest = root / "manifest.json"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != CLARITY_SHA256:
        raise ValueError("Fixture clarity manifest differs")
    binding = json.loads(manifest.read_text(encoding="utf-8"))
    load_prompt_comparison()
    load_success_contract()
    if (
        binding["parent_fixture_manifest_sha256"] != load_revision()["manifest_sha256"]
        or binding["parent_prompt_manifest_sha256"] != PROMPT_COMPARISON_SHA256
        or binding["measurement_manifest_sha256"] != SUCCESS_DIAGNOSTICS_SHA256
        or set(binding["sha256"]) != {"PROTOCOL.md", "requests.json"}
    ):
        raise ValueError("Fixture clarity parent differs")
    for name, expected in binding["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Fixture clarity input differs")
    profile = json.loads((root / "requests.json").read_text(encoding="utf-8"))
    return {**profile, "manifest_sha256": CLARITY_SHA256, "measurement_manifest_sha256": SUCCESS_DIAGNOSTICS_SHA256}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    roots = [(Path.cwd() / name).resolve() for name in ("test_output", "tests/test_output")]
    if output.exists() or not any(output.is_relative_to(root) and output != root for root in roots):
        parser.error("Output must be fresh local ignored evidence")
    profile = load_clarity()
    metadata = {
        "status": "offline_plan",
        "kind": profile["kind"],
        "experiment": "fixture-clarity-v1",
        "inference_started": False,
        "qualification_accepted": False,
        "fixture_manifest_sha256": profile["manifest_sha256"],
        "success_diagnostic_manifest_sha256": profile["measurement_manifest_sha256"],
        "arms": list(profile["arms"]),
        "candidate_outbound_attempts": len(profile["arms"]),
        "approved_outbound_budget": 0,
        "outbound_budget": 0,
        "paper_collection_planned": False,
        "payload_sha256": {arm: digest(row["payload"]) for arm, row in profile["arms"].items()},
        "source_sha256": source_hashes(),
    }
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "metadata.json", metadata)
    print(json.dumps({"status": "offline_plan", "candidate_attempts": len(profile["arms"]), "approved_attempts": 0}))


if __name__ == "__main__":
    main()
