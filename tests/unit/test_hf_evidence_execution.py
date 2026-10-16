import json
import sys
from unittest.mock import Mock

import httpx
import pytest
from src.commands import evaluate_hf_papers as cli
from src.commands import hf_paper_client as client_module
from src.commands import score_hf_agent as scoring
from src.commands.hf_paper_allowance import TaskAllowance
from src.commands.hf_paper_profile import EVIDENCE_PROFILE, EVIDENCE_TASK_SHA256
from src.config import Settings
from src.operations import request_context
from src.schemas.api.rag import GeneratedAnswer
from src.services.rag.service import _selection_pattern

from tests.unit.test_hf_client import envelope, settings
from tests.unit.test_hf_evidence_allowance import evidence_setup
from tests.unit.test_hf_paper_client import arguments
from tests.unit.test_hf_paper_scoring import complete_development
from tests.unit.test_hf_tokenizer import install_vocabulary


def test_evidence_cli_proposal_is_unfunded_and_does_not_read_credentials(tmp_path, monkeypatch):
    metadata, _, path = evidence_setup(tmp_path, monkeypatch, approved=False)
    monkeypatch.setattr(cli, "plan_collection", lambda *a, **k: metadata.copy())
    monkeypatch.setattr(cli, "Settings", lambda: pytest.fail("Proposal read credentials"))
    monkeypatch.setattr(sys, "argv", ["evaluate_hf_papers", "--snapshot", str(tmp_path), "--profile", EVIDENCE_PROFILE,
                                    "--output", str(tmp_path / "proposal"), "--propose-approval"])
    cli.main()
    proposed = json.loads((tmp_path / "proposal/proposed-approval.json").read_text())
    assert proposed["status"] == "pending_user_approval" and proposed["prior_attempts_used"] == 125
    assert proposed["hosted_manifest_sha256"] == EVIDENCE_TASK_SHA256
    assert not path.exists() and not path.with_suffix(".registered").exists()


def test_approved_evidence_collector_receives_exact_profile_without_changing_private_settings(tmp_path, monkeypatch):
    metadata, approval, path = evidence_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "plan_collection", lambda *a, **k: metadata.copy())
    monkeypatch.setattr(cli, "source_hashes", lambda: metadata["source_sha256"].copy())
    original = settings(agent_enabled=False, rag_sentence_candidates_per_passage=1).model_copy(
        update={"hf_inference_enabled": False})
    before = original.model_dump()
    factory = Mock(return_value=original); factory.model_validate = Settings.model_validate
    monkeypatch.setattr(cli, "Settings", factory)
    monkeypatch.setattr(cli, "free_memory_mib", lambda: 4096)
    monkeypatch.setattr(cli, "live_snapshot", lambda s: ({}, [], []))
    monkeypatch.setattr(cli, "provider_available", lambda model: {"pricing": {"input": .35, "output": .75}})
    cases = [{"id": f"case-{i}", "query": "synthetic paper question"} for i in range(8)]
    monkeypatch.setattr(cli, "load_labels", lambda *a: ({}, {"development": {"cases": cases}}, [], []))
    (tmp_path / "state.json").write_text("{}")
    seen = []

    async def collect(config, jobs, papers, chunks, output, profile, budget, **kwargs):
        assert config.rag_sentence_candidates_per_passage == 3 and config.rag_max_sentence_candidates == 10
        assert config.hf_inference_enabled and config.agent_enabled and not config.answer_cache_enabled
        assert len(jobs) == 64 and budget == 261 and profile["version"] == EVIDENCE_PROFILE
        assert kwargs["hf_factory"].keywords["profile_name"] == EVIDENCE_PROFILE
        seen.append(True)
        return {"status": "stopped", "outbound_attempts": 0}

    monkeypatch.setattr(cli, "run_collection", collect)
    monkeypatch.setattr(sys, "argv", ["evaluate_hf_papers", "--snapshot", str(tmp_path), "--profile", EVIDENCE_PROFILE,
                                    "--output", str(tmp_path / "run"), "--execute", "--approval", str(approval)])
    cli.main()
    assert seen and path.exists() and original.model_dump() == before


@pytest.mark.anyio
async def test_evidence_client_qualifies_then_enforces_ten_candidate_boundary(tmp_path, monkeypatch, stub_httpx):
    install_vocabulary(tmp_path, monkeypatch)
    metadata, approval, path = evidence_setup(tmp_path, monkeypatch)
    grant = TaskAllowance(approval, metadata, snapshot=tmp_path)
    monkeypatch.setattr(client_module, "source_hashes", lambda: metadata["source_sha256"].copy())
    config = settings(hf_models=["openai/gpt-oss-120b:cerebras"], hf_default_model="openai/gpt-oss-120b:cerebras",
                      agent_enabled=True, answer_cache_enabled=False, local_tracing_enabled=False,
                      monitoring_directory=None, rag_sentence_candidates_per_passage=3, rag_max_sentence_candidates=10)
    cases = client_module.load_cerebras()["cases"] + client_module.load_selectors()["cases"]
    outputs = [case["expected"] or {"query": "synthetic retrieval rewrite"} for case in cases] + [{"answer": "E1"}]
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope(json.dumps(outputs.pop(0)),
                                                        usage={"prompt_tokens": 100, "completion_tokens": 20})))
    hf = client_module.FundedHF(config, grant=grant, output=tmp_path, source=metadata["source_sha256"],
                                outbound_budget=261, memory=lambda: 4096, profile_name=EVIDENCE_PROFILE)
    try:
        for case in cases:
            await hf.generate_result(config.hf_default_model, case["prompt"], **arguments(case))
        token = request_context.set({"request_id": "bounded-evidence"})
        try:
            schema = GeneratedAnswer.model_json_schema()
            schema["properties"]["answer"] = {"type": "string", "pattern": _selection_pattern(10)}
            await hf.generate_result(config.hf_default_model, "Synthetic ten-candidate selection", response_format=schema)
            schema["properties"]["answer"]["pattern"] = _selection_pattern(11)
            with pytest.raises(ValueError):
                await hf.generate_result(config.hf_default_model, "Synthetic eleven-candidate selection", response_format=schema)
        finally:
            request_context.reset(token)
        assert hf.attempts == grant.used == len(calls) == 6 and grant.path == path
    finally:
        await hf.aclose()


def test_evidence_scoring_uses_funded_complete_matrix_without_lowering_quality_gates(tmp_path, monkeypatch):
    reviews = complete_development(tmp_path, monkeypatch)
    path = tmp_path / "metadata.json"
    metadata = json.loads(path.read_text())
    metadata["configuration"]["policy"] = EVIDENCE_PROFILE
    metadata["hosted_manifest_sha256"] = reviews["hosted_manifest_sha256"] = EVIDENCE_TASK_SHA256
    path.write_text(json.dumps(metadata))
    result = scoring.score_run(tmp_path, tmp_path, reviews, profile_name=EVIDENCE_PROFILE)
    assert result["development_accepted"] and result["funding_binding"] == "funded-proof"
    assert result["attempts"] == 64 and result["gate_failures"] == []
