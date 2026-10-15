"""User-selected Cerebras diagnostic reallocates three existing slots, never adds funds."""

import json
from pathlib import Path

from src.commands.evaluate_retrieval import digest
from src.commands.hf_provider_allowance import STOPPED_APPROVAL, STOPPED_RUN, stopped_binding
from src.commands.hf_schema_allowance import REALLOCATION_PATH, SCHEMA_ALLOWANCE_PATH, SchemaAllowance
from src.commands.hf_schema_allowance import approval_proposal as schema_proposal
from src.commands.hf_schema_execution import load_cerebras

CEREBRAS_ALLOWANCE_PATH = Path("tests/test_output/hf-cerebras-allowance-20261015/allowance.sqlite3")
AUTHORITY = "user_provider_instruction_with_remaining_approved_budget"


def allocation_proposal(*, stopped_path=SCHEMA_ALLOWANCE_PATH, stopped_approval=STOPPED_APPROVAL, stopped_run=STOPPED_RUN,
                        **parents) -> dict:
    profile = load_cerebras()
    return {"kind": "hf_remaining_provider_allocation_v1", "status": "approved", "authorization_source": AUTHORITY,
            "user_instruction": "you can use this openai/gpt-oss-120b:cerebras",
            "model": profile["model"], "manifest_sha256": profile["manifest_sha256"],
            "maximum_remaining_attempts": 3, "attempts_used_before": 23, "retained_total_ceiling": 26,
            "stopped_schema_allowance_binding": stopped_binding(stopped_path=stopped_path,
                stopped_approval=stopped_approval, stopped_run=stopped_run, **parents)}


def approval_proposal(*, stopped_path=SCHEMA_ALLOWANCE_PATH, stopped_approval=STOPPED_APPROVAL, stopped_run=STOPPED_RUN,
                      **parents) -> dict:
    profile = load_cerebras()
    proposal = schema_proposal(**parents)
    allocation = allocation_proposal(stopped_path=stopped_path, stopped_approval=stopped_approval, stopped_run=stopped_run, **parents)
    proposal.update(kind="hf_cerebras_remaining_approval_v1", manifest_sha256=profile["manifest_sha256"],
                    model=profile["model"], maximum_outbound_attempts=3, arms=profile["arms"], scope=profile["approval_scope"],
                    allocation_contract_sha256=digest(allocation),
                    stopped_schema_allowance_binding=allocation["stopped_schema_allowance_binding"])
    return proposal


class CerebrasAllowance(SchemaAllowance):
    maximum_arms = 3
    authorization_source = AUTHORITY

    def __init__(self, approval: Path, *, path=CEREBRAS_ALLOWANCE_PATH, allocation=REALLOCATION_PATH,
                 stopped_path=SCHEMA_ALLOWANCE_PATH, stopped_approval=STOPPED_APPROVAL, stopped_run=STOPPED_RUN, **parents):
        self.allocation = Path(allocation)
        self.stopped = {"stopped_path": stopped_path, "stopped_approval": stopped_approval, "stopped_run": stopped_run}
        super().__init__(approval, path=path, **parents)

    def _proposal(self) -> dict:
        expected = allocation_proposal(**self.parents, **self.clarity, **self.stopped)
        if digest(json.loads(self.allocation.read_text(encoding="utf-8"))) != digest(expected):
            raise ValueError("Exact retained-budget provider allocation is required")
        return approval_proposal(**self.parents, **self.clarity, **self.stopped)
