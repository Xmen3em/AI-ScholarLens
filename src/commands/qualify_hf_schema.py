"""Default-offline five-case schema qualification; execution needs exact new approval."""

import argparse
import asyncio
import json
import math
from pathlib import Path

from src.commands.evaluate_agent import free_memory_mib, write_json
from src.commands.evaluate_hf_agent import live_snapshot, plan_collection, provider_available, source_hashes
from src.commands.evaluate_retrieval import digest
from src.commands.hf_allowance import PILOT_CASE, PILOT_MODEL
from src.commands.hf_cerebras_allowance import CerebrasAllowance
from src.commands.hf_cerebras_allowance import approval_proposal as cerebras_proposal
from src.commands.hf_cerebras_selectors import SelectorAllowance
from src.commands.hf_cerebras_selectors import approval_proposal as selector_proposal
from src.commands.hf_clarity_allowance import ClarityAllowance
from src.commands.hf_evaluation import MeasuredHF, hosted_admission, load_protocol, qualify
from src.commands.hf_provider_allowance import AlternativeAllowance
from src.commands.hf_provider_allowance import approval_proposal as alternative_proposal
from src.commands.hf_qualification import load_revision
from src.commands.hf_schema_allowance import SchemaAllowance, approval_proposal
from src.commands.hf_schema_execution import load_execution, load_experiment, measurement_profile
from src.config import Settings
from src.middlewares import RateLimiter
from src.services.hf.client import HFGenerationError


class SchemaHF(MeasuredHF):
    def __init__(self, settings: Settings, grant: ClarityAllowance, output: Path, source: dict, *, memory=free_memory_mib,
                 experiment="schema-execution-v1"):
        self.execution = load_experiment(experiment)
        self.experiment = experiment
        self.budget = self.execution["maximum_outbound_attempts"]
        if settings.hf_models != [self.execution["model"]] or settings.hf_default_model != self.execution["model"]:
            raise ValueError("Schema execution requires the frozen model")
        if any(grant.receipt.get(key) != self.execution[key] for key in
               ("manifest_sha256", "model", "endpoint", "maximum_outbound_attempts", "arms")):
            raise ValueError("Schema execution requires approval of this exact provider experiment")
        self.grant, self.output, self.source, self.memory = grant, output, source, memory
        self.position = 0
        super().__init__(settings, outbound_budget=self.budget)

    def _payload(self, model, prompt, system, response_format, options):
        payload = super()._payload(model, prompt, system, response_format, options)
        if self.position >= self.budget or digest(payload) != digest(self.execution["payloads"][self.position]):
            raise ValueError("Request differs from frozen schema execution")
        return payload

    async def generate_result(self, model, prompt, **kwargs):
        if self.position >= self.budget:
            raise HFGenerationError("Schema execution attempt budget exhausted")
        self._payload(model, prompt, kwargs.get("system"), kwargs.get("response_format"), kwargs.get("options"))
        free_mib = self.memory()
        if not math.isfinite(free_mib) or free_mib < load_protocol()["live_margin_mib"]:
            raise ValueError("Schema execution resource margin failed")
        if source_hashes() != self.source:
            raise ValueError("Schema execution source changed")
        # Revalidates all immutable inputs and completed parents before reserving.
        load_experiment(self.experiment)
        arm = self.execution["arms"][self.position]
        self.grant.reserve(str(self.output), arm)
        before = self.attempts
        try:
            return await super().generate_result(model, prompt, **kwargs)
        finally:
            attempts = self.attempts - before
            self.grant.settle(arm, attempts if attempts in {0, 1} else None)
            self.position += 1


async def collect(settings: Settings, grant: ClarityAllowance, output: Path, source: dict, *, memory=free_memory_mib,
                  experiment="schema-execution-v1") -> dict:
    client = SchemaHF(settings, grant, output, source, memory=memory, experiment=experiment)
    try:
        revision = {**load_revision(), "cases": client.execution["cases"]}
        result = await qualify(client, measurement_profile(experiment), limiter=RateLimiter(settings), memory=memory, revision=revision)
        return {"kind": "schema_qualification_only", "app_accepted": False,
                "qualification": result, "outbound_attempts": client.attempts,
                "diagnostic_passed": (experiment in {"cerebras-remaining-v1", "cerebras-selectors-v1"}
                                      and len(result["checks"]) == client.budget
                                      and all(check["ok"] for check in result["checks"]))}
    finally:
        await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--experiment", choices=["schema-execution-v1", "provider-alternative-v1", "cerebras-remaining-v1", "cerebras-selectors-v1"],
                        default="schema-execution-v1")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--propose-approval", action="store_true")
    args = parser.parse_args()
    profile = load_experiment(args.experiment)
    alternative = args.experiment == "provider-alternative-v1"
    cerebras = args.experiment == "cerebras-remaining-v1"
    selectors = args.experiment == "cerebras-selectors-v1"
    budget = profile["maximum_outbound_attempts"]
    output = args.output.resolve()
    roots = [(Path.cwd() / name).resolve() for name in ("test_output", "tests/test_output")]
    if output.exists() or not any(output.is_relative_to(root) and output != root for root in roots):
        parser.error("Output must be fresh local ignored evidence")
    metadata = plan_collection(args.snapshot, split="development", model=PILOT_MODEL,
                               case_ids=[PILOT_CASE], modes=["bm25"], transports=["json"], qualification_v2=True)
    # The original planner validates retained labels under its unchanged Groq-only
    # pilot contract. This command sends no paper jobs; name the actual schema model.
    metadata["configuration"]["model"] = profile["model"]
    metadata.update(kind=profile["kind"], jobs=[], arms=profile["arms"], planned_outbound_budget=budget,
                    schema_execution_manifest_sha256=profile["manifest_sha256"], app_accepted=False,
                    proposed_outbound_budget=budget, approved_outbound_budget=0, outbound_budget=0, paper_collection_planned=False)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "metadata.json", metadata)
    if args.propose_approval:
        proposal = selector_proposal() if selectors else cerebras_proposal() if cerebras else alternative_proposal() if alternative else approval_proposal()
        write_json(output / "proposed-approval.json", proposal)
        print(json.dumps({"status": "pending_user_approval", "maximum_attempts": budget}))
        return
    if not args.execute:
        print(json.dumps({"status": "offline_plan", "proposed_attempts": budget, "approved_attempts": 0}))
        return
    try:
        if args.approval is None:
            raise ValueError("Additional approval required")
        grant = SelectorAllowance(args.approval) if selectors else CerebrasAllowance(args.approval) if cerebras else AlternativeAllowance(args.approval) if alternative else SchemaAllowance(args.approval)
    except Exception:
        metadata.update(status="not_started", reason="approval_required")
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "reason": "approval_required"}))
        return
    settings = Settings()
    metadata["admission_free_mib"] = free_memory_mib()
    reason = hosted_admission(settings, [], metadata["admission_free_mib"], load_protocol())
    if reason:
        metadata.update(status="not_started", reason=reason)
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "reason": reason}))
        return
    try:
        before, _, _ = live_snapshot(settings)
        if before != json.loads((args.snapshot / "state.json").read_text(encoding="utf-8")):
            raise ValueError("Live source snapshot differs")
        metadata["provider_catalog"] = provider_available(profile["model"])
        local = Settings.model_validate(settings.model_copy(update={"hf_inference_enabled": True,
            "hf_models": [profile["model"]], "hf_default_model": profile["model"], "answer_cache_enabled": False,
            "local_tracing_enabled": False, "monitoring_directory": None,
            "api_rate_limit_path": str(output / "quotas.sqlite3")}).model_dump())
    except Exception:
        metadata.update(status="not_started", reason="preflight_failed")
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "reason": "preflight_failed"}))
        return
    metadata.update(status="qualifying_schema", inference_started=None, approved_outbound_budget=budget,
                    outbound_budget=budget, approval_sha256=grant.signature)
    write_json(output / "metadata.json", metadata)
    try:
        extra = {"experiment": args.experiment} if alternative or cerebras or selectors else {}
        result = asyncio.run(collect(local, grant, output, metadata["source_sha256"], **extra))
    except Exception:
        result = {"kind": "schema_qualification_only", "app_accepted": False,
                  "qualification": {"qualified": False}, "outbound_attempts": None, "error_class": "CollectionInterrupted"}
    preservation = {"source_unchanged": source_hashes() == metadata["source_sha256"], "frozen_labels_unchanged": False,
                    "corpus_unchanged": False, "models_unchanged": False}
    try:
        load_experiment(args.experiment)
        plan_collection(args.snapshot, split="development", model=PILOT_MODEL,
                        case_ids=[PILOT_CASE], modes=["bm25"], transports=["json"], qualification_v2=True)
        preservation["frozen_labels_unchanged"] = True
        after, _, _ = live_snapshot(settings)
        preservation.update(corpus_unchanged=after == before, models_unchanged=True)
    except Exception:
        pass
    result.update(preservation=preservation, extension_attempts_used=grant.used,
                  original_attempts_used=26 if selectors else 23 if alternative or cerebras else 21,
                  schema_execution_manifest_sha256=profile["manifest_sha256"],
                  schema_qualified=(all(preservation.values()) and result["qualification"].get("qualified") is True
                                    and result["outbound_attempts"] == 5))
    write_json(output / "qualification.json", result)
    metadata.update(status="schema_qualification_completed", inference_started=(result["outbound_attempts"] > 0
                    if result["outbound_attempts"] is not None else None))
    write_json(output / "metadata.json", metadata)
    print(json.dumps({"status": metadata["status"], "outbound_attempts": result["outbound_attempts"],
                      "schema_qualified": result["schema_qualified"], "app_accepted": False, "preservation": preservation}), flush=True)


if __name__ == "__main__":
    main()
